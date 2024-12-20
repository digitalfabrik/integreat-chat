"""
User message class
"""
from django.conf import settings

from integreat_chat.chatanswers.services.language import LanguageService
from integreat_chat.chatanswers.services.query_transformer import QueryTransformer

class RagMessage:
    """
    Class that represents a user message
    """

    def __init__(self, data):
        """
        Set up message
        """
        self.gui_language = data["language"]
        self.original_message = data["message"]
        self.region = data["region"]
        self.language_service = LanguageService()
        self.likely_message_language = None
        self.rag_message = None
        self.rag_language = None
        self.answer = None
        self.sources = []

    def detect_message_language(self) -> str:
        """
        Detect language and decide which language to use for RAG
        """
        self.likely_message_language = self.language_service.classify_language(
            self.gui_language, self.original_message
        )
        return self.likely_message_language

    def select_rag_language(self):
        """
        Select a language for RAG prompting
        """

    def optimize_query(self) -> bool:
        """
        Optimize message if enabled and required
        """
        query_transformer = QueryTransformer(self.original_message)
        if settings.RAG_QUERY_OPTIMIZATION and query_transformer.is_transformation_required():
            self.rag_message = query_transformer.transform_query()["modified_query"]
            return True
        self.rag_message = self.original_message
        return False

    def translate_language(self) -> str:
        """
        prepare message for RAG prompting. Optimize first, then translate.
        """

    def generate_answer(self):
        """
        Prompt LLM and generate answer
        """

    def generate_sources(self):
        """
        Add sources for citation
        """