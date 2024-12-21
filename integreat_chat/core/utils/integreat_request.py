"""
base request class
"""

from integreat_chat.translate.services.language import LanguageService

class IntegreatRequest:
    """
    base request class. Classes inheriting this class have to implement
    their own prepare() method which sets the supported languages by the
    used models and a fallback language.
    """
    def __init__(self, data):
        self.parse_arguments(data)
        self.likely_message_language = self.detect_message_language()
        self.supported_languages = None
        self.fallback_language = None
        self.prepare()
        if self.supported_languages is None or self.fallback_language:
            raise ValueError("supported_languages or fallback_language has not been set.")
        self.translated_message = self.translate_message()

    def parse_arguments(self, data):
        """
        Parse arguments from HTTP request body
        """
        if "language" not in data or "region" not in data or "message" not in data:
            raise ValueError("Missing language, region or message attribute")
        self.original_message = data["message"]
        self.gui_language = data["language"]
        self.region = data["region"]

    def prepare(self):
        """
        Classes inheriting from this class need to implement this method and
        set the following attributes:
        - self.supported_languages
        - self.fallback_language
        """
        raise NotImplementedError("prepare method has to be implemented.")

    def detect_message_language(self) -> str:
        """
        Detect language and decide which language to use for RAG
        """
        language_service = LanguageService()
        return language_service.classify_language(
            self.gui_language, self.original_message
        )

    def translate_message(self) -> str:
        """
        If necessary, translate message into GUI language
        """
        language_service = LanguageService()
        if self.likely_message_language not in self.supported_languages:
            return language_service.translate_message(
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
