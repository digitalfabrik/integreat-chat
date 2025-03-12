"""
Setup and use of OpenSearch
"""
import hashlib
import time
import requests
from django.conf import settings
from langchain_text_splitters import HTMLHeaderTextSplitter
from integreat_chat.core.utils.integreat_cms import get_pages, get_parent_page_titles

class OpenSearch:
    """
    Class for searching and updating documents in OpenSearch
    """

    ingest_pipeline_name = "nlp-ingest-pipeline"
    search_pipeline_name = "nlp-search-pipeline"

    def __init__(
            self,
            base_url: str = "https://localhost:9200",
            user: str = "admin",
            password: str = "changeme",
        ) -> None:
        """
        OpenSearch service

        param base_url: URL to OpenSearch server
        param user: user to log in on OpenSearch server
        parm password: password to log in on OpenSearch server
        """
        self.base_url = base_url
        self.user = user
        self.password = password
        self.model_id = settings.SEARCH_OPENSEARCH_MODEL_ID
        self.model_group_id = settings.SEARCH_OPENSEARCH_MODEL_GROUP_ID

    def request(self, path: str, payload: dict, method: str = "GET") -> dict:
        """
        Wrapper around Requests to OpenSearch server

        param path: path appended to the OpenSearch base_url
        param payload: a OpenSearch request payload
        param method: a HTTP method
        """
        response = None
        headers = {'Content-type': 'application/json'}
        if method == "GET":
            response = requests.get(
                f'{self.base_url}{path}',
                auth=(self.user, self.password),
                json=payload,
                timeout=30,
                verify="/etc/opensearch/root-ca.pem",
                headers=headers,
            ).json()
        if method == "PUT":
            response = requests.put(
                f'{self.base_url}{path}',
                auth=(self.user, self.password),
                json=payload,
                timeout=30,
                verify="/etc/opensearch/root-ca.pem",
                headers=headers,
            ).json()
        if method == "POST":
            response = requests.post(
                f'{self.base_url}{path}',
                auth=(self.user, self.password),
                json=payload,
                timeout=30,
                verify="/etc/opensearch/root-ca.pem",
                headers=headers,
            ).json()
        if method == "DELETE":
            response = requests.delete(
                f'{self.base_url}{path}',
                auth=(self.user, self.password),
                json=payload,
                timeout=30,
                verify="/etc/opensearch/root-ca.pem",
                headers=headers,
            ).json()
        if response:
            return response
        raise NotImplementedError("HTTP Method not implemented")

    def reduce_search_result(
            self,
            response: dict,
            deduplicate : bool = False,
            max_results : int = settings.SEARCH_MAX_DOCUMENTS,
            min_score: int = settings.SEARCH_SCORE_THRESHOLD,
        ) -> dict:
        """
        Reduce the search result into a condensed dictionary. Skip duplicate URLs
        and low scores.

        param response: OpenSearch response dict
        param deduplicate: deduplicate results based on the URL
        param max_results: limit number of results to N documents
        param min_score: Minimum required score for a hit to be included in the result
        """
        result = []
        found_urls = []
        if "hits" not in response:
            raise ValueError("Missing hits in result")
        for document in response["hits"]["hits"]:
            if (
                (deduplicate and document["_source"]["url"] in found_urls)
                or document["_score"] < min_score
            ):
                continue
            result.append({
                "url": document["_source"]["url"],
                "title": document["_source"]["title"],
                "score": document["_score"],
                "chunk_text": document["_source"]["chunk_text"],
            })
            found_urls.append(document["_source"]["url"])
        return result[:max_results]

    def search(self, region_slug: str, language_slug: str, message: str) -> dict:
        """
        Search for message

        param region_slug: slug of an Integreat region
        param language_slug: slug of a language of a region
        param message: search string / message
        """
        payload = {
            "_source": {
                "exclude": [
                    "chunk_embedding"
                ]
            },
            "query": {
                "hybrid": {
                    "queries": [
                        {
                        "match": {
                            "title": {
                                "query": message
                            }
                        }
                        },
                        {
                        "match": {
                            "chunk_text": {
                                "query": message
                            }
                        }
                        },
                        {
                        "neural": {
                            "title_embedding": {
                                "query_text": message,
                                "model_id": self.model_id,
                                "k": 5
                            }
                        }
                        },
                        {
                        "neural": {
                            "chunk_embedding": {
                                "query_text": message,
                                "model_id": self.model_id,
                                "k": 5
                            }
                        }
                        }
                    ]
                }
            }
        }
        return self.request(
            f"/{region_slug}_{language_slug}/_search?"
            f"search_pipeline={self.search_pipeline_name}", payload, "GET"
        )

    def search_api(self, index: str, payload: dict) -> dict:
        """
        Wrapper for full API search
        """
        if not index:
            raise ValueError("No search index provided")
        return self.request(
            f"/{index}/_search?search_pipeline={self.search_pipeline_name}", payload, "GET"
        )

