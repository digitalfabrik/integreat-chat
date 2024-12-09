"""
Service to transform/optimize input queries
"""

import logging
import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_community.llms import Ollama

from django.conf import settings

from ..static.prompts import Prompts


class QueryTransformer:
    """
    Class that enables transforming complicated queries based on different criteria
    """

    def __init__(self, original_query):
        self.original_query = original_query
        self.modified_query = ""
        self.llm = self.load_llm(settings.RAG_QUERY_OPTIMIZATION_MODEL)
        self.LENGTH_THRESHOLD_CHARS = 150

    def load_llm(self, llm_model_name):
        """
        Prepare LLM
        """
        return Ollama(model=llm_model_name, base_url=settings.OLLAMA_BASE_PATH)

    def punctuation_thresh_exceeded(self):
        """
        Identify punctuations(period, comma, question_mark) to identify complexity
        """
        max_period = 1
        max_question_mark = 1
        max_comma = 2

        punctuation_patterns = {
            "period": r"[.。]",
            "comma": r"[,،，、]",
            "question_mark": r"[?؟？]",
        }
        counts = {
            punct: len(re.findall(pattern, self.original_query))
            for punct, pattern in punctuation_patterns.items()
        }

        if (
            counts["period"] > max_period
            or counts["question_mark"] > max_question_mark
            or counts["comma"] > max_comma
        ):
            return True

    def length_thresh_exceeded(self):
        """
        Check if the query exceeds a certain length threshold
        """
        return len(self.original_query) > self.LENGTH_THRESHOLD_CHARS

    def is_transformation_required(self):
        """
        Check if the query requires transformation
        """
        if self.punctuation_thresh_exceeded() or self.length_thresh_exceeded():
            return True

    def transform_query(self):
        """
        Optimize the user query for document retrieval
        """
        prompt = PromptTemplate.from_template(Prompts.OPTIMIZE_MESSAGE)
        chain = prompt | self.llm | StrOutputParser()
        self.modified_query = chain.invoke({"message": self.original_query})
        return {
            "original_query": self.original_query,
            "modified_query": self.modified_query,
        }
