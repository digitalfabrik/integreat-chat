"""
Views for indexing and searching documents
"""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from integreat_chat.translate.services.language import LanguageService
from .services.search import SearchService
from .services.milvus import UpdateMilvus

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
