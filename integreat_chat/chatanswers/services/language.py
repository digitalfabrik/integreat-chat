"""
A service to detect languages and translate messages
"""

from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_community.llms import Ollama

#from langchain.runnables.base import RunnableLambda
from langchain_core.runnables import RunnableLambda
from langchain.prompts import PromptTemplate

from django.conf import settings
from ..static.prompts import Prompts

class LanguageService:
    """
    Service class that enables searching for Integreat content
    """
    def __init__(self):
        """
        
        """

    def classify_language(self, estimated_lang, message):
        """
        Check if a message fits the estimated language. Return another language tag, if it does not fit.
        """
        prompt_template = PromptTemplate.from_template(Prompts.LANGUAGE_CLASSIFICATION)
        llm = Ollama(model=settings.LANGUAGE_CLASSIFICATIONH_MODEL, base_url=settings.OLLAMA_BASE_PATH)
        chain = prompt_template | llm | StrOutputParser()
        answer = chain.invoke({"message": message, "estimated_lang": estimated_lang})
        if answer.startswith(estimated_lang):
            return estimated_lang
        return answer.split("-")[0]

    def translate_message(self, source_language, target_language, message):
        """
        Translate a message from source to target language
        """
        if source_language == target_language:
            return message
        prompt_template = PromptTemplate.from_template(Prompts.TRANSLATION)
        llm = Ollama(model=settings.TRANSLATION_MODEL, base_url=settings.OLLAMA_BASE_PATH)
        chain = prompt_template | llm | StrOutputParser()
        return chain.invoke({
            "source_language": source_language,
            "target_language": target_language,
            "message": message
        })
