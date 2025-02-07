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

    RELEVANCE_CHECK = """You are a relevance grader tasked with evaluating the connection between a user's question and a retrieved document. Your goal is to filter out clearly unrelated documents. 

To assess relevance, look for the presence of keywords, synonyms, or semantic meanings related to the user question within the document. A match does not require a precise or exhaustive answer to the question, but rather a discernible connection.

Provide a binary judgment on the relevance of the document to the user's question, responding with either 'yes' or 'no'.

User question: {0}

Retrieved document: {1}
"""

    CHECK_QUESTION = """Does the following message express a question or indicate a need? Respond with only "yes" or "no".

Message: {0}
"""

    OPTIMIZE_MESSAGE = """Please summarize the following text into one terse sentence or question. Only answer with the summary, no text around it.
    
Text: {0}"""

    HUMAN_REQUEST_CHECK = """You are an assistant trained to classify user intent. Your task is to determine whether the user explicitly wants to talk to a human counselor.

Respond with "Yes" only if the user is explicitly requesting a human, like in these cases:
- "I want to talk to a human"
- "Can I speak with a counselor?"
- "I need human support"

Otherwise, respond with "No," even if the user is asking about general topics.

User query: {0}
"""
