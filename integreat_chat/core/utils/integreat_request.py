"""
base request class
"""
import logging
from django.utils.functional import cached_property

from integreat_chat.translate.services.language import LanguageService
from integreat_chat.translate.static.language_code_map import LANGUAGE_MAP

from ..static.region_language_map import REGION_LANGUAGE_MAP


LOGGER = logging.getLogger('django')


class IntegreatRequest:
    """
    base request class. Classes inheriting this class have to implement
    their own __init__() method which sets the supported languages by the
    used models and a fallback language.
    """
    def __init__(self, data: dict, skip_language_detection: bool = False) -> None:
        self.parse_arguments(data)
        self.language_service = LanguageService()
        self.skip_language_detection = skip_language_detection
        self.supported_languages = (
            None if not hasattr(self, "supported_languages") else self.supported_languages
        )
        self.fallback_language = (
            None if not hasattr(self, "fallback_language") else self.fallback_language
        )
        if self.supported_languages is None or self.fallback_language is None:
            raise ValueError("supported_languages or fallback_language has not been set.")

    def parse_arguments(self, data: dict) -> None:
        """
        Parse arguments from HTTP request body
        """
        if "language" not in data or "region" not in data or "message" not in data:
            raise ValueError("Missing language, region or message attribute")
        self.original_message = data["message"]
        self.region = data["region"]
        self.gui_language = (
            REGION_LANGUAGE_MAP[self.region][data["language"]]
            if self.region in REGION_LANGUAGE_MAP
            and data["language"] in REGION_LANGUAGE_MAP[self.region]
            else data["language"]
        )

    @cached_property
    def likely_message_language(self) -> str:
        """
        Detect language and decide which language to use for RAG
        """
        if self.skip_language_detection:
            return self.gui_language
        return self.language_service.classify_language(self.original_message)

    @cached_property
    def translated_message(self) -> str:
        """
        If necessary, translate message into GUI language
        """
        if self.likely_message_language not in self.supported_languages:
            if self.likely_message_language not in LANGUAGE_MAP:
                raise ValueError(
                    f"Unsupported translation language: {self.likely_message_language}"
                )
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
