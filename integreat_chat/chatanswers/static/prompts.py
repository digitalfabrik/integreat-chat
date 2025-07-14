"""
Static Prompts
"""
# pylint: disable=C0301,disable=R0903

class Prompts:
    """
    Collection of required prompts
    """

    RAG = """You are tasked with answering user messages based on retrieved pages from a content management system for {0} in Germany. The user will get links to all retrieved pages.

Obey the following rules for phrasing the answer:
* If the answer is not in the linked pages, only state that the linked pages do not contain an answer to the question.
* If asked about appointments, clarify that you cannot facilitate them. However, if the provided pages contain relevant information on scheduling appointments, include those details.
* Provide an answer that is as short as possible and use three sentences at most.
* Respond in the language with the BCP-47 tag "{1}".

User message: {2}

Linked pages: {3}
"""

    CHECK_DOCUMENT = """# Task
You are part of a retrieval-augmented generation (RAG) system. Your task is to evaluate whether a retrieved document definitely contains a direct answer to the user’s message.
Evaluation Criteria:

* Generally assume that documents are not relevant and only deem them relevant if there are good reasons.
* The document must explicitly address the user’s question or request.
* General relevance is not enough — it must contain specific and authoritative information.
* If the document only provides related background information but does not directly answer the question, answer "no".
* If the document contains the exact answer or directly relevant information, answer "yes".

Response Format:

* Start the answer with "yes" or "no" and add a very brief reason.

# Retrieved document

---

{0}

---
"""


    CHECK_QUESTION = """### Task
You are part of a retrieval-augmented generation system. Determine whether the **last message in a conversation** requires a response.
You will be given up to 3 messages, the final message is the most important. Prior messages may provide context but should only be used
if they clarify the intent. Finally, provide a summary of the message that can be used for searching documents and in a prompt to generate
an answer. For the summary, leave out too specific personal details and only include generic information that can be found in a knowledge
base.

### Acceptance Criteria
Accept messages that:
- Are a clear and concise question, OR
- Indicate a need, OR
- Indicate a psychological or medical emergency (e.g. thoughts of suicide).
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

    HUMAN_REQUEST_CHECK = """Your task is to determine if the user explicitly requests to speak with a human counselor.

Respond with "Yes" if the user clearly asks to speak with a human counselor. Examples include:
    * "I want to talk to a human."
    * "Can I speak with a counselor?"
    * "I need human support."

For all other messages, including general inquiries or indirect mentions of counseling, respond with "No." This includes cases where the user expresses psychological distress, such as suicidal thoughts or self-harm. Examples:
    * "Who can help me with language courses?"
    * "I want to commit suicide."
    * "I’m thinking about hurting myself."

User message: {0}
"""

    SHALLOW_SEARCH = """# Task
You are part of a retrieval-augmented generation (RAG) system. In a previous search no relevant pages were found for a search term. We now want to run a more abstract search. Extract the general topic (one or two words) for a new search. Only return the best search term without any additional text.
## Examples
- "Finding a job as a medical doctor" to "Finding jobs"
- "medical treatment for flu" to "medical consultation"
- "Bus from city hall to arena" to "public transport"  
- "asylum request was denied after 2 years" to "asylum process"
- "Homeschooling in Germany" to "schooling"
## Search Term
{0}
"""
