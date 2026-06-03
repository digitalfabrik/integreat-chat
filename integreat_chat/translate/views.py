
import json
import logging

import aiohttp
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from integreat_chat.translate.services.language import LanguageService
from integreat_chat.core.utils.integreat_cms import async_get_region_languages

LOGGER = logging.getLogger("django")

@csrf_exempt
async def detect_language(request):
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
                "detected_language": await language_service.classify_language(data["message"]),
                "status": "success",
            }
    return JsonResponse(data=result)

@csrf_exempt
async def translate_message(request):
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
            result = {"status": "error", "reason": "Missing source_language, target_language or message attribute."}
        else:
            force_src_lang = "force_source_language" in data and data["force_source_language"]
            try:
                source_language = (
                    data["source_language"] if force_src_lang
                    else await language_service.classify_language(data["message"])
                )
                result = {
                    "translation": str(await language_service.translate_message(
                        source_language,
                        data["target_language"],
                        data["message"],
                        True
                    )),
                    "target_language": data["target_language"],
                    "status": "success",
                }
            except (TimeoutError, aiohttp.ClientError):
                LOGGER.error("LLM request failed in translate_message", exc_info=True)
                result = {"status": "error", "reason": "Translation service unavailable."}
                status = 503
            except ValueError as exc:
                LOGGER.info("Unsupported language in translate_message: %s", exc)
                result = {"status": "error", "reason": str(exc)}
                status = 422
            except KeyError as exc:
                LOGGER.error(exc)
                result = {
                    "status": "error",
                    "reason": str(exc)
                }
                status = 404
    return JsonResponse(data=result, status=status)

@csrf_exempt
async def message_to_region_languages(request):
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
                result = {"translations": [], "status": "success"}
                for language in await async_get_region_languages(data["region"]):
                    LOGGER.debug("translating to %s", language)
                    result["translations"].append({
                        "translation": str(await language_service.translate_message(
                            data["source_language"],
                            language,
                            data["message"],
                            True
                        )),
                        "language": language,
                    })
            except (TimeoutError, aiohttp.ClientError):
                LOGGER.error(
                    "LLM request failed in message_to_region_languages", exc_info=True
                )
                result = {"status": "error", "reason": "Translation service unavailable."}
                status = 503
            except ValueError as exc:
                LOGGER.info(
                    "Unsupported language in message_to_region_languages: %s", exc
                )
                result = {"status": "error", "reason": str(exc)}
                status = 422
            except KeyError as exc:
                result = {
                    "status": "error",
                    "reason": str(exc)
                }
                status = 404
    return JsonResponse(data=result, status=status)
