"""
Message for processing a user message / RAG request
"""

import logging

from django.conf import settings
from django.utils.functional import cached_property

from integreat_chat.core.utils.integreat_request import IntegreatRequest
from integreat_chat.chatanswers.services.query_transformer import QueryTransformer

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

    @cached_property
    def optimized_message(self) -> bool:
        """
        Optimize RAG message if required
        """
        query_transformer = QueryTransformer(self.translated_message)
        LOGGER.debug("Checking if query needs optimization.")
        if query_transformer.is_transformation_required():
            LOGGER.debug("Optimizing user query.")
            return query_transformer.transform_query()["modified_query"]
        return self.translated_message

    def __str__(self) -> str:
        """
        string representation returns the message prepared for prompting
        """
        if settings.RAG_QUERY_OPTIMIZATION:
            return self.optimized_message
        return self.translated_message

    def as_dict(self) -> dict:
        """
        Return relevant data for RAG prompting as dictionary
        """
        return {
            "message": str(self),
            "rag_language": self.use_language,
            "gui_language": self.gui_language,
            "region": self.region,
        }
