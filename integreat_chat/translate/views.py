
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from integreat_chat.translate.services.language import LanguageService
from integreat_chat.core.utils.integreat_cms import get_region_languages

LOGGER = logging.getLogger("django")

@csrf_exempt
def detect_language(request):
    """
    Detect language of a provided message.
    """
    result = {}
    if (
        request.method in ("POST")
        and request.META.get("CONTENT_TYPE").lower() == "application/json"
    ):
        data = json.loads(request.body)
        language_service = LanguageService()
        if "message" not in data:
            result = {"status": "error"}
        else:
            result = {
                "detected_language": language_service.classify_language(data["message"]),
                "status": "success",
            }
    return JsonResponse(data=result)

@csrf_exempt
def translate_message(request):
    """
    Translate a message from a source into a target language
    """
    status = 200
    result = None
    if (
        request.method in ("POST")
        and request.META.get("CONTENT_TYPE").lower() == "application/json"
    ):
        data = json.loads(request.body)
        language_service = LanguageService()
        if (
            "source_language" not in data
            or "target_language" not in data
            or "message" not in data
        ):
            result = {"status": "error"}
        else:
            force_src_lang = "force_source_language" in data and data["force_source_language"]
            try:
                result = {
                    "translation": str(language_service.translate_message(
                        data["source_language"] if force_src_lang
                            else language_service.classify_language(data["message"]),
                        data["target_language"],
                        data["message"],
                        True
                    )),
                    "target_language": data["target_language"],
                    "status": "success",
                }
            except KeyError as exc:
                result = {
                    "status": "error",
                    "reason": str(exc)
                }
                status = 404
    return JsonResponse(data=result, status=status)

@csrf_exempt
def message_to_region_languages(request):
    """
    Translate a message from a source into a target language
    """
    status = 200
    result = None
    if (
        request.method in ("POST")
        and request.META.get("CONTENT_TYPE").lower() == "application/json"
    ):
        data = json.loads(request.body)
        language_service = LanguageService()
        if (
            "source_language" not in data
            or "region" not in data
            or "message" not in data
        ):
            result = {"status": "error"}
        else:
            try:
                result = {"translations":[], "status": "success"}
                for language in get_region_languages(data["region"]):
                    LOGGER.debug(f"translating to {language}")
                    result["translations"].append({
                        "translation": str(language_service.translate_message(
                            data["source_language"],
                            language,
                            data["message"],
                            True
                        ))
                    })
            except KeyError as exc:
                result = {
                    "status": "error",
                    "reason": str(exc)
                }
                status = 404
    return JsonResponse(data=result, status=status)
