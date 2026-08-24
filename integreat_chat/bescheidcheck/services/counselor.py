"""
Counseling for the bescheidcheck app (issue #498).

The user selects an Integreat region. We generate a generic question
based on the classified Bescheid type — for example, for
``bamf_simple_rejection``:

    "Where can I find Flüchtlingsberatung / Asylberatung?"

Then we call the existing ``AnswerService`` (RAG) of the ``chatanswers``
app against the selected region and surface the answer (translated to
the user's target language) with a citation. We do NOT read a static
INI table of counseling offices: the Integreat content for the region
is the single source of truth.
"""

import logging
import time

import aiohttp

from integreat_chat.chatanswers.services.answer import AnswerService
from integreat_chat.chatanswers.services.llmapi import LlmClientError
from integreat_chat.chatanswers.utils.rag_request import RagRequest
from integreat_chat.translate.services.language import LanguageService

from ..static.prompts import COUNSELING_SERVICE_BY_TYPE, counseling_question_for
from .sanitizer import sanitize_html

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


async def find_counseling(
    region_slug: str,
    bescheid_type: str,
    target_language: str,
    session: aiohttp.ClientSession | None = None,
) -> dict:
    """
    Look up a counseling option for the user's region using RAG.

    The question is built from the hard-coded counseling service name
    for the given Bescheid type, and then answered by the
    ``AnswerService`` of the chatanswers app. The result is translated
    to the target language via ``RagResponse.render``.

    param region_slug: slug of an Integreat region (e.g. "region-slug-1")
    param bescheid_type: the classified type (e.g. "bamf_simple_rejection")
    param target_language: BCP-47 tag of the user's target language
    return: dict with keys:
        - question:          the question we ask RAG (in EN or DE)
        - answer:            the answer RAG returned (HTML, in the
                              user's target language)
        - answer_language:   the language RAG originally answered in
        - counseling_name:   the hard-coded counseling service name
        - automatic_answers: whether RAG answered (vs. "could not
                              find" / "talk to a human")
        - details:           list of source documents RAG used

    If the LLM server is unavailable (``LlmClientError`` from
    ``LlmApiClient.chat_prompt``), this function degrades gracefully: it
    returns the same dict shape with ``answer == ""``,
    ``automatic_answers is False`` and ``details == []``. The view never
    sees a ``LlmClientError`` propagate.
    """
    started = time.monotonic()
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
    LOGGER.info(
        "counseling: start (region=%s type=%s question=%r)",
        region_slug,
        bescheid_type,
        question[:120],
    )

    rag_request = RagRequest(
        {
            "message": question,
            "language": question_language,
            "region": region_slug,
        },
        skip_language_detection=True,
    )

    rag_request.gui_language = target_language
    t0 = time.monotonic()
    await rag_request.prepare()
    LOGGER.info(
        "counseling: RagRequest.prepare took %.2fs", round(time.monotonic() - t0, 2)
    )

    rag_request.search_term = question

    answer_service = AnswerService(rag_request)
    t0 = time.monotonic()
    response = None
    try:
        response = await answer_service.extract_answer()
    except LlmClientError as exc:
        LOGGER.error("counseling: RAG LLM call failed: %s", exc)
    if response is not None:
        LOGGER.info(
            "counseling: RAG extract_answer took %.2fs (automatic_answers=%s)",
            round(time.monotonic() - t0, 2),
            response.automatic_answers,
        )

    if response is None:
        LOGGER.info(
            "counseling: total %.2fs (degraded, no LLM answer)",
            round(time.monotonic() - started, 2),
        )
        return {
            "question": question,
            "answer": "",
            "answer_language": question_language,
            "counseling_name": translated_name,
            "automatic_answers": False,
            "details": [],
        }

    t0 = time.monotonic()
    response_dict = await response.as_dict()
    LOGGER.info(
        "counseling: response rendering took %.2fs", round(time.monotonic() - t0, 2)
    )
    LOGGER.info("counseling: total %.2fs", round(time.monotonic() - started, 2))

    raw_answer = response_dict.get("answer", "") if response_dict else ""
    return {
        "question": question,
        "answer": sanitize_html(raw_answer) if raw_answer else "",
        "answer_language": response_dict.get("rag_language", question_language),
        "counseling_name": translated_name,
        "automatic_answers": response.automatic_answers,
        "details": response_dict.get("details", []) if response_dict else [],
    }
