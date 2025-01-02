"""
base request class
"""
import logging
from django.utils.functional import cached_property

from integreat_chat.translate.services.language import LanguageService

LOGGER = logging.getLogger('django')


class IntegreatRequest:
    """
    base request class. Classes inheriting this class have to implement
    their own __init__() method which sets the supported languages by the
    used models and a fallback language.
    """
    def __init__(self, data):
        self.parse_arguments(data)
        self.language_service = LanguageService()
        self.supported_languages = (
            None if not hasattr(self, "supported_languages") else self.supported_languages
        )
        self.fallback_language = (
            None if not hasattr(self, "fallback_language") else self.fallback_language
        )
        if self.supported_languages is None or self.fallback_language is None:
            raise ValueError("supported_languages or fallback_language has not been set.")

    def parse_arguments(self, data):
        """
        Parse arguments from HTTP request body
        """
        if "language" not in data or "region" not in data or "message" not in data:
            raise ValueError("Missing language, region or message attribute")
        self.original_message = data["message"]
        self.gui_language = data["language"]
        self.region = data["region"]

    @cached_property
    def likely_message_language(self) -> str:
        """
        Detect language and decide which language to use for RAG
        """
        return self.language_service.classify_language(
            self.gui_language, self.original_message
        )

    @cached_property
    def translated_message(self) -> str:
        """
        If necessary, translate message into GUI language
        """
        if self.likely_message_language not in self.supported_languages:
            return self.language_service.translate_message(
                self.likely_message_language, self.fallback_language, self.original_message
            )
        return self.original_message

    @property
    def use_language(self) -> str:
        """
        Select a language for RAG prompting
        """
        if self.likely_message_language not in self.supported_languages:
            return self.fallback_language
        return self.likely_message_language
