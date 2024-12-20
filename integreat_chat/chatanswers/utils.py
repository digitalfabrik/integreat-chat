import json
from urllib.request import urlopen
from urllib.parse import quote

from django.conf import settings
from integreat_chat.chatanswers.services.language import LanguageService
from integreat_chat.chatanswers.services.answer_service import AnswerService
from integreat_chat.chatanswers.services.query_transformer import QueryTransformer


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


def generate_answer(data: dict) -> dict:
    """
    Generate answer to message
    """
    language_service = LanguageService()
    if data["language"] not in settings.RAG_SUPPORTED_LANGUAGES:
        rag_language = settings.RAG_FALLBACK_LANGUAGE
    else:
        rag_language = data["language"]
    if (
        message_language := language_service.classify_language(
            data["language"], data["message"]
        )
        != data["language"]
    ):
        message = language_service.translate_message(
            message_language, rag_language, data["message"]
        )
    else:
        message = data["message"]

    answer_service = AnswerService(data["region"], rag_language)
    if answer_service.needs_answer(data["message"]):
        if settings.RAG_QUERY_OPTIMIZATION:
            qtrans = QueryTransformer(message)
            if qtrans.is_transformation_required():
                message = qtrans.transform_query()["modified_query"]
        result = answer_service.extract_answer(message)
        if rag_language != data["language"]:
            result["answer"] = language_service.translate_message(
                rag_language, data["language"], result["answer"]
            )
            old_sources = result["sources"]
            result["sources"] = []
            for source in old_sources:
                result["sources"].append(
                    translate_source_path(source, data["language"])
                )
        result["status"] = "success"
        result["message"] = message
    else:
        result["status"] = "not a question"
    return result
