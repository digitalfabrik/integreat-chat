"""
Some BCP-47 tags are not understood by the translation model. This maps
those tags to plain language names used in prompts.
"""

LANGUAGE_PROMPT_NAMES = {
    "de-si": "Simplified German (Leichte Sprache)",
}


def language_for_prompt(language: str) -> str:
    """
    Return the name to use in a prompt for the given language code.
    """
    return LANGUAGE_PROMPT_NAMES.get(language, language)
