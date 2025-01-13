"""
Static Prompts
"""
# pylint: disable=C0301,disable=R0903

class Prompts:
    """
    Collection of required prompts
    """

    RAG_SYSTEM_PROMPT = "You are a helpful assistant in the Integreat App. You counsel migrants based on content that exists in the app."

    RAG = """You are an assistant for question-answering tasks.
Use the following pieces of retrieved context to answer the question.
If you don't know the answer, just say that you don't know.
Use three sentences maximum and keep the answer concise. Answer the question in {0} language.

Question: {1}

Context: {2}
"""

    CHECK_SYSTEM_PROMPT = "You are an internal assistant in an application without user interaction."

    RELEVANCE_CHECK = """You are a grader assessing relevance of a retrieved document to a user question.
If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant.
It does not need to be a stringent test. The goal is to filter out erroneous retrievals.
Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question and only answer with either 'yes' or 'no'.

User question: {0}

Retrieved document: {1}
"""

    CHECK_QUESTION = """Does the following message express a question or indicate a need? Respond with only "yes" or "no".

Message: {0}
"""

    OPTIMIZE_MESSAGE = """Please summarize the following text into one terse sentence or question. Only answer with the summary, no text around it.
    
Text: {0}"""

    HUMAN_REQUEST_CHECK = """You are an assistant trained to classify user intent. Your task is to determine whether the user wants to talk to a human.
Always respond with "Yes" if the user is asking for human assistance, and "No otherwise"

User query: {0}"""
