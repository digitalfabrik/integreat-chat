"""
Django views
"""

import json
import logging

from integreat_chat.chatanswers.services.answer_service import AnswerService
from integreat_chat.chatanswers.services.language import LanguageService
from integreat_chat.chatanswers.services.search import SearchService

from .services.milvus import UpdateMilvus
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

LOGGER = logging.getLogger('django')

@csrf_exempt
def search_documents(request):
    """
    Search for documents related to the question. If the message is in the wrong language,
    first translate it to the GUI language. As we are only searching for similar documents,
    this should be fine, even if the translation is not very good.
    """
    result = None
    if request.method in ('POST') and request.META.get('CONTENT_TYPE').lower() == 'application/json':
        data = json.loads(request.body)
        language_service = LanguageService()
        search_service = SearchService(data["region"], data["language"])
        if language := language_service.classify_language(data["language"], data["message"]) == data["language"]:
            result = {
                "related_documents": search_service.search_documents(data["message"]),
                "search_term": data["message"]
            }
        else:
            translated_message = language_service.translate_message(
                language,
                data["language"],
                data["message"]
            )
            result = {
                "related_documents": search_service.search_documents(translated_message),
                "search_term": translated_message
            }
    return JsonResponse(result)

@csrf_exempt
def translate_message(request):
    """
    Translate a message from a source into a target language
    """
    result = None
    if request.method in ('POST') and request.META.get('CONTENT_TYPE').lower() == 'application/json':
        data = json.loads(request.body)
        language_service = LanguageService()

        result =  language_service.translate_message(
                    data["source_language"],
                    data["target_language"],
                    data["message"]
                )
    return JsonResponse(result)

@csrf_exempt
def extract_answer(request):
    """
    Extract an answer for a user query from Integreat content. Expects a JSON body with message
    and language attributes
    """
    result = None
    if request.method in ('POST') and request.META.get('CONTENT_TYPE').lower() == 'application/json':
        data = json.loads(request.body)
        question = data["message"]
        language = data["language"]
        region = data["region"]
        answer_service = AnswerService(region, language)
        result = { "answer": "" }
        if answer_service.needs_answer(question):
            result = answer_service.extract_answer(question)
    return JsonResponse(result)

@csrf_exempt
def update_vdb(request):
    """
    Extract an answer for a user query from Integreat content. Expects a JSON body with message
    and language attributes
    """
    if request.method in ('POST') and request.META.get('CONTENT_TYPE').lower() == 'application/json':
        data = json.loads(request.body)
        region = data["region"]
        language = data["language"]
        update_milvus = UpdateMilvus(region, language)
        pages = update_milvus.fetch_pages_from_cms()
        text_chunks = []
        for page in pages:
            text_chunks = text_chunks + update_milvus.split_page(page)
        update_milvus.create_embeddings(text_chunks)
    return JsonResponse({"status": "collection updated"})
