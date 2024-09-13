from django.http import JsonResponse
from .services.answer_service import AnswerService
from django.views.decorators.csrf import csrf_exempt
import json
from django.conf import settings

@csrf_exempt
def extract_answer(request):
    """
    Extract an answer for a user query from Integreat content. Expects a JSON body with message
    and language attributes
    """
    answer = None
    if request.method in ('POST') and request.META.get('CONTENT_TYPE').lower() == 'application/json':
        data = json.loads(request.body)
        question = data["message"]
        language = data["language"]
        print(f"Message ({language}): {message}", file=sys.stderr)
        answer = settings.ANSWER_SERVICE.extract_answer(question)
        print(f"Answer: {answer}", file=sys.stderr)
    return JsonResponse({"answer": answer})