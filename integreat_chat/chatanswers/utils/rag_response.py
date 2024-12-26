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
        RAG response. Translate if GUI language does not match used
        RAG language.
        """
        if self.request.gui_language != self.request.use_language:
            message = self.request.language_service.translate_message(
                self.request.use_language,
                self.request.gui_language,
                self.rag_response
            )
        else:
            message = self.rag_response
        return f"{message} {self.create_citation()}"

    def create_citation(self):
        """
        Create human readable list of citations
        """
        sources = []
        for document in self.documents:
            if self.request.gui_language != self.request.use_language:
                sources.append((document.get_source_for_language(self.request.gui_language)))
            else:
                sources.append((document.chunk_source_path, document.title))

        citation = "".join(
            [
                f"<li><a href='{path}'>{title}</a></li>"
                for path, title in sources
            ]
        )
        return f"<ul>{citation}</ul>"

    def as_dict(self):
        """
        Response suitable for returning as JSON
        """
        return {
            "answer": str(self),
            "status": "success",
            "message": self.request.original_message,
            "rag_language": self.request.use_language,
            "rag_message": self.request.translated_message,
            "rag_sources": [document.chunk_source_path for document in self.documents],
            "sources": [],  # legacy hack to not break the Integreat CMS. Can be removed later.
            "details": [{
                "source": document.chunk_source_path,
                "score": document.score,
                "context": document.content,
            } for document in self.documents],
        }