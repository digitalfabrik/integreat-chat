"""
Static Prompts
"""
# pylint: disable=C0301,disable=R0903

class Prompts:
    """
    Collection of required prompts
    """

    RAG = """You are tasked with answering user message based on retrieved pages from a content management system. The user will get links to all retrieved pages.

Obey the following rules for phrasing the answer:
* If the answer is not in the linked pages, only state that the linked pages do not contain an answer to the question.
* If asked about appointments, clarify that you cannot facilitate them. However, if the provided pages contain relevant information on scheduling appointments, include those details.
* Provide a answer that is as short as possible and use three sentences at most.
* Respond in the language with the BCP-47 tag "{0}".

User message: {1}

Linked pages: {2}
"""

    CHECK_SYSTEM_PROMPT = "You are an internal assistant in an application without user interaction."

    RELEVANCE_CHECK = """You are part of a retrieval augmented generation system.
It's your task to filter retrieved documents that can be used to answer the user question.
Provide a binary judgement if the document contains an answer to the user question, responding with either 'yes' or 'no'.

User question: {0}

Retrieved document: {1}
"""

    CHECK_QUESTION = """### Task
You are part of a retrieval-augmented generation system. Determine whether the **last message in a conversation** requires a response.
You will be given up to 3 messages, the final message is the most important. Prior messages may provide context but should only be used
if they clarify the intent. Finally, provide a summary of the message that can be used for searching documents and in a prompt to generate
an answer.

### Acceptance Criteria
Accept messages that:
- Are a **clear and concise question**, OR
- Are a **specific, actionable statement** that indicates a need.
Reject messages that:
- Are too vague or generic (e.g., "I need help," "I have a question").
- Lack a clear request or actionable intent.

### Processing Steps
1. If needed, use previous messages for context, but do not introduce new information.
2. Determine if the last message is actionable.
3. Summarize the message into a short sentence or question.

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
