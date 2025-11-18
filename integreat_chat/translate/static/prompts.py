"""
Static prompts
"""

class Prompts:
    """
    Static prompts
    """

    LANGUAGE_CLASSIFICATION = """Identify the BCP47 language tag of the provided message.
Make sure to only return valid BCP-47 tags.
If languages are mixed, return the language that has more stop words in the message.
If a few German nouns are mixed into the message, ignore them. Return only the BCP-47 tag, no other text.
"""

    LANGUAGE_CLASSIFICATION_SCHEMA = {
        "name": "language",
        "schema": {
            "type": "object",
            "properties": {
                "bcp47-tag": {
                    "type": "string"
                }
            },
            "required": ["bcp47-tag"],
            "additionalProperties": False,
        },
        "strict": True,
    }

    TRANSLATE_PROMPT = "You are a translator. Translate the user message from '{0}' to '{1}' using BCP-47 language tags. Provide only the translation, without any additional text or explanation."
