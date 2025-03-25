"""
base request class
"""

from typing import TYPE_CHECKING

from django.utils.functional import cached_property
from integreat_chat.translate.static.language_code_map import LANGUAGE_MAP
if TYPE_CHECKING:
    from .integreat_request import IntegreatRequest

class ChatMessage:
    """
    Class for handling messages
    """
    def __init__(  # pylint: disable=too-many-arguments
            self,
            message: dict,
            integreat_request: "IntegreatRequest",
        ):
        self.original_message = message["content"]
        self.role = message["role"]
        self.integreat_request = integreat_request

    @cached_property
    def likely_message_language(self) -> str:
        """
        Detect language and decide which language to use for RAG
        """
        if self.integreat_request.skip_language_detection:
            return self.integreat_request.gui_language
        return self.integreat_request.language_service.classify_language(self.original_message)

    @cached_property
    def translated_message(self) -> str:
        """
        If necessary, translate message into GUI language
        """
        if self.likely_message_language not in self.integreat_request.supported_languages:
            if self.likely_message_language not in LANGUAGE_MAP:
                raise ValueError(
                    f"Unsupported translation language: {self.likely_message_language}"
                )
            return self.integreat_request.language_service.translate_message(
                self.likely_message_language,
                self.integreat_request.fallback_language,
                self.original_message
            )
        return self.original_message

    @property
    def use_language(self) -> str:
        """
        Select a language for RAG prompting
        """
        if self.likely_message_language not in self.integreat_request.supported_languages:
            return self.integreat_request.fallback_language
        return self.likely_message_language

    def as_dict(self) -> dict:
        return {
            "content": self.original_message,
            "role": self.role
        }
