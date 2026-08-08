"""
Retrieving matching documents for question an create summary text
"""

import asyncio
import logging
from math import ceil

import aiohttp
from asgiref.sync import sync_to_async
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
        self.shallow_search = False

    async def message_requires_context(self, session: aiohttp.ClientSession) -> bool:
        """
        Check if the last message is a standalone message or requires context of previous messages
        """
        prompt = Prompts.CONTEXT_CHECK.format(self.rag_request.last_message.translated_message)
        response = await self.llm_api.simple_prompt(session, prompt)
        return response.startswith("yes")

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
            str(self.rag_request.last_message.use_language),
        ).replace(
            "MESSAGES",
            "---\n".join([message.translated_message for message in self.rag_request.messages[-num_messages:]])
        )
        return LlmPrompt(settings.RAG_RELEVANCE_CHECK_MODEL,
            [LlmMessage(prompt_text, role="system")],
            json_schema=Prompts.SUMMARIZE_MESSAGE_SCHEMA,
        )

    def prepare_accept_message_prompt(self, num_messages: int) -> LlmPrompt:
        """
        Prepare prompt for checking if a human ist requested
        """
        return LlmPrompt(settings.RAG_RELEVANCE_CHECK_MODEL,
            [LlmMessage(Prompts.CHECK_QUESTION, role="system")] +
            self.rag_request.messages[-num_messages:]
        )

    async def check_message_parallelized(
        self, session: aiohttp.ClientSession, num_messages: int
    ) -> tuple[bool, str, list[str], bool]:
        """
        Check if a chat message is a question

        :return: request human, summarized message, search terms, accept_message
        """
        tasks = [
            asyncio.create_task(self.llm_api.chat_prompt(
                session, self.prepare_request_human_prompt()
            )),
            asyncio.create_task(self.llm_api.chat_prompt(
                session, self.prepare_summarize_prompt(num_messages)
            )),
            asyncio.create_task(self.llm_api.chat_prompt(
                session, self.prepare_accept_message_prompt(num_messages)
            )),
        ]
        LOGGER.debug("Sent HUMAN_REQUEST_CHECK / SUMMARIZE_MESSAGE / CHECK_QUESTION")
        llmresponses = await asyncio.gather(*tasks)
        LOGGER.debug("Gathered check responses")
        summary, search_terms = self.parse_summary_response(llmresponses[1])
        return (
            str(LlmResponse(llmresponses[0])).lower().startswith("yes"),
            summary,
            search_terms,
            str(LlmResponse(llmresponses[2])).lower().startswith("yes"),
        )

    def parse_summary_response(self, response: dict) -> tuple[str, list[str]]:
        """
        Parse the structured summarize response into a summary and search terms.

        Falls back gracefully if the JSON is malformed or incomplete, so the
        retrieval step always receives at least one usable term.

        :param response: raw LLM response dict for the summarize prompt
        :return: summary string and list of search terms
        """
        parsed = LlmResponse(response).as_dict()
        summary = str(parsed.get("summary", "")).strip()
        search_terms = [
            str(term).strip()
            for term in parsed.get("search_terms", [])
            if str(term).strip()
        ]
        if not summary and not search_terms:
            summary = str(LlmResponse(response)).strip()
        if not summary and search_terms:
            summary = search_terms[0]
        if not search_terms and summary:
            search_terms = [summary]
        return summary, search_terms

    async def skip_rag_answer(
        self,
        session: aiohttp.ClientSession,
        language_service: LanguageService,
    ) -> RagResponse | bool:
        """
        Check if a chat message is a question

        :param message: a user message
        :return: answer message if no further processing is required, else False
        """
        num_messages = (
            settings.RAG_CONTEXT_LENGTH
            if await self.message_requires_context(session)
            else 1
        )
        LOGGER.debug("Using the last %s messages.", num_messages)
        request_human, summary, search_terms, accept_message = await self.check_message_parallelized(
            session, num_messages
        )
        automatic_answer = True
        if request_human and settings.INTEGREAT_REGIONS[self.region]["human_counseling"]:
            automatic_answer = False
            message = Messages.TALK_TO_HUMAN
        else:
            if accept_message:
                self.rag_request.search_term = summary
                self.rag_request.search_terms = search_terms
                LOGGER.debug("Message requires response.")
                return False
            message = Messages.NOT_QUESTION
            LOGGER.debug("Message does not require response.")
        return RagResponse(
            [],
            self.rag_request,
            await language_service.translate_message(
                "en", self.language, message, session=session
            ),
            automatic_answer,
        )

    async def get_documents(self, session: aiohttp.ClientSession) -> list:
        """
        Retrieve documents for RAG
        """
        terms = self.rag_request.search_terms or [self.rag_request.search_term]
        LOGGER.debug("Retrieving documents for: %s", terms)
        results = await asyncio.gather(
            *[self.search_for_term(session, term) for term in terms]
        )
        documents = self.merge_documents(results)
        batches = ceil(len(documents)/3)
        filtered_documents = []
        for batch in range(0, batches):
            filtered_documents += await self.filter_documents(
                session, documents[batch*3:batch*3+3]
            )
            relevant_docs = self.count_relevant_documents(filtered_documents)
            if (relevant_docs > 1 and batch == 0) or (relevant_docs >= 1 and batch > 0):
                break
        if not self.count_relevant_documents(documents) and not self.shallow_search:
            shallow_term = await self.llm_api.simple_prompt(
                session,
                Prompts.SHALLOW_SEARCH.format(
                    self.rag_request.last_message.use_language,
                    self.rag_request.search_term
                )
            )
            self.rag_request.search_term = shallow_term
            self.rag_request.search_terms = [shallow_term]
            LOGGER.debug(
                "No documents found, trying shallow search: %s.",
                self.rag_request.search_term
            )
            self.shallow_search = True
            return await self.get_documents(session)
        LOGGER.debug("Retrieved %s documents.", len(filtered_documents))
        return filtered_documents

    async def search_for_term(
        self, session: aiohttp.ClientSession, term: str
    ) -> list:
        """
        Run a single OpenSearch query for one search term.

        :param session: shared aiohttp session
        :param term: search term to query
        :return: list of retrieved documents
        """
        search_request = SearchRequest(
            {
                "message": str(term),
                "language": self.rag_request.last_message.use_language,
                "region": self.rag_request.region
            },
            True
        )
        await search_request.prepare(session=session)
        search = SearchService(search_request, deduplicate_results=True)
        search_response = await sync_to_async(
            search.search_documents, thread_sensitive=False
        )(
            settings.RAG_MAX_PAGES * 4,
            settings.RAG_SCORE_THRESHOLD,
        )
        return search_response.documents

    def merge_documents(self, result_lists: list) -> list:
        """
        Merge documents retrieved for the individual search terms. Deduplicate
        by page URL, keeping the highest scoring occurrence, and sort by score
        descending.

        :param result_lists: list of document lists, one per search term
        :return: merged and sorted list of documents
        """
        merged: dict = {}
        for documents in result_lists:
            for document in documents:
                key = document.chunk_source_path
                if key not in merged or document.score > merged[key].score:
                    merged[key] = document
        return sorted(
            merged.values(), key=lambda document: document.score, reverse=True
        )

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

    async def filter_documents(
        self, session: aiohttp.ClientSession, documents: list
    ) -> list:
        """
        Filter documents by checking for relevance

        :param search_results: results/hits coming from search index
        :return: filtered list of documents
        """
        if settings.RAG_RELEVANCE_CHECK:
            documents = await self.check_documents_relevance(
                session, str(self.rag_request.search_term), documents
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

    async def get_no_answer_response(
            self,
            session: aiohttp.ClientSession,
            language_service: LanguageService,
            documents: list
        ) -> RagResponse:
        """
        Generate response that no answer has been found
        """
        answer = Messages.NO_ANSWER + (
                Messages.RELEVANT_PAGES if any(document.include_in_answer for document in documents) else ""
        )
        return RagResponse(
                documents,
                self.rag_request,
                await language_service.translate_message(
                    "en", self.language, answer, session=session
                ),
            )

    def format_rag_prompt(self, documents: list) -> str:
        """
        Generate RAG prompt including context
        """
        return Prompts.RAG.format(
            settings.INTEGREAT_REGIONS[self.region]["name"],
            self.language,
            self.rag_request.search_term,
            self.format_context(documents)
        )

    async def answer_valid(
        self,
        session: aiohttp.ClientSession,
        answer: str,
        documents: list[Document],
    ) -> bool:
        """
        Check if a given answer is valid
        """
        if not settings.RAG_FACT_CHECK:
            return True
        check = await self.llm_api.simple_prompt(
            session,
            Prompts.FACT_CHECK.format(answer, self.format_context(documents)),
        )
        if check.lower().startswith('not valid'):
            LOGGER.info(
                "Answer not valid. Question: %s\nAnswer: %s\nReason: %s",
                self.rag_request.search_term,
                answer,
                check
            )
        return answer != "" and check.lower().startswith("valid")

    async def extract_answer(self) -> RagResponse:
        """
        Search for pages that are related to the question and create
        answer that summarizes the content of found pages.

        return: a dict containing a response and sources
        """
        language_service = LanguageService()

        async with aiohttp.ClientSession() as session:
            if response := await self.skip_rag_answer(session, language_service):
                return response
            documents = await self.get_documents(session)
            rag_documents = (
                [document for document in documents if document.include_in_answer]
                [:settings.RAG_MAX_PAGES]
            )
            if not rag_documents:
                LOGGER.info("No documents found for : %s", self.rag_request.search_term)
                return await self.get_no_answer_response(session, language_service, documents)
            retries = 0
            while True:
                retries += 1
                answer = await self.llm_api.simple_prompt(
                    session, self.format_rag_prompt(rag_documents)
                )
                if await self.answer_valid(session, answer, rag_documents):
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
                return await self.get_no_answer_response(session, language_service, documents)
            if self.shallow_search:
                answer = await language_service.translate_message(
                    "en",
                    self.language,
                    Messages.SHALLOW_SEARCH.format(self.rag_request.search_term),
                    True,
                    session=session,
                ) + answer
            return RagResponse(documents, self.rag_request, answer)

    async def check_documents_relevance(
        self,
        session: aiohttp.ClientSession,
        question: str,
        search_results: list,
    ) -> list:
        """
        Check if the retrieved documents are relevant for answering the question

        param question: a message/question from a user
        param content: a page content that could be relevant for answering the question
        return: list of documents with include_in_answer set
        """
        tasks = []
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
