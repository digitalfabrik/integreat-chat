"""
A service to detect languages and translate messages
"""

import logging
import hashlib
import re

import aiohttp
from bs4 import BeautifulSoup

# pylint: disable=no-name-in-module

from django.conf import settings
from django.core.cache import cache
from integreat_chat.chatanswers.services.llmapi import (
    LlmApiClient, LlmMessage, LlmPrompt, LlmResponse
)

from ..static.prompts import Prompts
from ..static.language_classification_map import LANGUAGE_CLASSIFICATION_MAP
from integreat_chat.core.utils.integreat_cms import async_get_page

LOGGER = logging.getLogger("django")


class LanguageService:
    """
    Service class that enables searching for Integreat content
    """

    def __init__(self):
        """
        Initialize class
        """
        self.llm_api = LlmApiClient()

    def parse_language(self, response: str) -> str:
        """
        Parse String with language classification received from model
        """
        classfied_language = response
        stripped_language = classfied_language.split("-")[0]
        if stripped_language in LANGUAGE_CLASSIFICATION_MAP:
            return LANGUAGE_CLASSIFICATION_MAP[stripped_language]
        LOGGER.debug("Finished message language detection: %s", stripped_language)
        return stripped_language

    async def detect_language_of_string(
        self, session: aiohttp.ClientSession, message: str
    ) -> str:
        """
        Detect language for string

        :param session: shared aiohttp session for the LLM call
        :param message: a message string of unknown language
        :return: a BCP-47 tag
        """
        prompt = LlmPrompt(
            settings.LANGUAGE_CLASSIFICATION_MODEL,
            [
                LlmMessage(Prompts.LANGUAGE_CLASSIFICATION.format(message), role="user")
            ]
        )
        LOGGER.debug("Detecting message language")
        response = LlmResponse(await self.llm_api.chat_prompt(session, prompt))
        return self.parse_language(str(response))

    async def classify_language(
        self, message: str, session: aiohttp.ClientSession | None = None
    ) -> str:
        """
        Check if a message fits the estimated language.
        Return another language tag, if it does not fit.

        param message: the message of which the language should be detected
        param session: optional shared aiohttp session
        return: language slug of the detected language
        """
        if session is None:
            async with aiohttp.ClientSession() as owned_session:
                return await self.classify_language(message, owned_session)
        cache_key = hashlib.sha256(
            f"language-classification-{message}".encode("utf-8")
        ).hexdigest()
        classified_language = await cache.aget(cache_key, None)
        if classified_language is None:
            classified_language = await self.detect_language_of_string(session, message)
            if classified_language not in settings.TRANSLATION_MODEL_SUPPORTED_LANGUAGES:
                # try again once to avoid errors (some temperature exists)
                # Cache result nonetheless, we don't need to retry this again and again
                classified_language = await self.detect_language_of_string(session, message)
            await cache.aset(cache_key, classified_language)
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

    async def check_cache(
        self, source_language: str, target_language: str, message: str
    ) -> tuple[str, str | None]:
        """
        Check if message exists in translation cache. If not, return cache key
        """
        cache_key = hashlib.sha256(
            f"{source_language}-{target_language}-{message}".encode("utf-8")
        ).hexdigest()
        return cache_key, await cache.aget(cache_key, None)

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

    def sanitize_message(
        self, message: str, keep_html: bool = False
    ) -> tuple[str, dict[str, str]]:
        """
        Sanitize text. Remove HTML and replace links.

        :return: tuple of sanitized text and mapping of placeholder -> original url
        """
        if not keep_html:
            soup = BeautifulSoup(message, "lxml")
            message = soup.get_text()
        else:
            LOGGER.debug("Keep HTML in translation")
        urls = re.findall(r"(https?://[^\s\"\']+)", message)
        placeholders: dict[str, str] = {}
        for index, url in enumerate(urls):
            placeholder = f"_STR_URL_{index}_"
            message = message.replace(url, placeholder)
            placeholders[placeholder] = url
        return message, placeholders

    async def translate_link(
        self, session: aiohttp.ClientSession, page_url: str, target_language: str
    ) -> str:
        """
        Translate a link to target language from available CMS translations
        """
        if (not page_url.startswith(f"https://{settings.INTEGREAT_APP_DOMAIN}") and
            not page_url.startswith(f"http://{settings.INTEGREAT_APP_DOMAIN}")):
            LOGGER.debug(
                "Link %s does not seem to be a valid Integreat App URL, skipping translation",
                page_url
            )
            return page_url

        translations = (await async_get_page(session, page_url))["available_languages"]
        available_languages = list(translations.keys())
        if target_language in available_languages:
            translated_path = translations[target_language]["path"]
            translated_link = f"https://{settings.INTEGREAT_APP_DOMAIN}{translated_path}"
            LOGGER.debug("Translated link to %s in message: %s",
                         target_language, translated_link)
        else:
            LOGGER.debug(
                "No translation for %s in %s, using original link",
                page_url, target_language
            )
            translated_link = page_url

        return translated_link

    async def restore_links(
        self,
        session: aiohttp.ClientSession,
        translated_message: str,
        placeholders: dict[str, str],
        target_language: str,
    ) -> str:
        """
        Replace placeholders back to URLs after translation
        """
        if not placeholders:
            return translated_message
        for placeholder, url in placeholders.items():
            try:
                translated_url = await self.translate_link(session, url, target_language)
            except Exception:
                translated_url = url
                LOGGER.error("Could not translate URL: %s", url)
            translated_message = translated_message.replace(placeholder, translated_url)
        return translated_message

    async def translate_message_llm_wrapper(
        self,
        session: aiohttp.ClientSession,
        source_language: str,
        target_language: str,
        message: str,
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
            await self.llm_api.chat_prompt(session, prompt)
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

    async def translate_message(
            self,
            source_language: str,
            target_language: str,
            message: str,
            keep_html: bool = False,
            session: aiohttp.ClientSession | None = None,
    ) -> str:
        """
        Check if message is in translation cache. If not, translate. To prevent
        problems with URLs, replace them with placeholders.
        Do some sanity checks before translating.
        """
        if session is None:
            async with aiohttp.ClientSession() as owned_session:
                return await self.translate_message(
                    source_language,
                    target_language,
                    message,
                    keep_html,
                    owned_session,
                )
        self.check_language_support(source_language, target_language)
        if not self.translation_required(source_language, target_language, message):
            return message
        cache_key, translated_message = await self.check_cache(
            source_language, target_language, message
        )
        if translated_message is not None:
            return translated_message
        sanitized_message, placeholders = self.sanitize_message(message, keep_html=keep_html)
        translated_message = await self.translate_message_llm_wrapper(
            session,
            source_language,
            target_language,
            sanitized_message,
        )
        translated_message = await self.restore_links(
            session, translated_message, placeholders, target_language
        )
        await cache.aset(cache_key, translated_message)
        return translated_message

    async def opportunistic_translate(
        self,
        expected_language: str,
        message: str,
        session: aiohttp.ClientSession | None = None,
    ) -> str:
        """
        Translate if detected language does not fit the expected language
        """
        classified_language = await self.classify_language(message, session=session)
        return (
            message
            if classified_language == expected_language
            else await self.translate_message(
                classified_language, expected_language, message, session=session
            )
        )
