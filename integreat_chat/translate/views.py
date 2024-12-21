
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from integreat_chat.translate.services.language import LanguageService

LOGGER = logging.getLogger("django")

@csrf_exempt
def translate_message(request):
    """
    Translate a message from a source into a target language
    """
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
            result = {
                "translation": language_service.translate_message(
                    data["source_language"], data["target_language"], data["message"]
                ),
                "target_language": data["target_language"],
                "status": "success",
            }
    return JsonResponse(result)
