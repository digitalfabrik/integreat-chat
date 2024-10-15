"""
Retrieving matching documents for question an create summary text
"""
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_community.llms import Ollama
from langchain_milvus.vectorstores import Milvus

#from langchain.runnables.base import RunnableLambda
from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import ChatPromptTemplate

from django.conf import settings
import json

from .language import LanguageService

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
            sources.append({"source": source[0].metadata["source"], "score": source[1]})
        return sources

    def needs_answer(self, question):
        """
        Check if a chat message is a question
        """
        parser = StrOutputParser()
        prompt = (
            f"Can the following message considered to be a question? "
            f"Answer only one word, either yes or no.\nMessage:{question}"
        )
        answer = parser.invoke(self.llm.invoke(prompt))
        if answer.startswith("Yes"):
            return True
        return False


    def extract_answer(self, question):
        """
        Create summary answer for question
        """
        results = sorted([
            result for result in self.vdb.similarity_search_with_score(
                question, k=settings.RAG_MAX_DOCUMENTS
            ) if result[1] < settings.RAG_DISTANCE_THRESHOLD
        ], key=lambda x: x[1])
        
        if settings.RAG_RELEVANCE_CHECK:
            results = [result for result in results if self.check_document_relevance(question, result[0].page_content)]

        context = RunnableLambda(lambda _: "\n".join(
            [result[0].page_content for result in results]
        ))
        if not results:
            language_service = LanguageService()
            return {"answer": language_service.translate_message("en", self.language,
                "Sorry, we could not find an answer for you in the "
                "Integreat content. Please wait for a message from a human counsel."
            )}
        rag_chain = (
            {"context": context, "question": RunnablePassthrough()}
                | settings.RAG_PROMPT
                | self.llm
                | StrOutputParser()
        )
        answer = rag_chain.invoke(question)
        return {
            "answer": answer,
            "sources": list({result[0].metadata["source"] for result in results}),
            "details": self.doc_details(results)
        }


    def check_document_relevance(self, question, content):
        """
        Check if the retrieved documents are relevant
        """

        system = """You are a grader assessing relevance of a retrieved document to a user question. \n 
        If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant. \n
        It does not need to be a stringent test. The goal is to filter out erroneous retrievals. \n
        Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question and only answer with either 'yes' or 'no'."""
        
        grade_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                ("human", "Retrieved document: \n\n {document} \n\n User question: {question}"),
            ]
        )
        chain = grade_prompt | self.llm | StrOutputParser()
        
        response = chain.invoke({"document": content, "question": question})
        response = response.strip().lower()
        print(content, '\n', '-'*25)
        print(f'Relevance - {response}', '\n', '-'*70)
        return response.startswith("yes")
