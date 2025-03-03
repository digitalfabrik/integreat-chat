"""
base request class
"""
from django.utils.functional import cached_property

from integreat_chat.translate.services.language import LanguageService
from integreat_chat.translate.static.language_code_map import LANGUAGE_MAP


class ChatMessage:
    """
    Class for handling messages
    """
    def __init__(  # pylint: disable=too-many-arguments
            self,
            message: dict,
            language_service: LanguageService,
            skip_language_detection: bool,
            gui_language: str,
            supported_languages: list[str],
            fallback_language = str
        ):
        self.original_message = message["content"]
        self.role = message["role"]
        self.language_service = language_service
        self.skip_language_detection = skip_language_detection
        self.gui_language = gui_language
        self.supported_languages = supported_languages
        self.fallback_language = fallback_language

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
