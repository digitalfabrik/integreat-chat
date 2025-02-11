"""
Views for indexing and searching documents
"""
import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .services.search import SearchService
from .services.opensearch import OpenSearch
from .utils.search_request import SearchRequest

@csrf_exempt
def search_documents(request):
    """
    Search for documents related to the question. If the message is in the wrong language,
    first translate it to the GUI language. As we are only searching for similar documents,
    this should be fine, even if the translation is not very good.
    """
    result = {}
    if (
        request.method in ("POST")
        and request.META.get("CONTENT_TYPE").lower() == "application/json"
    ):
        try:
            search_request = SearchRequest(json.loads(request.body))
            search_service = SearchService(search_request, True)
            result = search_service.search_documents(include_text=True).as_dict()
        except ValueError as exc:
            result = {"status": "error", "message": str(exc)}
    return JsonResponse(result)

@csrf_exempt
def search_opensearch(request, region_slug, language_slug):
    """
    Search for documents related to the question. If the message is in the wrong language,
    first translate it to the GUI language. As we are only searching for similar documents,
    this should be fine, even if the translation is not very good.
    """
    result = {}
    if (
        request.method in ("GET")
        and request.META.get("CONTENT_TYPE").lower() == "application/json"
    ):
        opensearch = OpenSearch(password=settings.OPENSEARCH_PASSWORD)
        result = opensearch.search_api(
            f"{region_slug}_{language_slug}",
            json.loads(request.body)
        )
    return JsonResponse(result)
