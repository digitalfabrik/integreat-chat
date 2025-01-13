"""
Retrieving matching documents for question an create summary text
"""
import logging

from django.conf import settings

from integreat_chat.search.services.search import SearchService
from integreat_chat.search.utils.search_request import SearchRequest
from integreat_chat.translate.services.language import LanguageService

from ..static.prompts import Prompts
from ..static.messages import Messages
from ..utils.rag_response import RagResponse
from ..utils.rag_request import RagRequest
from .litellm import LiteLLMClient

LOGGER = logging.getLogger('django')


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
        self.language = rag_request.use_language
        self.region = rag_request.region
        self.llm_model_name = settings.RAG_MODEL
        self.llm_api = LiteLLMClient(Prompts.RAG_SYSTEM_PROMPT, settings.RAG_MODEL)

    def needs_answer(self, message: str) -> bool:
        """
        Check if a chat message is a question

        param message: a user message
        return: indication if the message needs an answer
        """
        LOGGER.debug("Checking if message requires response.")
        answer = self.llm_api.simple_prompt(Prompts.CHECK_QUESTION.format(message))
        if answer.startswith("Yes"):
            LOGGER.debug("Message requires response.")
            return True
        LOGGER.debug("Message does not require response.")
        return False

    def get_documents(self) -> list:
        """
        Retrieve documents for RAG
        """
        search_request = SearchRequest({
            "message": self.rag_request.translated_message,
            "language": self.rag_request.use_language,
            "region": self.rag_request.region
        })
        search = SearchService(search_request, deduplicate_results=False)
        search_results = search.search_documents(
            settings.RAG_MAX_PAGES,
            include_text=True,
        ).documents
        search_results = search.deduplicate_pages(
            search_results,
            settings.RAG_MAX_PAGES,
            max_score=settings.RAG_DISTANCE_THRESHOLD
        )
        LOGGER.debug("Number of retrieved documents: %i", len(search_results))
        if settings.RAG_RELEVANCE_CHECK:
            search_results = [result for result in search_results if self.check_document_relevance(
                str(self.rag_request), result.content
            )]
        LOGGER.debug("Number of documents after relevance check: %i", len(search_results))
        return search_results

    def extract_answer(self) -> RagResponse:
        """
        Create summary answer for question

        return: a dict containing a response and sources
        """
        question = str(self.rag_request)
        LOGGER.debug("Retrieving documents.")
        documents = self.get_documents()
        LOGGER.debug("Retrieved documents.")

        context = "\n".join(
            [result.content for result in documents]
        )[:settings.RAG_CONTEXT_MAX_LENGTH]
        if not documents:
            language_service = LanguageService()
            return RagResponse(
                documents,
                self.rag_request,
                language_service.translate_message(
                    "en", self.language,
                    Messages.NO_ANSWER
                )
            )
        LOGGER.debug("Generating answer.")
        answer = self.llm_api.simple_prompt(Prompts.RAG.format(self.language, question, context))
        LOGGER.debug("Finished generating answer. Question: %s\nAnswer: %s", question, answer)
        return RagResponse(documents, self.rag_request, answer)

    def check_document_relevance(self, question: str, content: str) -> bool:
        """
        Check if the retrieved documents are relevant for answering the question

        param question: a message/question from a user
        param content: a page content that could be relevant for answering the question
        return: bool that indicates if the page is relevant for the question
        """
        response = (self.llm_api.simple_prompt(
            Prompts.RELEVANCE_CHECK.format(question, content)).strip().lower()
        )
        return response.startswith("yes")

    def detect_human_request(self) -> bool:
        """
        Check if the user requests to talk to a human counselor or is asking a question
        return: bool that indicates if the user requests a human or not
        """
        query = str(self.rag_request)
        LOGGER.debug("Checking if user requests human intervention")
        response = self.llm_api.simple_prompt(Prompts.HUMAN_REQUEST_CHECK.format(query))
        LOGGER.debug("Finished checking if user requests human. Response: %s", response)
        return response.lower().startswith("yes")

    def trigger_zammad_human_request(self):
        print("Human has been requested")
