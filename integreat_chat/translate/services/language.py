"""
A service to detect languages and translate messages
"""

from langchain_core.output_parsers import StrOutputParser
# pylint: disable=no-name-in-module
from langchain_community.llms import Ollama
from transformers import pipeline

from langchain.prompts import PromptTemplate

from django.conf import settings
from integreat_chat.chatanswers.static.prompts import Prompts
from integreat_chat.translate.static.language_code_map import LANGUAGE_MAP

class LanguageService:
    """
    Service class that enables searching for Integreat content
    """
    def __init__(self):
        """
        
        """

    def classify_language(self, estimated_lang, message):
        """
        Check if a message fits the estimated language.
        Return another language tag, if it does not fit.
        """
        prompt_template = PromptTemplate.from_template(Prompts.LANGUAGE_CLASSIFICATION)
        llm = Ollama(
            model=settings.LANGUAGE_CLASSIFICATIONH_MODEL,
            base_url=settings.OLLAMA_BASE_PATH
        )
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
        pipe = pipeline("translation", model=settings.TRANSLATION_MODEL)
        return " ".join([
            result["translation_text"] for result in pipe(
                self.split_text(message),
                tgt_lang=LANGUAGE_MAP[target_language],
                src_lang=LANGUAGE_MAP[source_language]
            )
        ])

    def opportunistic_translate(self, expected_language, message):
        """
        Translate if detected language does not fit the expected language
        """
        classified_language = self.classify_language(
            expected_language,
            message
        )
        return (
            message if classified_language == expected_language
            else self.translate_message(
                classified_language,
                expected_language,
                message
            )
        )

    def split_text(self, text, max_length=200):
        """
        Chunk text at the end of sentences into max 500 char chunks
        """
        sentences = text.split('.')
        chunks = []
        current_chunk = ""
        for sentence in sentences:
            if not sentence.strip():
                continue
            sentence = sentence.strip() + "."
            if len(current_chunk) + len(sentence) <= max_length:
                current_chunk += sentence + " "
            else:
                chunks.append(current_chunk.strip())
                current_chunk = sentence + " "
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        return chunks
