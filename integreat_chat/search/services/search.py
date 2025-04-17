"""
A service to search for documents
"""
import aiohttp
from django.conf import settings

from .opensearch import OpenSearch
from ..utils.search_request import SearchRequest
from ..utils.search_response import SearchResponse, Document

class SearchService:
    """
    Service class that enables searching for Integreat content
    """
    def __init__(self, search_request: SearchRequest, deduplicate_results: bool) -> None:
        self.search_request = search_request
        self.os = OpenSearch(password=settings.OPENSEARCH_PASSWORD)
        self.deduplicate_results = deduplicate_results

    def search_documents(
            self,
            max_results: int = settings.SEARCH_MAX_DOCUMENTS,
            include_text: bool = False,
            min_score: int = settings.SEARCH_SCORE_THRESHOLD,
        ) -> SearchResponse:
        """
        Search for documents based on the text of the last message.

        param max_results: limit number of results to N documents
        param include_text: fetch full text of page from Integreat CMS
        param min_score: Minimum required score for a hit to be included in the result
        """
        results = self.os.reduce_search_result(
            response = self.os.search(
                self.search_request.region,
                self.search_request.last_message.use_language,
                self.search_request.last_message.translated_message
            ),
            deduplicate = self.deduplicate_results,
            max_results = max_results,
            min_score = min_score,
        )
        documents = []
        async with aiohttp.ClientSession() as session:
            for result in results:
                documents.append(Document.create(
                    result["url"],
                    result["chunk_text"],
                    result["score"],
                    result["parent_titles"],
                    include_text,
                    self.search_request.gui_language,
                    session
                ))
        return SearchResponse(self.search_request, documents)
