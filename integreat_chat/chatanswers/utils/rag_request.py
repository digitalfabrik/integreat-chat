"""
Message for processing a user message / RAG request
"""

import logging

from django.conf import settings

from integreat_chat.core.utils.integreat_request import IntegreatRequest

LOGGER = logging.getLogger("django")


class RagRequest(IntegreatRequest):
    """
    Class that represents a chat user message
    """
    def __init__(self, data: dict, skip_language_detection: bool = False):
        """
        Set needed attributes for RAG request
        """
        self.supported_languages = settings.RAG_SUPPORTED_LANGUAGES
        self.fallback_language = settings.RAG_FALLBACK_LANGUAGE
        super().__init__(data, skip_language_detection)
        self.most_important_message_first = False
        self.search_term = None

    def as_dict(self) -> dict:
        """
        Return relevant data for RAG prompting as dictionary
        """
        return {
            "messages": [message.as_dict() for message in self.messages],
            "extracted_question": self.search_term,
            "rag_language": self.first_message.use_language,
            "gui_language": self.gui_language,
            "region": self.region,
        }
