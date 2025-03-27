"""
Static prompts
"""

class Prompts:
    """
    Static prompts
    """

    SYSTEM_PROMPT = "You are an internal assistant in an application without user interaction."

    LANGUAGE_CLASSIFICATION = "Identify the BCP47 language tag of the provided message."

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

    TRANSLATE_PROMPT = "Translate the user message from {0} into {1}. Return nothing else than the translation itself."
