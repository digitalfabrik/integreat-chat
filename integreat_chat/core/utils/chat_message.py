"""
base request class
"""

import hashlib
import logging
from typing import TYPE_CHECKING

import aiohttp

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
        self.likely_message_language: str | None = None
        self.translated_message: str | None = None
        self.use_language: str | None = None

    async def prepare(self, session: aiohttp.ClientSession) -> None:
        """
        Detect language and translate the message into a supported language if needed.
        Must be awaited before accessing language/translation attributes.
        """
        if self.integreat_request.skip_language_detection:
            self.likely_message_language = self.integreat_request.gui_language
        else:
            try:
                self.likely_message_language = (
                    await self.integreat_request.language_service.classify_language(
                        self.original_message, session=session
                    )
                )
            except ValueError:
                LOGGER.info("Assuming GUI language")
                self.likely_message_language = self.integreat_request.gui_language

        if self.likely_message_language not in self.integreat_request.supported_languages:
            self.use_language = self.integreat_request.fallback_language
            self.translated_message = (
                await self.integreat_request.language_service.translate_message(
                    self.likely_message_language,
                    self.integreat_request.fallback_language,
                    self.original_message,
                    session=session,
                )
            )
        else:
            self.use_language = self.likely_message_language
            self.translated_message = self.original_message

    def as_dict(self) -> dict:
        """
        Return dict usable for API responses
        """
        return {
            "content": self.translated_message,
            "role": self.role
        }
