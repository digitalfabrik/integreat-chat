"""
A service to search for documents
"""
from pymilvus import (
    connections,
    Collection,
)

from django.conf import settings

from ..utils.search_request import SearchRequest
from ..utils.search_response import SearchResponse, Document

class SearchService:
    """
    Service class that enables searching for Integreat content
    """
    def __init__(self, search_request: SearchRequest, deduplicate_results: bool) -> None:
        self.search_request = search_request
        self.language = search_request.use_language
        self.original_language = search_request.gui_language
        self.region = search_request.region
        self.vdb_host = settings.VDB_HOST
        self.vdb_port = settings.VDB_PORT
        self.deduplicate_results = deduplicate_results
        self.vdb_collection_name = f"collection_ig_{self.region}_{self.language}"

    def get_embeddings(self, question: str):
        """
        Get embedding for question string
        """
        return settings.SEARCH_EMBEDDING_MODEL.embed_query(question)

    def load_collection(self) -> Collection:
        """
        Connect to Milvus and load collection
        """
        connections.connect("default", host=self.vdb_host, port=self.vdb_port)
        collection = Collection(self.vdb_collection_name)
        collection.load()
        return collection

    def search_documents(
            self,
            limit_results: int = settings.SEARCH_MAX_DOCUMENTS,
            include_text: bool = False
        ) -> list:
        """
        Create summary answer for question
        """
        question = self.search_request.translated_message
        results = self.load_collection().search(
            data=[self.get_embeddings(question)],
            anns_field="vector",
            param={"metric_type": "L2", "params": {"nprobe": 10}},
            limit=limit_results,
            expr=None,
            consistency_level="Strong",
            output_fields=(["source", "text"] if include_text else ["source"])
        )[0]
        results = sorted(results, key=lambda x: x.distance)
        documents = []
        for result in results:
            documents.append(Document(
                result.entity.get('source'),
                result.entity.get('text'),
                result.distance,
                include_text,
                self.search_request.gui_language
            ))
        if self.deduplicate_results:
            results = self.deduplicate_pages(documents)
        return SearchResponse(self.search_request, documents)

    def deduplicate_pages(
            self,
            documents: list[Document],
            max_pages: int = settings.SEARCH_MAX_PAGES,
            max_score: int = settings.SEARCH_DISTANCE_THRESHOLD
        ):
        """
        Get N unique pages from the sources retrieved from the retriever
        """
        unique_sources = []
        for document in documents:
            if (
                document.chunk_source_path not in [
                    source.chunk_source_path for source in unique_sources
                ]
                and document.score <= max_score
            ):
                unique_sources.append(document)
            if len(unique_sources) == max_pages:
                break
        return unique_sources
