"""
A service to detect languages and translate messages
"""

import logging
import hashlib
import re

import asyncio
from bs4 import BeautifulSoup

# pylint: disable=no-name-in-module

from django.conf import settings
from django.core.cache import cache
from integreat_chat.chatanswers.services.llmapi import (
    LlmApiClient, LlmMessage, LlmPrompt, LlmResponse
)

from ..static.prompts import Prompts
from ..static.language_classification_map import LANGUAGE_CLASSIFICATION_MAP
from integreat_chat.core.utils.integreat_cms import get_page

LOGGER = logging.getLogger("django")


class LanguageService:
    """
    Service class that enables searching for Integreat content
    """

    def __init__(self):
        """ """
        self.llm_api = LlmApiClient()
        self.message = None
        self.placeholders = {}

    def parse_language(self, response: dict) -> str:
        """
        Parse String with language classification received from model
        """
        classfied_language = response["bcp47-tag"]
        stripped_language = classfied_language.split("-")[0]
        if stripped_language in LANGUAGE_CLASSIFICATION_MAP:
            return LANGUAGE_CLASSIFICATION_MAP[stripped_language]
        LOGGER.debug("Finished message language detection: %s", stripped_language)
        return stripped_language

    def detect_language_of_string(self, message: str) -> str:
        """
        Detect language for string

        :param message: a message string of unknown language
        :return: a BCP-47 tag
        """
        prompt = LlmPrompt(
            settings.LANGUAGE_CLASSIFICATION_MODEL,
            [
                LlmMessage(Prompts.LANGUAGE_CLASSIFICATION, role="system"),
                LlmMessage(message, role="user")
            ],
            json_schema = Prompts.LANGUAGE_CLASSIFICATION_SCHEMA
        )
        LOGGER.debug("Detecting message language")
        response = LlmResponse(asyncio.run(self.llm_api.chat_prompt_session_wrapper(prompt)))
        return self.parse_language(response.as_dict())

    def classify_language(self, message: str) -> str:
        """
        Check if a message fits the estimated language.
        Return another language tag, if it does not fit.

        param message: the message of which the language should be detected
        return: language slug of the detected language
        """
        cache_key = hashlib.sha256(
            f"language-classification-{message}".encode("utf-8")
        ).hexdigest()
        classified_language = cache.get(cache_key, None)
        if classified_language is None:
            classified_language = self.detect_language_of_string(message)
            if classified_language not in settings.TRANSLATION_MODEL_SUPPORTED_LANGUAGES:
                # try again once to avoid errors (some temperature exists)
                # Cache result nonetheless, we don't need to retry this again and again
                classified_language = self.detect_language_of_string(message)
            cache.set(cache_key, classified_language)
        if classified_language not in settings.TRANSLATION_MODEL_SUPPORTED_LANGUAGES:
            error_msg = f"Did not detect a supported language: {classified_language}"
            LOGGER.error(error_msg)
            raise ValueError(error_msg)
        return classified_language

    def is_numerical(self, message: str) -> bool:
        """
        Check if message is numerical

        param message: the message
        return: true if the message is only a number
        """
        return re.match(r"^[0-9\s+\.\,]*$", message)

    def check_cache(
        self, source_language: str, target_language: str, message: str
    ) -> tuple[str, str | None]:
        """
        Check if message exists in translation cache. If not, return cache key
        """
        cache_key = hashlib.sha256(
            f"{source_language}-{target_language}-{message}".encode("utf-8")
        ).hexdigest()
        return cache_key, cache.get(cache_key, None)

    def translation_required(
        self, source_language: str, target_language: str, message: str
    ) -> bool:
        """
        Check if a translation is (not) required.
        """
        if source_language == target_language:
            LOGGER.debug(
                "Skipping translation from %s to %s", source_language, target_language
            )
            return False
        if self.is_numerical(message):
            return False
        return True

    def sanitize_message(self) -> None:
        """
        Sanitize text. Remove HTML and replace links.
        """
        soup = BeautifulSoup(self.message, "lxml")
        self.message = soup.get_text()
        urls = re.findall(r"(https?://[^\s]+)", self.message)
        self.placeholders = {}
        for url in urls:
            placeholder = f"_STR_URL_{len(self.placeholders)}_"
            self.message = self.message.replace(url, placeholder)
            self.placeholders[placeholder] = url

    def translate_link(self, page_url: str, target_language: str) -> str:
        """
        Translate a link to target language from available CMS translations
        """
        LOGGER.debug("URL to translate: %s", page_url)
        if not page_url.startswith("https://") and not page_url.startswith("http://"):
            LOGGER.debug("Link %s does not seem to be a valid url/, skipping translation", page_url)
            return page_url
        
        translations = get_page(page_url)["available_languages"]
        available_languages = list(translations.keys())
        if target_language in available_languages:
            translated_path = translations[target_language]["path"]
            translated_link = f"https://{settings.INTEGREAT_APP_DOMAIN}{translated_path}"
        else:
            LOGGER.debug(
                "No translation for %s in %s, using original link",
                page_url, target_language
            )
            translated_link = page_url

        return translated_link

    def restore_links(self, translated_message: str, target_language: str) -> str:
        """
        Replace placeholders back to URLs after translation
        """
        for placeholder, url in self.placeholders.items():
            url = self.translate_link(url, target_language)
            LOGGER.debug("After translation, URL: %s", url)
            translated_message = translated_message.replace(placeholder, url)
            LOGGER.debug("Translated message: %s", translated_message)
        return translated_message

    def translate_message_llm_wrapper(
        self, source_language: str, target_language: str, message: str
    ) -> str:
        """
        Translate a string from source to target language (without sanity checks).
        """
        LOGGER.debug(
            "Starting translation from %s to %s", source_language, target_language
        )
        prompt = LlmPrompt(
            settings.TRANSLATION_MODEL,
            [
                LlmMessage(Prompts.TRANSLATE_PROMPT.format(
                    source_language,
                    target_language
                ), role="system"),
                LlmMessage(message, role="user")
            ],
        )
        translated_message = str(LlmResponse(
            asyncio.run(self.llm_api.chat_prompt_session_wrapper(prompt))
        ))
        LOGGER.debug(
            "Finished translation from %s to %s", source_language, target_language
        )
        return translated_message

    def check_language_support(self, source_language: str, target_language: str) -> None:
        """
        Check if source and target languages are supported. Raise error if not.
        """
        if source_language not in settings.TRANSLATION_MODEL_SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported source translation language: {source_language}"
            )
        if target_language not in settings.TRANSLATION_MODEL_SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported target translation language: {target_language}"
            )

    def translate_message(
        self, source_language: str, target_language: str, message: str
    ) -> str:
        """
        Check if message is in translation cache. If not, translate. To prevent
        problems with URLs, replace them with placeholders.
        Do some sanity checks before translating.
        """
        self.check_language_support(source_language, target_language)
        self.message = message
        if not self.translation_required(source_language, target_language, message):
            return message
        cache_key, translated_message = self.check_cache(
            source_language, target_language, message
        )
        if translated_message is not None:
            return translated_message
        self.sanitize_message()
        translated_message = self.translate_message_llm_wrapper(
            source_language,
            target_language,
            message
        )
        translated_message = self.restore_links(translated_message, target_language)
        cache.set(cache_key, translated_message)
        return translated_message

    def opportunistic_translate(self, expected_language: str, message: str) -> str:
        """
        Translate if detected language does not fit the expected language
        """
        classified_language = self.classify_language(message)
        return (
            message
            if classified_language == expected_language
            else self.translate_message(classified_language, expected_language, message)
        )
