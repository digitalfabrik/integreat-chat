"""
Utility functions
"""
import json
from urllib.request import urlopen
from urllib.parse import quote

from django.conf import settings
from integreat_chat.chatanswers.services.answer_service import AnswerService
from integreat_chat.chatanswers.services.language import LanguageService


def translate_source_path(path: str, wanted_language: str) -> str:
    """
    Get the page path for a specified language
    """
    region = path.split("/")[1]
    cur_language = path.split("/")[2]
    pages_url = (
        f"https://{settings.INTEGREAT_CMS_DOMAIN}/api/v3/{region}/"
        f"{cur_language}/children/?url={path}&depth=0"
    )
    encoded_url = quote(pages_url, safe=':/=?&')
    response = urlopen(encoded_url)
    return json.loads(response.read())[0]["available_languages"][wanted_language]["path"]

def answer_generation(
        data: dict,
        language_service: LanguageService,
        message: str
    ) -> dict:
    """
    Generate request response for message

    param data: request body
    param language_service: Service class for translations etc
    param message: original or trans
    """
    rag_language = (
        data["language"] if data["language"] in settings.RAG_SUPPORTED_LANGUAGES
        else settings.RAG_FALLBACK_LANGUAGE
    )
    answer_service = AnswerService(data["region"], rag_language)
    if answer_service.needs_answer(data["message"]):
        if settings.RAG_QUERY_OPTIMIZATION:
            message = answer_service.optimize_query_for_retrieval(message)
        result = answer_service.extract_answer(message)
        if data["language"] not in settings.RAG_SUPPORTED_LANGUAGES:
            result["answer"] = language_service.translate_message(
                        settings.RAG_FALLBACK_LANGUAGE,
                        data["language"],
                        result["answer"]
                    )
            old_sources = result["sources"]
            result["sources"] = []
            for source in old_sources:
                result["sources"].append(translate_source_path(source, data["language"]))
        result["status"] = "success"
        result["message"] = message
    else:
        result["status"] = "not a question"
    return result

def language_transformation(
        language_service: LanguageService,
        data: dict
    ) -> str:
    """
    Translate incoming message into chosen front end language. Fall back to fallback
    languge if the GUI language is not supported by the LLM.
    """
    detected_language = language_service.classify_language(
        data["language"], data["message"]) != data["language"]

    if (
        detected_language == data["language"] and
        detected_language in settings.RAG_SUPPORTED_LANGUAGES
    ):
        return data["message"]

    target_language = (
        detected_language if detected_language in settings.RAG_SUPPORTED_LANGUAGES
        else settings.RAG_FALLBACK_LANGUAGE
    )
    return language_service.translate_message(
                detected_language,
                target_language,
                data["message"]
            )
