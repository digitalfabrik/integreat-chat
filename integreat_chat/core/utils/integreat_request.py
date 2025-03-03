"""
base request class
"""
import logging
from django.conf import settings
from django.utils.functional import cached_property

from integreat_chat.translate.services.language import LanguageService

from ..static.region_language_map import REGION_LANGUAGE_MAP
from .chat_message import ChatMessage


LOGGER = logging.getLogger('django')


class IntegreatRequest:
    """
    base request class. Classes inheriting this class have to implement
    their own __init__() method which sets the supported languages by the
    used models and a fallback language.
    """
    def __init__(self, data: dict, skip_language_detection: bool = False) -> None:
        self.parse_meta_information(data)
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
        self.parse_messages(data)
        self.most_important_message_first = True

    def parse_meta_information(self, data: dict) -> None:
        """
        Parse meta information from HTTP request body
        """
        if "language" not in data or "region" not in data:
            raise ValueError("Missing language or region attribute")
        if data["region"] not in settings.INTEGREAT_REGIONS:
            raise ValueError("Integreat region not enabled")
        self.region = data["region"]
        self.gui_language = (
            REGION_LANGUAGE_MAP[self.region][data["language"]]
            if self.region in REGION_LANGUAGE_MAP
            and data["language"] in REGION_LANGUAGE_MAP[self.region]
            else data["language"]
        )

    def parse_messages(self, data: dict) -> None:
        """
        Parse message(s) from HTTP request body
        """
        if "messages" not in data and "message" not in data:
            raise ValueError("No messages in request body")
        if "message" in data:
            messages = [{"content": data["message"], "role": "user"}]
        else:
            messages = data["messages"]
        self.messages = [
            ChatMessage(
                message,
                self.language_service,
                self.skip_language_detection,
                self.gui_language,
                self.supported_languages,
                self.fallback_language
            ) for message in messages
            if message["role"] != "system"
        ]

    @cached_property
    def translated_message(self) -> str:
        """
        Get translated last message
        """
        if self.most_important_message_first:
            return self.messages[0].translated_message
        return self.messages[-1].translated_message

    @property
    def use_language(self) -> str:
        """
        Get language to be used
        """
        if self.most_important_message_first:
            return self.messages[0].use_language
        return self.messages[-1].use_language

    @property
    def original_message(self) -> str:
        if self.most_important_message_first:
            return self.messages[0].original_message
        return self.messages[-1].original_message
