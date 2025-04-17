"""
base request class
"""

import hashlib
import logging
from typing import TYPE_CHECKING

from django.utils.functional import cached_property
if TYPE_CHECKING:
    from .integreat_request import IntegreatRequest

LOGGER = logging.getLogger('django')


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
        self.hash = hashlib.sha256(self.original_message.encode("utf-8")).hexdigest()
        warm_cache = self.translated_message  # pylint: disable=unused-variable

    @property
    def likely_message_language(self) -> str:
        """
        Detect language and decide which language to use for RAG
        """
        if self.integreat_request.skip_language_detection:
            return self.integreat_request.gui_language
        try:
            return self.integreat_request.language_service.classify_language(self.original_message)
        except ValueError:
            LOGGER.info("Assuming GUI language")
            return self.integreat_request.gui_language

    @cached_property
    def translated_message(self) -> str:
        """
        If necessary, translate message into a message supported by the used
        Search- or Answer-Services.
        """
        if self.likely_message_language not in self.integreat_request.supported_languages:
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
        """
        Return dict usable for API responses
        """
        return {
            "content": self.translated_message,
            "role": self.role
        }
