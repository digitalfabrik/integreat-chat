"""
RAG response
"""
from integreat_chat.search.utils.search_response import Document
from integreat_chat.core.utils.integreat_request import IntegreatRequest

class RagResponse():
    """
    Representation of RAG response
    """
    def __init__(self, documents: list[Document], request: IntegreatRequest, rag_response: str):
        self.documents = documents
        self.request = request
        self.rag_response = rag_response

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
            "message": self.request.original_message,
            "sources": [document["url"] for document in self.documents],
            "details": [{
                "source": document['source_path'],
                "score": document['score'],
                "context_path": document['source'],
                "context": document['text'],
            } for document in self.documents],
        }
