"""
RAG response
"""

from integreat_chat.search.utils.search_response import Document
from .rag_request import RagRequest


class RagResponse:
    """
    Representation of RAG response
    """

    def __init__(
        self,
        documents: list[Document],
        request: RagRequest,
        rag_response: str,
        automatic_answers: bool = True,
    ):
        self.documents = documents
        self.request = request
        self.rag_response = rag_response
        self.automatic_answers = automatic_answers

    def __str__(self):
        """
        RAG response. Translate if GUI language does not match used
        RAG language.
        """
        if self.request.gui_language != self.request.use_language:
            message = self.request.language_service.translate_message(
                self.request.use_language, self.request.gui_language, self.rag_response
            )
        else:
            message = self.rag_response
        return f"{message}{self.create_citation()}"

    def create_citation(self):
        """
        Create human readable list of citations
        """
        sources = []
        for document in self.documents:
            if self.request.gui_language != self.request.use_language:
                sources.append(
                    (document.get_source_for_language(self.request.gui_language))
                )
            else:
                sources.append((document.chunk_source_path, document.title))

        citation = "".join(
            [
                f"<li><a href='{path}'>{title}</a></li>"
                for path, title in sources
                if title is not None
            ]
        )
        return f"\n<ul>{citation}</ul>" if citation else ""

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
            "automatic_answers": self.automatic_answers,
            "details": [
                {
                    "source": document.chunk_source_path,
                    "score": document.score,
                    "context": document.content,
                }
                for document in self.documents
            ],
        }
