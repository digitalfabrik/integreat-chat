"""
responses to search request and document class
"""
from integreat_chat.chatanswers.utils.integreat_cms import get_page

from .search_request import SearchRequest

class Document:
    """
    Documents represent chunks of Integreat pages
    """
    def __init__(
            self,
            source_path: str,
            chunk: str,
            score: float,
            include_details: bool,
            gui_language: str
        ):
        self.chunk_source_path = source_path
        self.gui_language = gui_language
        self.score = score
        self.chunk = chunk
        self.enrich(include_details)

    def enrich(self, include_details):
        """
        Enrich document with GUI langauge URLs and titles
        """
        if self.gui_language != self.chunk_source_path.split("/")[2]:
            self.gui_source_path = (
                get_page(self.chunk_source_path)["available_languages"][self.gui_language]
            )
        else:
            self.gui_source_path = self.chunk_source_path
        page = get_page(self.gui_source_path)
        self.title = page["title"] if include_details else None
        self.content = page["excerpt"] if include_details else None

    def as_dict(self):
        """
        Dict representation of document
        """
        result = {
            "source": self.gui_source_path,
            "score": self.score,
            "found_chunk": self.chunk,
            "chunk_path": self.chunk_source_path,
        }
        if self.title is not None:
            result["title"] = self.title
        if self.content is not None:
            result["content"] = self.content
        return result

class SearchResponse:
    """
    Response for a search
    """
    def __init__(self, search_request: SearchRequest, documents: list[Document]):
        self.search_term = search_request.translated_message
        self.documents = documents

    def as_dict(self) -> dict:
        """
        dict representation of a search result
        """
        return {
            "related_documents": [document.as_dict() for document in self.documents],
            "search_term": self.search_term,
            "status": "success",
        }
