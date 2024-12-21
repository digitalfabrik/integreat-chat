"""
Message for processing a user message / RAG request
"""
from django.conf import settings

from integreat_chat.translate.services.language import LanguageService
from integreat_chat.chatanswers.services.query_transformer import QueryTransformer

class RagRequest:
    """
    Class that represents a chat user message
    """

    def __init__(self, data):
        """
        Set up message
        """
        if "language" not in data or "region" not in data or "message" not in data:
            raise ValueError("Missing language, region or message attribute")
        self.gui_language = data["language"]
        self.original_message = data["message"]
        self.region = data["region"]
        self.language_service = LanguageService()
        self.likely_message_language = self.detect_message_language()
        self.rag_message = self.translate_message()

    def detect_message_language(self) -> str:
        """
        Detect language and decide which language to use for RAG
        """
        return self.language_service.classify_language(
            self.gui_language, self.original_message
        )

    def rag_language(self) -> str:
        """
        Select a language for RAG prompting
        """
        if self.likely_message_language not in settings.RAG_SUPPORTED_LANGUAGES:
            return settings.RAG_FALLBACK_LANGUAGE
        return self.likely_message_language

    def optimized_message(self) -> bool:
        """
        Optimize RAG message if required
        """
        query_transformer = QueryTransformer(self.original_message)
        if query_transformer.is_transformation_required():
            return query_transformer.transform_query()["modified_query"]
        return self.rag_message

    def translate_message(self) -> str:
        """
        If necessary, translate message into a supported RAG language.
        """
        if self.likely_message_language != self.rag_language:
            return self.language_service.translate_message(
                self.likely_message_language, self.rag_language, self.original_message
            )
        return self.original_message

    def __str__(self) -> str:
        """
        string representation returns the message prepared for prompting
        """
        if settings.RAG_QUERY_OPTIMIZATION:
            return self.optimized_message()
        return self.rag_message

    def __dict__(self) -> dict:
        """
        Return relevant data for RAG prompting as dictionary
        """
        return {
            "message": self.__str__(),
            "rag_language": self.rag_language(),
            "gui_language": self.gui_language,
            "region": self.region
        }
