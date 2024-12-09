"""
Django views
"""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from integreat_chat.chatanswers.services.answer_service import AnswerService
from integreat_chat.chatanswers.services.language import LanguageService
from integreat_chat.chatanswers.services.search import SearchService
from integreat_chat.chatanswers.services.query_transformer import QueryTransformer

from .services.milvus import UpdateMilvus
from .utils import translate_source_path

LOGGER = logging.getLogger("django")


@csrf_exempt
def search_documents(request):
    """
    Search for documents related to the question. If the message is in the wrong language,
    first translate it to the GUI language. As we are only searching for similar documents,
    this should be fine, even if the translation is not very good.
    """
    result = None
    if (
        request.method in ("POST")
        and request.META.get("CONTENT_TYPE").lower() == "application/json"
    ):
        data = json.loads(request.body)
        if "language" not in data or "message" not in data:
            result = {"status": "error"}
        else:
            search_service = SearchService(data["region"], data["language"])
            language_service = LanguageService()
            search_term = language_service.opportunistic_translate(
                search_service.language, data["message"]
            )

            result = {
                "related_documents": search_service.deduplicate_pages(
                    search_service.search_documents(
                        search_term,
                        include_text="include_text" in data and data["include_text"],
                    )
                ),
                "search_term": search_term,
                "status": "success",
            }
    return JsonResponse(result)


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


@csrf_exempt
def extract_answer(request):
    """
    Extract an answer for a user query from Integreat content. Expects a JSON body with message
    and language attributes
    """
    result = {}
    if (
        request.method in ("POST")
        and request.META.get("CONTENT_TYPE").lower() == "application/json"
    ):
        data = json.loads(request.body)
        if "language" not in data or "region" not in data or "message" not in data:
            result = {"status": "error"}
        else:
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
    return JsonResponse(result)


@csrf_exempt
def update_vdb(request):
    """
    Extract an answer for a user query from Integreat content. Expects a JSON body with message
    and language attributes
    """
    if (
        request.method in ("POST")
        and request.META.get("CONTENT_TYPE").lower() == "application/json"
    ):
        data = json.loads(request.body)
        region = data["region"]
        language = data["language"]
        update_milvus = UpdateMilvus(region, language)
        if not update_milvus.check_language_support(language):
            return JsonResponse(
                {
                    "status": "not supported languge",
                }
            )
        pages = update_milvus.fetch_pages_from_cms()
        texts = []
        paths = []
        for page in pages:
            add_texts, add_paths = update_milvus.split_page(page)
            texts = texts + add_texts
            paths = paths + add_paths
        texts, paths, num_dedups = update_milvus.deduplicate_documents(texts, paths)
        update_milvus.create_embeddings(texts, paths)
        return JsonResponse(
            {
                "status": "collection updated",
                "num_pages": len(pages),
                "num_documents": len(texts),
                "num_deduplicated_documents": num_dedups,
            }
        )
    return JsonResponse(
        {
            "status": "malformed request",
        }
    )
