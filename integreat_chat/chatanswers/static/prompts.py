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
You are part of a retrieval-augmented generation (RAG) system.  
Your goal is to analyze up to 3 user messages and produce a structured list of **distinct intents** that may appear:
1. Across multiple messages, and/or  
2. Within a single message containing multiple requests.

Each intent should describe one specific user goal or question.

### Acceptance Criteria
Accept intents that:
- Are explicit or implicit questions (e.g., “Where can I learn German?” or “I need a doctor”).
- Express a concrete need or goal.
- Indicate an emergency or psychological distress (e.g., suicidal thoughts).

Reject intents that:
- Are vague, incomplete, or purely social (e.g., “Hi”, “I have a question”, “Help”).
- Lack any actionable information.

### Instructions
- Detect **multiple intents even within a single user message** (e.g., “I need a job and housing” → two intents: `find a job`, `find housing`).
- Merge related messages that share the same topic into one intent (e.g., “I need to learn German” + “for work” → `how to learn German for work`).
- Keep each intent independent — one intent = one line of thought or topic.
- Summarize **only** when needed:
  - If an intent is already clear, keep it as-is.
  - If context from previous messages is required, merge and summarize concisely.
- For emergencies, prefix with `"emergency:"` in the summary.

### Output format (exact)
Return a single JSON object:

{
  "intents": [
    {
      "accept_message": true|false,
      "summarized_user_question": "short summary or empty string"
    },
    ...
  ]
}

Notes:
- Maintain the order of intents as they appear (first → last).
- Use empty string for `summarized_user_question` when rejecting/vague.
- Keep summary ≤ 12 words where possible.
"""

    CHECK_QUESTION_SCHEMA = {
    "name": "user_question_classification",
    "schema": {
        "type": "object",
        "properties": {
            "intents": {
                "type": "array",
                "items": {
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
                    "additionalProperties": False
                },
                "minItems": 1
            }
        },
        "required": ["intents"],
        "additionalProperties": False
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
