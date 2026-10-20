"""
Counseling question for the bescheidcheck app (issue #498).

The user selects an Integreat region. We generate a generic question
based on the classified Bescheid type — for example, for
``bamf_simple_rejection``:

    "Where can I find Flüchtlingsberatung / Asylberatung?"

The question travels with the analyze result; the UI then asks the
existing ``/chatanswers/extract_answer/`` endpoint for the answer in the
selected region, which is also where the LLM summary of the question is
produced. We do NOT read a static INI table of counseling offices: the
Integreat content for the region is the single source of truth.
"""

import logging

import aiohttp

from integreat_chat.translate.services.language import LanguageService

from ..static.prompts import COUNSELING_SERVICE_BY_TYPE, counseling_question_for

LOGGER = logging.getLogger(__name__)


async def _translate_counseling_name(
    name: str, target_language: str, session: aiohttp.ClientSession
) -> str:
    """
    Translate a counseling service name into the question language so the
    RAG question is coherent.

    If the target language is German, or the LLM call fails, the
    original (German) name is returned unchanged.
    """
    if target_language.lower() in ("de", "deu", "de-de"):
        return name
    try:
        language_service = LanguageService()
        translated = await language_service.translate_message(
            "de",
            target_language,
            name,
            keep_html=False,
            session=session,
        )
    except (ValueError, RuntimeError, aiohttp.ClientError) as exc:
        LOGGER.warning(
            "Could not translate counseling name %r to %s: %s",
            name,
            target_language,
            exc,
        )
        return name
    translated = " ".join((translated or "").split()).strip()
    return translated or name


async def counseling_question(
    bescheid_type: str,
    target_language: str,
    session: aiohttp.ClientSession | None = None,
) -> dict:
    """
    Build the counseling question for a classified Bescheid type.

    param bescheid_type: the classified type (e.g. "bamf_simple_rejection")
    param target_language: BCP-47 tag of the user's target language
    return: dict with keys:
        - question:          the question to ask RAG (in EN or DE)
        - question_language: the language the question is phrased in
        - counseling_name:   the hard-coded counseling service name
    """
    question_language = target_language if target_language in ("de", "en") else "en"

    counseling_name = COUNSELING_SERVICE_BY_TYPE.get(
        bescheid_type, COUNSELING_SERVICE_BY_TYPE["unsupported"]
    )

    translated_name = counseling_name
    if question_language != "de":
        if session is not None:
            translated_name = await _translate_counseling_name(
                counseling_name, question_language, session
            )
        else:
            async with aiohttp.ClientSession() as translate_session:
                translated_name = await _translate_counseling_name(
                    counseling_name, question_language, translate_session
                )
        if translated_name != counseling_name:
            LOGGER.info(
                "counseling: translated counseling name %r -> %r",
                counseling_name,
                translated_name,
            )
    question = counseling_question_for(
        question_language, bescheid_type, translated_name
    )
    LOGGER.info("counseling: question for type=%s: %r", bescheid_type, question[:120])

    return {
        "question": question,
        "question_language": question_language,
        "counseling_name": translated_name,
    }
