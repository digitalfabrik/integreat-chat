"""
Django views
"""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from integreat_chat.chatanswers.services.answer import AnswerService

from .utils.rag_request import RagRequest

LOGGER = logging.getLogger("django")


@csrf_exempt
def extract_answer(request):
    """
    Extract an answer for a user query from Integreat content. Expects a JSON body with message
    and language attributes
    """
    rag_response = {"status": "error", "message": "unsupported method"}
    if (
        request.method in ("POST")
        and request.META.get("CONTENT_TYPE").lower() == "application/json"
    ):
        try:
            rag_request = RagRequest(json.loads(request.body))
            answer_service = AnswerService(rag_request)
            rag_response = answer_service.extract_answer().as_dict()
        except ValueError as exc:
            rag_response = {"status": "error", "message": str(exc)}
    return JsonResponse(rag_response)
