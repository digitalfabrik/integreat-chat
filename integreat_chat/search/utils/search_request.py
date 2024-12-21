"""
Class for Search request messages
"""

from django.conf import settings

from integreat_chat.core.utils.integreat_request import IntegreatRequest


class SearchRequest(IntegreatRequest):
    """
    Representation for search request
    """
    def __init__(self, data):
        self.supported_languages = settings.SEARCH_EMBEDDING_MODEL_SUPPORTED_LANGUAGES
        self.fallback_language = settings.SEARCH_FALLBACK_LANGUAGE
        super().__init__(data)
