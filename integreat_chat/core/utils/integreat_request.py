"""
base request class
"""
import logging
from django.conf import settings

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
        self.all_messages = self.parse_messages(data)
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
        parsed_messages = []
        for message in messages:
            try:
                parsed_messages.append(ChatMessage(
                    message,
                    self,
                    language_dection=(message["role"] == "user")
                ))
            except ValueError:
                LOGGER.error("Skipping message because language could not be classified.")
        return parsed_messages

    @property
    def last_user_messages(self) -> list:
        """
        Return a list of user messages limited by the 
        """
        return (
            [message for message in self.all_messages if message.role == "user"]
            [-(settings.REQUEST_MAX_MESSAGES):]
        )

    @property
    def last_messages(self) -> list:
        """
        Return a list of the last messages
        """
        return self.all_messages[-(settings.REQUEST_MAX_MESSAGES):]

    @property
    def first_user_message(self) -> ChatMessage|None:
        """
        Return first message from associated messages list
        """
        for message in self.all_messages:
            if message.role == "user":
                return message
        return None

    @property
    def last_user_message(self):
        """
        Return first message from associated messages list
        """
        return [message for message in self.all_messages if message.role == "user"][-1]
