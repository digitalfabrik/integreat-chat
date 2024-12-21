"""
Retrieving matching documents for question an create summary text
"""
import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
# pylint: disable=no-name-in-module
from langchain_community.llms import Ollama

from django.conf import settings

from integreat_chat.search.services.search import SearchService
from integreat_chat.search.utils.search_request import SearchRequest
from integreat_chat.translate.services.language import LanguageService

from ..static.prompts import Prompts
from ..static.messages import Messages
from ..utils.rag_response import RagResponse
from ..utils.rag_request import RagRequest

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
        self.llm = self.load_llm(self.llm_model_name)

    def load_llm(self, llm_model_name: str) -> Ollama:
        """
        Prepare Ollama LLM

        param llm_model_name: name of an LLM model that can be pulled from Ollama
        return: Ollama model
        """
        return Ollama(model=llm_model_name, base_url=settings.OLLAMA_BASE_PATH)

    def needs_answer(self, message: str) -> bool:
        """
        Check if a chat message is a question

        param message: a user message
        return: indication if the message needs an answer
        """
        prompt = PromptTemplate.from_template(Prompts.CHECK_QUESTION)
        chain = prompt | self.llm | StrOutputParser()
        answer = chain.invoke({"message": message})
        if answer.startswith("Yes"):
            return True
        return False

    def get_documents(self) -> list:
        """
        Retrieve documents for RAG
        """
        search_request = SearchRequest({
            "message": self.rag_request.original_message,
            "language": self.rag_request.use_language,
            "region": self.rag_request.region
        })
        search = SearchService(search_request, deduplicate_results=False)
        search_results = search.search_documents(
            settings.RAG_MAX_PAGES,
            include_text=True,
        )
        search_results = search.deduplicate_pages(
            search_results,
            settings.RAG_MAX_PAGES,
            max_score=settings.RAG_DISTANCE_THRESHOLD
        )
        LOGGER.debug("Number of retrieved documents: %i", len(search_results))
        if settings.RAG_RELEVANCE_CHECK:
            search_results = [result for result in search_results if self.check_document_relevance(
                str(self.rag_request), result['text']
            )]
        LOGGER.debug("Number of documents after relevance check: %i", len(search_results))
        return search_results

    def extract_answer(self) -> RagResponse:
        """
        Create summary answer for question

        param question: a question or statement of need
        return: a dict containing a response and sources
        """
        question = str(self.rag_request)
        documents = self.get_documents()

        context = "\n".join(
            [result['text'] for result in documents]
        )[:settings.RAG_CONTEXT_MAX_LENGTH]
        if not documents:
            language_service = LanguageService()
            return RagResponse(
                self.rag_request,
                language_service.translate_message(
                    "en", self.language,
                    Messages.NO_ANSWER
                ),
                documents
            )
        prompt = PromptTemplate.from_template(Prompts.RAG)
        chain = prompt | self.llm | StrOutputParser()
        answer = chain.invoke({"language": self.language, "context": context, "question": question})
        LOGGER.debug("Question: %s\nAnswer: %s", question, answer)
        return RagResponse(self.rag_request, answer, documents)

    def check_document_relevance(self, question: str, content: str) -> bool:
        """
        Check if the retrieved documents are relevant for answering the question

        param question: a message/question from a user
        param content: a page content that could be relevant for answering the question
        return: bool that indicates if the page is relevant for the question
        """
        grade_prompt = PromptTemplate.from_template(Prompts.RELEVANCE_CHECK)
        chain = grade_prompt | self.llm | StrOutputParser()

        response = chain.invoke({"document": content, "question": question})
        response = response.strip().lower()
        return response.startswith("yes")
