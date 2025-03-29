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
        self.language = rag_request.first_message.use_language
        self.region = rag_request.region
        self.llm_model_name = settings.RAG_MODEL
        self.llm_api = LlmApiClient()

    def skip_rag_answer(self, language_service: LanguageService) -> str|bool:
        """
        Check if a chat message is a question

        :param message: a user message
        :return: answer message if no further processing is required, else False
        """
        if self.detect_request_human():
            message = Messages.TALK_TO_HUMAN
        else:
            prompt = LlmPrompt(
                settings.LANGUAGE_CLASSIFICATION_MODEL,
                [LlmMessage(Prompts.CHECK_QUESTION, role="system")] + self.rag_request.messages,
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
            False,
        )

    def get_documents(self) -> list:
        """
        Retrieve documents for RAG
        """
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
            include_text=True,
            min_score=settings.RAG_SCORE_THRESHOLD,
        ).documents
        LOGGER.debug("Number of retrieved documents: %i", len(search_results))
        if settings.RAG_RELEVANCE_CHECK:
            search_results = asyncio.run(self.check_documents_relevance(
                str(self.rag_request), search_results)
            )
            LOGGER.debug("Number of documents after relevance check: %i", len(search_results))
        return search_results[:settings.RAG_MAX_PAGES]

    def extract_answer(self) -> RagResponse:
        """
        Create summary answer for question

        return: a dict containing a response and sources
        """
        language_service = LanguageService()

        if response := self.skip_rag_answer(language_service):
            return response

        LOGGER.debug("Retrieving documents for: %s.", self.rag_request.search_term)
        documents = self.get_documents()
        LOGGER.debug("Retrieved %s documents.", len(documents))

        context = "\n---\n".join(
            [
                f"# {' > '.join(result.parent_titles + [result.title])}\n{result.content}"
                for result in documents
            ]
        )[: settings.RAG_CONTEXT_MAX_LENGTH]

        if not documents:
            return RagResponse(
                documents,
                self.rag_request,
                language_service.translate_message(
                    "en", self.language, Messages.NO_ANSWER
                ),
            )
        LOGGER.debug("Generating answer.")
        answer = self.llm_api.simple_prompt(
            Prompts.RAG.format(self.language, self.rag_request.search_term, context)
        )
        LOGGER.debug(
            "Finished generating answer. Question: %s\nAnswer: %s",
            self.rag_request.search_term,
            answer
        )
        return RagResponse(documents, self.rag_request, answer)

    async def check_documents_relevance(self, question: str, search_results: list) -> bool:
        """
        Check if the retrieved documents are relevant for answering the question

        param question: a message/question from a user
        param content: a page content that could be relevant for answering the question
        return: bool that indicates if the page is relevant for the question
        """
        sys_message = LlmMessage(Prompts.CHECK_SYSTEM_PROMPT, "system")
        tasks = []
        async with aiohttp.ClientSession() as session:
            for document in search_results:
                message = LlmMessage(Prompts.RELEVANCE_CHECK.format(question, document.content))
                tasks.append(
                    asyncio.create_task(self.llm_api.chat_prompt(
                        session,
                        LlmPrompt(settings.RAG_RELEVANCE_CHECK_MODEL, [sys_message, message])
                    )
                ))
            llmresponses = await asyncio.gather(*tasks)
        kept_documents = []
        for i, response in enumerate(llmresponses):
            llm_response = LlmResponse(response)
            if str(llm_response).lower().startswith("yes"):
                kept_documents.append(search_results[i])
        return kept_documents

    def detect_request_human(self) -> bool:
        """
        Check if the user requests to talk to a human counselor or is asking a question
        return: bool that indicates if the user requests a human or not
        """
        query = str(self.rag_request)
        LOGGER.debug("Checking if user requests human intervention")
        response = self.llm_api.simple_prompt(Prompts.HUMAN_REQUEST_CHECK.format(query))
        LOGGER.debug("Finished checking if user requests human. Response: %s", response)
        return response.lower().startswith("yes")
