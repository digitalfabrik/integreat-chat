"""
Retrieving matching documents for question an create summary text
"""

import asyncio
import json
import logging
import aiohttp

from django.conf import settings

from integreat_chat.search.services.search import SearchService
from integreat_chat.search.utils.search_request import SearchRequest
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

    def skip_rag_answer(self, language_service: LanguageService) -> str|bool:
        """
        Check if a chat message is a question

        :param message: a user message
        :return: answer message if no further processing is required, else False
        """
        automatic_answer = True
        if self.detect_request_human():
            automatic_answer = False
            message = Messages.TALK_TO_HUMAN
        else:
            prompt_text = Prompts.CHECK_QUESTION.replace(
                    "LANG_CODE",
                    str(self.rag_request.last_message.use_language)
                )
            prompt = LlmPrompt(
                settings.LANGUAGE_CLASSIFICATION_MODEL,
                [LlmMessage(prompt_text, role="system")] + self.rag_request.messages,
                json_schema = Prompts.CHECK_QUESTION_SCHEMA
            )
            response = json.loads(asyncio.run(
                self.llm_api.chat_prompt_session_wrapper(prompt)
            )["choices"][0]["message"]["content"])
            if response["accept_message"]:
                self.rag_request.search_term = response["summarized_user_question"]
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
        LOGGER.debug("Retrieving documents for: %s.", self.rag_request.search_term)
        search_request = SearchRequest(
            {
                "message": str(self.rag_request.search_term),
                "language": self.rag_request.last_message.use_language,
                "region": self.rag_request.region
            },
            True
        )
        search = SearchService(search_request, deduplicate_results=True)
        search_results = search.search_documents(
            settings.RAG_MAX_PAGES * 2,
            min_score=settings.RAG_SCORE_THRESHOLD,
        ).documents
        documents = self.filter_documents(search_results)[:settings.RAG_MAX_PAGES]
        if not documents and not shallow_search:
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
        LOGGER.debug("Retrieved %s documents.", len(documents))
        return documents

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
        no_answer_response = self.get_no_answer_response(language_service, documents)
        if not documents:
            LOGGER.info("No documents found for : %s", self.rag_request.search_term)
            return no_answer_response
        answer = self.llm_api.simple_prompt(self.format_rag_prompt(documents))
        LOGGER.info(
            "Finished generating answer. Question: %s\nAnswer: %s",
            self.rag_request.search_term,
            answer
        )
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

    def detect_request_human(self) -> bool:
        """
        Check if the user requests to talk to a human counselor or is asking a question
        return: bool that indicates if the user requests a human or not
        """
        if not settings.RAG_HUMAN_REQUEST_CHECK:
            return False
        LOGGER.debug("Checking if user requests human intervention")
        response = self.llm_api.simple_prompt(Prompts.HUMAN_REQUEST_CHECK.format(
            self.rag_request.last_message.translated_message
        ))
        LOGGER.debug("Finished checking if user requests human. Response: %s", response)
        return response.lower().startswith("yes")
