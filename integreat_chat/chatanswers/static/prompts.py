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
* Use HTML as markup. Only use HTML sparsely, for example for making phone numbers and e-mail addresses clickable.
* Respond in the language with the BCP-47 tag "{1}".

User message: {2}

Linked pages: 
---
{3}
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
You will be given up to 3 messages, the final message is the one that needs answering.

### Acceptance Criteria
Accept messages that:
- Are a clear and concise question, OR
- Indicate a need, OR
- Indicate a psychological or medical emergency (e.g. thoughts of suicide).
Reject messages that:
- Are too vague or generic (e.g., "I need help," "I have a question").
- Lack a clear request or actionable intent.

### Output Format
Respond with "yes" if the message should be accepted. Reespond with "no" if it should not be accepted. Do not return any additonal text.
"""

    SUMMARIZE_MESSAGE = """### Task
You are part of a RAG system. You will be given up to 3 messages. **Create a terse summary of the user message.**
Leave out specific personal details and only include generic information that can be found in a knowledge base. Use the language 'LANG_CODE'
for the summary. If the last message is contains an incopmlete question or partial sentence, the previous messages can be used for context.

### Examples for summarizing the user question
- Clear questions like "Where can I learn German?" do not need additional context and can be summarized to "learning German"
- If the current message is "for work" and the previous message reads "I need to learn German", then a suitable summary would be "learning German for work".
- Three messages like "Hello, my name is Max", "I need help" and "I'm ill", a summary would be "helping with illness".

### Output Format
Return only the terse summarized user question, nothing else.
"""

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
You are part of a retrieval-augmented generation (RAG) system. In a previous search no relevant pages were found for a search term. We now want to run a more abstract search. Extract the general topic (one or two words) for a new search. Only return the best search term without any additional text. Use the language '{0}' for the search term.
## Examples
- "Finding a job as a medical doctor" to "Finding jobs"
- "medical treatment for flu" to "medical consultation"
- "Bus from city hall to arena" to "public transport"  
- "asylum request was denied after 2 years" to "asylum process"
- "Homeschooling in Germany" to "schooling"
## Search Term
{1}
"""

    CONTEXT_CHECK = """You're a compontent of a RAG system tasked with answering questions. Your job is to judge if a message contains an answerable question or if context from previous messages is required. Answer only with "yes", if more context is required and "no" if the message itself can be answered.

User message: {0}
"""