class OpenSearchSetup(OpenSearch):
    """
    Setup for OpenSearch

    https://opensearch.org/docs/latest/ml-commons-plugin/pretrained-models/
    https://opensearch.org/docs/latest/search-plugins/semantic-search/
    """
    def setup(self) -> str:
        """
        Prepare OpenSearch
        """
        self.basic_settings()
        group_id = self.create_model_group()
        if not group_id:
            raise ValueError("Unexpected OpenSearch response while creating model group")
        model_id = self.register_embedding_model(group_id)
        if not model_id:
            raise ValueError("Unexpected OpenSearch response while registering model")
        self.deploy_model(model_id)
        self.create_ingestion_pipeline(model_id)
        self.create_search_pipeline()
        return group_id, model_id

    def delete_model_group(self):
        """
        Delete previously created model group and model
        """
        self.request(f"/_plugins/_ml/models/{self.model_id}/_undeploy", {}, "POST")
        self.request(f"/_plugins/_ml/models/{self.model_id}", {}, "DELETE")
        self.request(f"/_plugins/_ml/model_groups/{self.model_group_id}", {}, "DELETE")

    def prepare_index(self, region_slug: str = "", language_slug: str = ""):
        """
        Prepare index with ingestion pipeline and fill with pages
        """
        if not region_slug or not language_slug:
            raise ValueError
        self.delete_index(f"{region_slug}_{language_slug}")
        self.create_index(f"{region_slug}_{language_slug}")
        self.index_pages(region_slug, language_slug)

    def basic_settings(self):
        """
        Basic OpenSearch node settings
        """
        payload = {
            "persistent": {
                "plugins.ml_commons.only_run_on_ml_node": "false",
                "plugins.ml_commons.model_access_control_enabled": "true",
                "plugins.ml_commons.native_memory_threshold": "99"
            }
        }
        self.request("/_cluster/settings", payload, "PUT")

    def create_model_group(self):
        """
        Create model group
        """
        payload = {
            "name": "integreat-chat-2025-01-31",
            "description": "Integreat Chat embedding models"
        }
        response = self.request("/_plugins/_ml/model_groups/_register", payload, "POST")
        if "model_group_id" in response:
            return response["model_group_id"]
        return False

    def register_embedding_model(self, model_group_id: str) -> str:
        """
        Register embedding model
        """
        payload = {
            "name": settings.OPENSEARCH_EMBEDDING_MODEL_NAME,
            "version": "1.0.1",
            "model_group_id": model_group_id,
            "model_format": "TORCH_SCRIPT"
        }
        register_response = self.request(
            "/_plugins/_ml/models/_register", payload, "POST"
        )
        if "task_id" in register_response:
            for n in range(0, 10):  # pylint: disable=W0612
                time.sleep(5)
                if "model_id" in (task_response := self.request(
                    f"/_plugins/_ml/tasks/{register_response['task_id']}", {}, "GET"
                )):
                    return task_response["model_id"]
        return False

    def deploy_model(self, model_id: str):
        """
        Register embedding model
        """
        if "task_id" in (response := self.request(
            f"/_plugins/_ml/models/{model_id}/_deploy", {}, "POST"
        )):
            return response["task_id"]
        return False

    def create_ingestion_pipeline(self, model_id: str):
        """
        Create ingestion pipeline
        """
        payload = {
            "description": "A text embedding pipeline",
            "processors": [
                {
                    "text_embedding": {
                        "model_id": model_id,
                        "field_map": {
                            "chunk_text": "chunk_embedding"
                        }
                    }
                },
                {
                    "text_embedding": {
                        "model_id": model_id,
                        "field_map": {
                        "title": "title_embedding"
                        }
                    }
                }
            ]
        }
        self.request(f"/_ingest/pipeline/{self.ingest_pipeline_name}", payload, "PUT")

    def create_search_pipeline(self):
        """
        Create index search pipeline
        """
        payload = {
            "description": "Post processor for hybrid search",
            "phase_results_processors": [
                {
                    "normalization-processor": {
                        "normalization": {
                            "technique": "min_max"
                        },
                        "combination": {
                            "technique": "arithmetic_mean",
                            "parameters": {
                                "weights": [
                                    0.15,  # title match
                                    0.2,   # content match
                                    0.15,  # title embedding
                                    0.5    # content embedding
                                ]
                            }
                        }
                    }
                }
            ]
        }
        self.request(f"/_search/pipeline/{self.search_pipeline_name}", payload, "PUT")

    def set_default_index_model(self, model_id):
        """
        Set default model for field

        https://opensearch.org/docs/latest/search-plugins/semantic-search/#setting-a-default-model-on-an-index-or-field
        """
        payload = {
            "request_processors": [
                {
                    "neural_query_enricher" : {
                        "default_model_id": model_id,
                    }
                }
            ]
        }
        self.request(f"/_search/pipeline/{self.ingest_pipeline_name}", payload, "PUT")

    def delete_index(self, index_slug: str) -> None:
        """
        Delete an index
        """
        return self.request(f"/{index_slug}", {}, "DELETE")

    def create_index(self, index_slug: str):
        """
        Createa index for region
        """
        payload = {
            "settings": {
                "index.knn": True,
                "default_pipeline": self.ingest_pipeline_name,
            },
            "mappings": {
                "properties": {
                "id": {
                    "type": "text"
                },
                "url": {
                    "type": "text"
                },
                "title": {
                    "type": "text"
                },
                "chunk_embedding": {
                    "type": "knn_vector",
                    "dimension": 384,
                    "method": {
                        "engine": "lucene",
                        "space_type": "l2",
                        "name": "hnsw",
                        "parameters": {}
                    }
                },
                "title_embedding": {
                    "type": "knn_vector",
                    "dimension": 384,
                    "method": {
                    "engine": "lucene",
                    "space_type": "l2",
                    "name": "hnsw",
                    "parameters": {}
                }
                },
                "chunk_text": {
                    "type": "text"
                }
                }
            }
        }
        return self.request(f"/{index_slug}", payload, "PUT")

    def index_pages(self, region_slug: str, language_slug: str):
        """
        Fill index with pages from region
        """
        known_hashes = []
        for page in get_pages(region_slug, language_slug):
            texts, paths = self.split_page(page)  # pylint: disable=W0612
            for chunk in texts:
                chunk_hash = hashlib.md5(chunk.encode(encoding="utf-8")).digest()
                if chunk_hash in known_hashes:
                    continue
                known_hashes.append(chunk_hash)
                payload = {
                    "chunk_text": chunk,
                    "id": page["id"],
                    "title": page["title"],
                    "parent_titles": self.get_parent_titles(region_slug, language_slug, page),
                    "url": f"https://{settings.INTEGREAT_APP_DOMAIN}{page['path']}",
                }
                self.request(f"/{region_slug}_{language_slug}/_doc/{page['id']}", payload, "PUT")

    def split_page(self, page):
        """
        split pages at headlines
        """
        if page["content"] == "":
            return [], []
        headers_to_split_on = [
            ("h1", "headline"),
            ("h2", "headline"),
        ]
        html_splitter = HTMLHeaderTextSplitter(
            headers_to_split_on=headers_to_split_on,
        )
        documents = html_splitter.split_text(page['content'])
        texts = []
        paths = []
        for doc in documents:
            texts.append(doc.page_content)
            paths.append({"source": page['path']})
        return texts, paths
    
    def get_parent_titles(self, region_slug: str, language_slug: str, page: dict):
        """
        Get parent headlines of a page and append them
        """
        page_path = page["path"]
        parent_titles = []
        for parent in get_parent_page_titles(region_slug, language_slug, page_path):
            parent_titles.append(parent["title"])
        
        return parent_titles