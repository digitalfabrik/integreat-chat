"""
Static Prompts
"""
# pylint: disable=C0301,disable=R0903

class Prompts:
    """
    Collection of required prompts
    """

    FACT_CHECK = """Your are tasked with fact checking the answer of a RAG system in the Integreat App. You're given a generated answer and its sources. Validate that all facts in the answer are contained in the sources. The LLM for generating the answer is instructed to tell users that it cannot make appointments, if relevant. Answer with only one sentence that begins either with 'valid, bacause' or 'not valid, because', depending on your judgement.

# Generated Answer
---
{0}
---

# Sources
---
{1}
"""

    RAG = """You are tasked with answering user messages, usually related to migration, based on retrieved pages from a content management system for {0} in Germany. The user will get links to all retrieved pages. The platform the user is using is named Integreat App.

Obey the following rules for phrasing the answer:
* Make sure that all facts in the generated answer are supported by the sources.
* If the answer is not in the linked pages, only state that the linked pages do not contain an answer to the question.
* If asked about appointments, clarify that you cannot facilitate them. However, if the provided pages contain relevant information on scheduling appointments, include those details.
* Provide an answer that is as short as possible and use three sentences at most.
* Only use HTML as markup, not Markdown. Use HTML sparsely, for example for making phone numbers and e-mail addresses clickable.
* Respond in the language with the BCP-47 tag "{1}".
* Do not add citation marks to the used documents/sources.

User message: {2}

Linked pages: 
---
{3}
"""

    CHECK_DOCUMENT = """# Task
You are part of a retrieval-augmented generation (RAG) system in the Integreat App. Your task is to evaluate whether a retrieved document definitely contains a direct answer to the user’s message. If the user is talking about 'you' or 'app', assume it is the Integreat App.
Evaluation Criteria:

* Generally assume that documents are not relevant and only deem them relevant if there are good reasons.
* General relevance is not enough — it must contain specific and authoritative information.
* However, the document is relevant if it contains information about general counseling about a topic.
* The document is relevant when it contains a direct answer or directly relevant information.
* The document must explicitly address the user’s question or request.
* The document is not relevant when it only provides related background information but does not directly answer the question.
* The document is not relevant if the document's content is tailored to a narrower or more specific audience than can be safely derived from the question.

Response Format:

* Start the answer with "yes" or "no" and add a very brief reason.

# Retrieved document

---

{0}

---
"""


    CHECK_QUESTION = """### Task
You are part of a retrieval-augmented generation system in the Integreat App. Determine whether the **last message in a conversation** requires a response.
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
You are part of a RAG system in the Integreat App that answers migration related questions. You will be given up to 3 messages. **Create a terse summary of the user message.**
Leave out specific personal details and only include generic information that can be found in a knowledge base. Use the language 'LANG_CODE'
for the summary. If the last message is contains an incopmlete question or partial sentence, the previous messages can be used for context.
If the user is talking about 'you' or 'app', assume it is the Integreat App.

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
You are part of a retrieval-augmented generation (RAG) system in the Integreat App. In a previous search no relevant pages were found for a search term. We now want to run a more abstract search. Extract the general topic (one or two words) for a new search. Only return the best search term without any additional text. Use the language '{0}' for the search term.
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
