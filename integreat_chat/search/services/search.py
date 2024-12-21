"""
A service to search for documents
"""

import json
from urllib.request import urlopen
from urllib.parse import unquote, quote

from pymilvus import (
    connections,
    Collection,
)

from django.conf import settings

class SearchService:
    """
    Service class that enables searching for Integreat content
    """
    def __init__(self, region: str, language: str) -> None:
        self.language = self.choose_language(language)
        self.original_language = language
        self.region = region
        self.vdb_host = settings.VDB_HOST
        self.vdb_port = settings.VDB_PORT
        self.vdb_collection_name = f"collection_ig_{region}_{self.language}"

    def choose_language(self, language: str) -> str:
        """
        Check if the chosen languge is supported. If not, use the fallback language.
        """
        if language in settings.SEARCH_EMBEDDING_MODEL_SUPPORTED_LANGUAGES:
            return language
        return settings.SEARCH_FALLBACK_LANGUAGE

    def doc_details(self, results: dict, include_text: bool = False) -> list:
        """
        convert result into sources dict
        """
        sources = []
        for source in results:
            cms_page = self.fetch_page_from_cms(source.entity.get('source'), self.language)
            source_url = (source.entity.get('source') if
                self.language == self.original_language else
                unquote(cms_page["available_languages"][self.original_language]["path"])
            )
            if include_text:
                text = (cms_page["excerpt"]
                    if self.language == self.original_language else
                    self.fetch_page_from_cms(source_url, self.original_language)["excerpt"]
                )
                sources.append({
                    "source": source_url,
                    "text": text,
                    "found_chunk": source.entity.get('text'),
                    "score": source.distance
                })
            else:
                sources.append({
                    "source": source_url,
                    "score": source.distance
                })
        sources = sorted(sources, key=lambda x: x["score"])
        return sources

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
            question: str,
            limit_results: int = settings.SEARCH_MAX_DOCUMENTS,
            include_text: bool = False
        ) -> list:
        """
        Create summary answer for question
        """
        results = self.load_collection().search(
            data=[self.get_embeddings(question)],
            anns_field="vector",
            param={"metric_type": "L2", "params": {"nprobe": 10}},
            limit=limit_results,
            expr=None,
            consistency_level="Strong",
            output_fields=(["source", "text"] if include_text else ["source"])
        )[0]
        return self.doc_details(results, include_text)

    def deduplicate_pages(
            self,
            sources: list[dict],
            max_pages: int = settings.SEARCH_MAX_PAGES,
            max_score: int = settings.SEARCH_DISTANCE_THRESHOLD
        ):
        """
        Get N unique pages from the sources retrieved from the retriever
        """
        unique_sources = []
        for source in sources:
            if (source['source'] not in [source['source'] for source in unique_sources] and source["score"] <= max_score):
                unique_sources.append(source)
            if len(unique_sources) == max_pages:
                break
        return unique_sources

    def fetch_page_from_cms(self, page_url: str, language: str) -> dict:
        """
        get data from Integreat cms using the children endpoint
        """
        pages_url = (
            f"https://{settings.INTEGREAT_CMS_DOMAIN}/api/v3/{self.region}/"
            f"{language}/children/?url={page_url}&depth=0"
        )
        encoded_url = quote(pages_url, safe=':/=?&')
        response = urlopen(encoded_url)
        return json.loads(response.read())[0]
