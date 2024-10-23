"""
Retrieving matching documents for question an create summary text
"""
import logging

from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_community.llms import Ollama
from langchain_milvus.vectorstores import Milvus
from sentence_transformers import SentenceTransformer

from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import PromptTemplate

from pymilvus import (
    connections,
    Collection,
)

from django.conf import settings

from .language import LanguageService
from ..static.prompts import Prompts
from ..static.messages import Messages

LOGGER = logging.getLogger('django')


class AnswerService:
    _instance = None

    @staticmethod
    def get_instance(region, language):
        if AnswerService._instance is None:
            AnswerService._instance = AnswerService(region, language)
        return AnswerService._instance

    def __init__(self, region, language):
        self.language = language
        self.llm_model_name = settings.RAG_MODEL

        self.vdb_host = settings.VDB_HOST
        self.vdb_port = settings.VDB_PORT
        self.vdb_collection = f"collection_ig_{region}_{language}"
        self.vdb = self.load_vdb(self.vdb_host, self.vdb_port,
                                 self.vdb_collection, settings.EMBEDDINGS)

        self.llm = self.load_llm(self.llm_model_name)

    def load_llm(self, llm_model_name):
        llm = Ollama(model=llm_model_name, base_url=settings.OLLAMA_BASE_PATH)
        return llm

    def load_vdb(self, URI, port, collection, embedding_model):
        vdb = Milvus(
                embedding_model,
                connection_args={"host": URI, "port": port},
                collection_name=collection)
        return vdb

    def doc_details(self, results):
        """
        convert result into sources dict
        """
        sources = []
        for source in results:
            sources.append({"source": source.entity.get('source'), "score": source.distance})
        return sources

    def needs_answer(self, message):
        """
        Check if a chat message is a question
        """
        prompt = PromptTemplate.from_template(Prompts.CHECK_QUESTION)
        chain = prompt | self.llm | StrOutputParser()
        answer = chain.invoke({"message": message})
        if answer.startswith("Yes"):
            return True
        return False


    def search_documents(self, question):
        """
        Retrieve a list of documents from database
        """
        connections.connect("default", host=self.vdb_host, port=self.vdb_port)

        search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
        embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        collection = Collection(self.vdb_collection)
        collection.load()

        sentences = [question]
        embeddings = embedding_model.encode(sentences)
        return collection.search(
            data=embeddings,
            anns_field="vector",
            param=search_params,
            limit=settings.RAG_MAX_DOCUMENTS,
            expr=None,
            consistency_level="Strong",
            output_fields=["source", "text"]
        )[0]

    def extract_answer(self, question):
        """
        Create summary answer for question
        """
        results = self.search_documents(question)

        LOGGER.debug("Number of retrieved documents: %i", len(results))
        if settings.RAG_RELEVANCE_CHECK:
            results = [result for result in results if self.check_document_relevance(
                question, result.entity.get('text')
            )]
        LOGGER.debug("Number of documents after relevance check: %i", len(results))

        context = RunnableLambda(lambda _: "\n".join(
            [result.entity.get('text') for result in results]
        ))
        if not results:
            language_service = LanguageService()
            return {
                "answer": language_service.translate_message(
                    "en", self.language,
                    Messages.NO_ANSWER
                )
            }
        rag_chain = (
            {"context": context, "question": RunnablePassthrough()}
                | settings.RAG_PROMPT
                | self.llm
                | StrOutputParser()
        )
        answer = rag_chain.invoke(question)
        return {
            "answer": answer,
            "sources": list({result.entity.get('source') for result in results}),
            "details": self.doc_details(results)
        }


    def check_document_relevance(self, question, content):
        """
        Check if the retrieved documents are relevant
        """
        grade_prompt = PromptTemplate.from_template(Prompts.RELEVANCE_CHECK)
        chain = grade_prompt | self.llm | StrOutputParser()

        response = chain.invoke({"document": content, "question": question})
        response = response.strip().lower()
        return response.startswith("yes")
