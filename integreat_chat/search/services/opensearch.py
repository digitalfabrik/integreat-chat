"""
Setup and use of OpenSearch
"""

import hashlib
import time
from datetime import timedelta, datetime

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
        headers = {'Content-type': 'application/json'}
        return requests.request(
            method=method,
            url=f'{self.base_url}{path}',
            auth=(self.user, self.password),
            json=payload,
            timeout=30,
            verify="/etc/opensearch/root-ca.pem",
            headers=headers,
        ).json()

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
                "parent_titles": document["_source"]["parent_titles"],
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

    def get_indexed_page_ids(self, index: str) -> list:
        """
        Get all page IDs currently indexed

        :param index: index name/slug
        :return: a list of page IDs
        """
        payload = {"query": {"match_all": {}}}
        result = self.request(f"/{index}/_search?_source=id&size=10000", payload, "GET")
        if not ["hits"] in result:
            return []
        return [page["_source"]["id"] for page in result["hits"]["hits"]]

    def delete_document(self, index: str, page_id: int) -> int:
        """
        Delete all chunks from index for given Integreat CMS page ID.
        
        :param index: name of the OpenSearch index
        :param page_id: Integreat CMS page ID
        :return: number of deleted documents
        """
        payload = {
            "query": {
                "match": {
                    "id": page_id
                }
            }
        }
        return self.request(f"/{index}/_delete_by_query", payload, "POST")["deleted"]

    def index_chunk(self, index: str, chunk: str, page: dict, parent_title: str) -> None:
        """
        Index page chunk
        """
        chunk_hash = hashlib.md5(chunk.encode(encoding="utf-8")).hexdigest()
        if self.hash_in_index(index, chunk_hash):
            return
        payload = {
            "chunk_text": chunk,
            "id": page["id"],
            "title": page["title"],
            "parent_titles": parent_title,
            "url": f"https://{settings.INTEGREAT_APP_DOMAIN}{page['path']}",
            "md5sum": chunk_hash,
        }
        self.request(f"/{index}/_doc", payload, "POST")

    def hash_in_index(self, index: str, chunk_hash: str) -> bool:
        """
        Check if hash is already in index
        """
        payload = {
            "query": {
                "match": {
                    "md5sum": chunk_hash
                }
            }
        }
        return bool(self.request(f"/{index}/_search?_source=id", payload, "POST")["hits"]["hits"])

    def remove_deleted_pages(self, index: str, current_page_ids: list) -> None:
        """
        Remove all pages from index that no longer exist in the Integreat content
        """
        removal_counter = 0
        for indexed_page_id in self.get_indexed_page_ids(index):
            if indexed_page_id not in current_page_ids:
                removal_counter = removal_counter + 1
                self.delete_document(index, indexed_page_id)
        print(f"Removed {removal_counter} pages.")

    def update_or_insert_page_chunks(
            self,
            region_slug: str,
            language_slug: str,
            cms_pages: list,
            differential: bool,
        ) -> None:
        """
        Insert page text chunks into index. If the document changed, remove the chunks associated
        with the page and insert the new ones.

        :param region_slug: Slug of Integreat CMS region
        :param language_slug: Slug of Integreat CMS language
        :param cms_pages: Reponse of Integreat CMS pages endpoint
        :param differential: recreate index if false
        """
        update_counter = 0
        for page in cms_pages:
            updated = datetime.fromisoformat(page["last_updated"])
            if datetime.now(updated.tzinfo) - updated < timedelta(days=7) or not differential:
                update_counter = update_counter + 1
                self.delete_document(f"{region_slug}_{language_slug}", page["id"])
                texts, paths = self.split_page(page)  # pylint: disable=W0612
                parent_title = self.get_parent_titles(region_slug, language_slug, page)
                for chunk in texts:
                    self.index_chunk(f"{region_slug}_{language_slug}", chunk, page, parent_title)
        print(f"Updated {update_counter} pages.")

    def index_pages(self, region_slug: str, language_slug: str, differential: bool = True) -> None:
        """
        Update or fill index of region.

        :param region_slug: Integreat CMS region slug
        :param language_slug: Integreat CMS language slug
        :param differential: recreate (fill) index if false, update if true
        """
        cms_pages = get_pages(region_slug, language_slug)
        if differential:
            self.remove_deleted_pages(
                f"{region_slug}_{language_slug}",
                [page["id"] for page in cms_pages]
            )
        self.update_or_insert_page_chunks(region_slug, language_slug, cms_pages, differential)

    def split_page(self, page: dict):
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
                                    0.35,  # content match
                                    0.15,  # title embedding
                                    0.35   # content embedding
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
