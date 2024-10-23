"""
A service to search for documents
"""
from sentence_transformers import SentenceTransformer
from pymilvus import (
    connections,
    Collection,
)

from django.conf import settings


class SearchService:
    """
    Service class that enables searching for Integreat content
    """
    _instance = None

    @staticmethod
    def get_instance(region, language):
        if SearchService._instance is None:
            SearchService._instance = SearchService(region, language)
        return SearchService._instance

    def __init__(self, region, language):
        self.language = language
        self.vdb_host = settings.VDB_HOST
        self.vdb_port = settings.VDB_PORT
        self.vdb_collection = f"collection_ig_{region}_{language}"

    def doc_details(self, results, include_text):
        """
        convert result into sources dict
        """
        sources = []
        for source in results:
            if include_text:
                sources.append({
                    "source": source.entity.get('source'),
                    "text": source.entity.get('text'),
                    "score": source.distance
                })
            else:
                sources.append({
                    "source": source.entity.get('source'),
                    "score": source.distance
                })
        return sources

    def search_documents(self, question, include_text=False):
        """
        Create summary answer for question
        """

        connections.connect("default", host=self.vdb_host, port=self.vdb_port)

        search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
        embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        collection = Collection(self.vdb_collection)
        collection.load()

        sentences = [question]
        embeddings = embedding_model.encode(sentences)
        results = collection.search(
            data=embeddings,
            anns_field="vector",
            param=search_params,
            limit=settings.RAG_MAX_DOCUMENTS,
            expr=None,
            consistency_level="Strong",
            output_fields=(["source", "text"] if include_text else ["source"])
        )[0]
        return {
            "documents": self.doc_details(results, include_text)
        }
