"""
Retrieving matching documents for question an create summary text
"""

import asyncio
import logging
import aiohttp
from math import ceil

from django.conf import settings

from integreat_chat.search.services.search import SearchService
from integreat_chat.search.utils.search_request import SearchRequest
from integreat_chat.search.utils.search_response import Document
from integreat_chat.translate.services.language import LanguageService

from ..static.prompts import Prompts
from ..static.messages import Messages
from ..utils.rag_response import RagResponse
from ..utils.rag_request import RagRequest
from .llmapi import LlmApiClient, LlmMessage, LlmPrompt, LlmResponse

LOGGER = logging.getLogger("django")


class AnswerService:
    """
    Service for providing summary answers to question-like messages.
    """

    def __init__(self, rag_request: RagRequest) -> None:
        """
        param region: Integreat CMS region slug
        param language: Integreat CMS language slug
        """
        self.rag_request = rag_request
        self.language = rag_request.last_message.use_language
        self.region = rag_request.region
        self.llm_model_name = settings.RAG_MODEL
        self.llm_api = LlmApiClient()

    def message_requires_context(self) -> bool:
        """
        Check if the last message is a standalone message or requires context of previous messages
        """
        prompt = Prompts.CONTEXT_CHECK.format(self.rag_request.last_message.translated_message)
        return self.llm_api.simple_prompt(prompt).startswith("yes")

    def prepare_request_human_prompt(self) -> LlmPrompt:
        """
        Prepare prompt for checking if a human ist requested
        """
        return LlmPrompt(settings.RAG_RELEVANCE_CHECK_MODEL, [
            LlmMessage(Prompts.HUMAN_REQUEST_CHECK.format(
                self.rag_request.last_message.translated_message
            ), "user")
        ])

    def prepare_summarize_prompt(self, num_messages: int) -> LlmPrompt:
        """
        Prepare prompt for message summary
        """
        prompt_text = Prompts.SUMMARIZE_MESSAGE.replace(
            "LANG_CODE",
            str(self.rag_request.last_message.use_language)
        )
        return LlmPrompt(settings.RAG_RELEVANCE_CHECK_MODEL,
            [LlmMessage(prompt_text, role="system")] +
            self.rag_request.messages[-num_messages:]
        )

    def prepare_accept_message_prompt(self, num_messages: int) -> LlmPrompt:
        """
        Prepare prompt for checking if a human ist requested
        """
        return LlmPrompt(settings.RAG_RELEVANCE_CHECK_MODEL,
            [LlmMessage(Prompts.CHECK_QUESTION, role="system")] +
            self.rag_request.messages[-num_messages:]
        )

    async def check_message_parallelized(self, num_messages: int) -> tuple[bool,str,bool]:
        """
        Check if a chat message is a question

        :return: request human, summarized message, accept_message
        """
        tasks = []
        async with aiohttp.ClientSession() as session:
            # HUMAN_REQUEST_CHECK
            tasks.append(
                asyncio.create_task(self.llm_api.chat_prompt(
                    session,
                    self.prepare_request_human_prompt()
                )
            ))
            LOGGER.debug("Sent HUMAN_REQUEST_CHECK")
            # SUMMARIZE_MESSAGE
            tasks.append(
                asyncio.create_task(self.llm_api.chat_prompt(
                    session,
                    self.prepare_summarize_prompt(num_messages)
                ))
            )
            LOGGER.debug("Sent SUMMARIZE_MESSAGE")
            # CHECK_QUESTION
            tasks.append(
                asyncio.create_task(self.llm_api.chat_prompt(
                    session,
                    self.prepare_accept_message_prompt(num_messages)
                ))
            )
            LOGGER.debug("Sent CHECK_QUESTION")
            llmresponses = await asyncio.gather(*tasks)
        LOGGER.debug("Gathered check responses")
        return (
            str(LlmResponse(llmresponses[0])).lower().startswith("yes"),
            str(LlmResponse(llmresponses[1])),
            str(LlmResponse(llmresponses[2])).lower().startswith("yes"),
        )

    def skip_rag_answer(self, language_service: LanguageService) -> str|bool:
        """
        Check if a chat message is a question

        :param message: a user message
        :return: answer message if no further processing is required, else False
        """
        num_messages = settings.RAG_CONTEXT_LENGTH if self.message_requires_context() else 1
        LOGGER.debug("Using the last %s messages.", num_messages)
        request_human, summary, accept_message = asyncio.run(
            self.check_message_parallelized(num_messages)
        )
        automatic_answer = True
        if request_human:
            automatic_answer = False
            message = Messages.TALK_TO_HUMAN
        else:
            if accept_message:
                self.rag_request.search_term = summary
                LOGGER.debug("Message requires response.")
                return False
            message = Messages.NOT_QUESTION
            LOGGER.debug("Message does not require response.")
        return RagResponse(
            [],
            self.rag_request,
            language_service.translate_message(
                "en", self.language, message
            ),
            automatic_answer,
        )

    def get_documents(self, shallow_search: bool = False) -> list:
        """
        Retrieve documents for RAG

        :param shallow_search: indicates that this is a shallow search.
        """
        LOGGER.debug("Retrieving documents for: %s", self.rag_request.search_term)
        search_request = SearchRequest(
            {
                "message": str(self.rag_request.search_term),
                "language": self.rag_request.last_message.use_language,
                "region": self.rag_request.region
            },
            True
        )
        search = SearchService(search_request, deduplicate_results=True)
        documents = search.search_documents(
            settings.RAG_MAX_PAGES * 4,
            min_score=settings.RAG_SCORE_THRESHOLD,
        ).documents
        batches = ceil(len(documents)/3)
        filtered_documents = []
        for batch in range(0, batches):
            filtered_documents += self.filter_documents(documents[batch*3:batch*3+3])
            relevant_docs = self.count_relevant_documents(filtered_documents)
            if (relevant_docs > 1 and batch == 0) or (relevant_docs >= 1 and batch > 0):
                break
        if not self.count_relevant_documents(documents) and not shallow_search:
            self.rag_request.search_term = self.llm_api.simple_prompt(
                Prompts.SHALLOW_SEARCH.format(
                    self.rag_request.last_message.use_language,
                    self.rag_request.search_term
                )
            )
            LOGGER.debug(
                "No documents found, trying shallow search: %s.",
                self.rag_request.search_term
            )
            return self.get_documents(shallow_search=True)
        LOGGER.debug("Retrieved %s documents.", len(filtered_documents))
        return filtered_documents

    def count_relevant_documents(self, documents: list) -> int:
        """
        Count the number of relevant documents in the list.

        :param documents: list of documents with relevance check performed
        :return: number of relevant documents
        """
        relevant_docs = 0
        for document in documents:
            if document.include_in_answer:
                relevant_docs += 1
        return relevant_docs

    def filter_documents(self, documents: list) -> list:
        """
        Filter documents by checking for relevance

        :param search_results: results/hits coming from search index
        :return: filtered list of documents
        """
        if settings.RAG_RELEVANCE_CHECK:
            documents = asyncio.run(self.check_documents_relevance(
                str(self.rag_request.search_term), documents)
            )
        return documents

    def format_context(self, documents: list) -> str:
        """
        Format retrieved documents into context string.

        :param documents: list of documents
        :return: Mardown formatted text for RAG context
        """
        return "\n---\n".join(
            [
                f"# {' > '.join(result.parent_titles + [result.title])}\n{result.content}"
                for result in documents
                if result.include_in_answer
            ]
        )[: settings.RAG_CONTEXT_MAX_LENGTH]

    def get_no_answer_response(
            self,
            language_service: LanguageService,
            documents: list
        ) -> RagResponse:
        """
        Generate response that no answer has been found
        """
        return RagResponse(
                documents,
                self.rag_request,
                language_service.translate_message(
                    "en", self.language, Messages.NO_ANSWER
                ),
            )

    def format_rag_prompt(self, documents: list) -> str:
        """
        Generate RAG prompt including context
        """
        return Prompts.RAG.format(
            settings.INTEGREAT_REGION_NAMES[self.region],
            self.language,
            self.rag_request.search_term,
            self.format_context(documents)
        )

    def answer_valid(self, answer: str, documents: list[Document]) -> bool:
        """
        Check if a given answer is valid
        """
        if not settings.RAG_FACT_CHECK:
            return True
        check = self.llm_api.simple_prompt(Prompts.FACT_CHECK.format(
            answer,
            self.format_context(documents)
        ))
        if check.lower().startswith('not valid'):
            LOGGER.info(
                "Answer not valid. Question: %s\nAnswer: %s\nReason: %s",
                self.rag_request.search_term,
                answer,
                check
            )
        return answer != "" and check.lower().startswith("valid")

    def extract_answer(self) -> RagResponse:
        """
        Search for pages that are related to the question and create
        answer that summarizes the content of found pages.

        return: a dict containing a response and sources
        """
        language_service = LanguageService()

        if response := self.skip_rag_answer(language_service):
            return response
        documents = self.get_documents()
        rag_documents = (
            [document for document in documents if document.include_in_answer]
            [:settings.RAG_MAX_PAGES]
        )
        if not rag_documents:
            no_answer_response = self.get_no_answer_response(language_service, documents)
            LOGGER.info("No documents found for : %s", self.rag_request.search_term)
            return no_answer_response
        retries = 0
        while True:
            retries += 1
            answer = self.llm_api.simple_prompt(self.format_rag_prompt(rag_documents))
            if self.answer_valid(answer, rag_documents):
                LOGGER.info(
                    "Finished generating answer. Question: %s\nAnswer: %s",
                    self.rag_request.search_term,
                    answer
                )
                break
            if retries >= 3:
                LOGGER.info(
                    "Stopped after 3rd attempt. Could not generate valid answer for question: %s\n",
                    self.rag_request.search_term
                )
                answer = ""
                break

        if answer == "":
            return no_answer_response
        return RagResponse(documents, self.rag_request, answer)

    async def check_documents_relevance(self, question: str, search_results: list) -> bool:
        """
        Check if the retrieved documents are relevant for answering the question

        param question: a message/question from a user
        param content: a page content that could be relevant for answering the question
        return: bool that indicates if the page is relevant for the question
        """
        tasks = []
        async with aiohttp.ClientSession() as session:
            for document in search_results:
                tasks.append(
                    asyncio.create_task(self.llm_api.chat_prompt(
                        session,
                        LlmPrompt(settings.RAG_RELEVANCE_CHECK_MODEL, [
                            LlmMessage(Prompts.CHECK_DOCUMENT.format(
                                f"## {document.parent_titles}\n\n{document.content}"
                            ), "system"),
                            LlmMessage(question)]
                        )
                    )
                ))
            llmresponses = await asyncio.gather(*tasks)
        for i, response in enumerate(llmresponses):
            llm_response = LlmResponse(response)
            LOGGER.info(
                "Using %s: %s",
                search_results[i].gui_source_path,
                str(llm_response)
            )
            search_results[i].include_in_answer = str(llm_response).lower().startswith("yes")
            search_results[i].reason_inclusion = str(llm_response)
        return search_results