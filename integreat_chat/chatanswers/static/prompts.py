"""
Static Prompts
"""
# pylint: disable=C0301,disable=R0903

class Prompts:
    """
    Collection of required prompts
    """

    RAG = """You are an AI assistant specializing in question-answering.
Use the retrieved context below to provide a concise and accurate response to the last user message.
Use the previous user messages as context, if this is required to understand the last message.

* If the answer is not in the context, state that you don’t know.
* If asked about appointments, clarify that you cannot facilitate them. However, if the provided documents contain relevant information on scheduling appointments, include those details.
* Keep your response within three sentences.
* Respond in {0} language.

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

    CHECK_QUESTION = """### Task
You are part of a retrieval-augmented generation system. Determine whether the **last message in a conversation** requires a response. You will be given up to 3 messages, the final message is the most important. Prior messages may provide context but should only be used if they clarify the intent.

### Acceptance Criteria
Accept messages that:
- Are a **clear and concise question**, OR
- Are a **specific, actionable statement** that indicates a need.
Reject messages that:
- Are too vague or generic (e.g., "I need help," "I have a question").
- Lack a clear request or actionable intent.

### Processing Steps
1. Determine if the last message is actionable.
2. If needed, use previous messages for context, but do not introduce new information.
3. Extract and summarize the core need or question from the last message and the previous message as context.

### Output Format
Respond with a JSON object:

{
  "accept_message": (true/false),
  "summarized_user_question": "keyword or empty string",
}
```
"""

    CHECK_QUESTION_SCHEMA = {
        "name": "user_question_classification",
        "schema": {
            "type": "object",
            "properties": {
                "accept_message": {
                    "type": "boolean"
                },
                "summarized_user_question": {
                    "type": "string"
                }
            },
            "required": ["accept_message", "summarized_user_question"],
            "additionalProperties": False,
        },
        "strict": True,
    }

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
