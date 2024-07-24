from django.http import JsonResponse
from .services.answer_service import AnswerService

def extract_answer(request):
    """
    Extract an answer for a user query from Integreat content. Expects a JSON body with message
    and language attributes
    """
    if request.method in ('POST') and request.META.get('CONTENT_TYPE').lower() == 'application/json':
        data = json.loads(request.body)
        question = data["message"]
        language = data["language"]
        answer_service = AnswerService(language)
        answer = answer_service.extract_answer(question)

    # keyword extraction code goes here

    return JsonResponse({"answer":[answer]})
