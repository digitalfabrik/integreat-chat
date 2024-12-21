"""
RAG response
"""
from .rag_request import RagRequest
from .integreat_cms import get_page

class RagResponse:
    """
    Representation of RAG response
    """
    def __init__(
            self,
            rag_request: RagRequest,
            rag_response: str,
            rag_documents: list,
        ):
        self.rag_response = rag_response
        self.rag_request = rag_request
        self.rag_documents = self.enrich_rag_documents(rag_documents)

    def __str__(self):
        """
        RAG response
        """
        return self.rag_response

    def as_dict(self):
        """
        Response suitable for returning as JSON
        """
        return {
            "answer": str(self),
            "status": "success",
            "message": self.rag_request.rag_request,
            "sources": [document["url"] for document in self.rag_documents],
            "details": [{
                "context_path": document['path'],
                "source": document['source_path'],
                "context": document['text'],
                "score": document['score']
            } for document in self.rag_documents],
        }

    def enrich_rag_documents(self, rag_documents: list):
        """
        Enrich used documents with GUI langauge URLs and titles
        """
        rag_documents = self.add_source_paths(rag_documents)
        rag_documents = self.add_titles(rag_documents)
        return rag_documents

    def add_source_paths(self, rag_documents: list) -> str:
        """
        Generate list of sources in the GUI language based on the used documents in RAG
        """
        result = []
        for document in rag_documents:
            if self.rag_request.gui_language == self.rag_request.rag_language:
                document["source_path"] = document["path"]
            else:
                document["source_path"] = (
                    get_page(document)["available_languages"][self.rag_request.gui_language]["path"]
                )
            result.append(document)
        return result

    def add_titles(self, rag_documents):
        """
        Get pages from Integreat CMS and add GUI language titles
        """
        result = []
        for document in rag_documents:
            document["title"] = get_page(document)["title"]
        return result
