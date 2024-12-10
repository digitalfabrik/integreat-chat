"""
Static Prompts
"""
# pylint: disable=C0301,disable=R0903

class Prompts:
    """
    Collection of required prompts
    """

    RAG = """You are an assistant for question-answering tasks.
Use the following pieces of retrieved context to answer the question.
If you don't know the answer, just say that you don't know.
Use three sentences maximum and keep the answer concise. Answer the question in {language} language.

Question: {question}

Context: {context}

Answer:
"""

    LANGUAGE_CLASSIFICATION = """
Identify the language of the provided message.
Only return the most likely BCP47 language tag that represents the message's language.
Do not add any additional words.

Message: {message}
"""


    TRANSLATION = """
Translate the following message from the language tagged as "{source_language}" to the language tagged as "{target_language}".
Please return only the translated message without any additional text.

Message: {message}
"""

    RELEVANCE_CHECK = """You are a grader assessing relevance of a retrieved document to a user question.
If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant.
It does not need to be a stringent test. The goal is to filter out erroneous retrievals.
Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question and only answer with either 'yes' or 'no'.

User question: {question}

Retrieved document: {document}
"""

    CHECK_QUESTION = """Does the following message express a question or indicate a need? Respond with only "yes" or "no".

Message: {message}
"""

    OPTIMIZE_MESSAGE = """Please summarize the following text into one terse sentence or question. Only answer with the summary, no text around it.
    
Text: {message}"""
