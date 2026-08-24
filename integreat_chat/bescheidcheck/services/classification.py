"""
Bescheid classification for the bescheidcheck pipeline (issues #496, #497).

Uses the LLM with a json_schema response_format to get a structured
classification for the document as a whole:

    {
      "type": "<one of the supported slugs or 'unsupported'>",
      "confidence": <float 0..1>,
      "reason": "<one sentence>"
    }

If the response cannot be parsed, we return a safe default classification
so the API can still return a useful response to the user.
"""

import logging
import re

import aiohttp
from django.conf import settings

from integreat_chat.chatanswers.services.llmapi import (
    LlmApiClient,
    LlmClientError,
    LlmMessage,
    LlmPrompt,
    LlmResponse,
)

from ..static.prompts import Prompts

LOGGER = logging.getLogger(__name__)

# Slugs we always accept in the "type" field of the response.
_TYPE_ALLOWLIST = {
    "bamf_simple_rejection",
    "obviously_unfounded_inadmissible",
    "dublin_decision",
    "unsupported",
}


def _safe_clamp_float(value, default: float = 0.0) -> float:
    """
    Coerce a JSON-able value into a float in [0, 1].
    """
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out < 0.0:
        return 0.0
    if out > 1.0:
        return 1.0
    return out


def _sanitize_classification(raw: dict) -> dict:
    """
    Force the response into the safe shape we promise to callers.
    """
    raw = raw if isinstance(raw, dict) else {}
    raw_type = (raw.get("type") or "").strip()
    if raw_type not in _TYPE_ALLOWLIST:
        raw_type = "unsupported"
    raw_reason = (raw.get("reason") or "").strip()
    if len(raw_reason) > 500:
        raw_reason = raw_reason[:500]
    return {
        "type": raw_type,
        "confidence": _safe_clamp_float(raw.get("confidence")),
        "reason": raw_reason,
    }


def _text_from_html(html: str, max_chars: int = 20000) -> str:
    """
    Strip HTML tags and collapse whitespace. Cap the length so we don't
    send unreasonably long prompts to the LLM.
    """
    html = re.sub(
        r"<(script|style)\b.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(r"<[^>]+>", " ", html)
    text = " ".join(text.split())
    if len(text) > max_chars:
        text = text[:max_chars] + " …"
    return text


def _build_json_schema() -> dict:
    """
    Build the OpenAI compatible json_schema for classification.
    """
    return {
        "type": "object",
        "name": "bescheid_classification",
        "schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": sorted(_TYPE_ALLOWLIST),
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "reason": {"type": "string"},
            },
            "required": ["type", "confidence"],
        },
    }


async def classify_bescheid(
    document_text: str,
    session: aiohttp.ClientSession | None = None,
) -> dict:
    """
    Classify a Bescheid by running the LLM prompt with the json_schema.

    param document_text: full OCR'd text of the document (any HTML is
        stripped by the LLM-side prompt)
    param session: optional shared aiohttp session
    return: sanitized dict with keys type/confidence/reason
    """
    document_text = _text_from_html(document_text)
    if not document_text:
        return {
            "type": "unsupported",
            "confidence": 0.0,
            "reason": "No text was found in the document.",
        }

    prompt = LlmPrompt(
        settings.BESCHEID_CLASSIFICATION_MODEL,
        [LlmMessage(Prompts.BESCHEID_CLASSIFICATION.format(document_text))],
        json_schema=_build_json_schema(),
    )
    llm = LlmApiClient()
    if session is None:
        async with aiohttp.ClientSession() as owned_session:
            session = owned_session
    try:
        raw = await llm.chat_prompt(session, prompt)
    except LlmClientError as exc:
        LOGGER.warning("Classification failed (LLM server error): %s", exc)
        return {
            "type": "unsupported",
            "confidence": 0.0,
            "reason": (
                "The classification service could not read the document "
                "(the language-model server returned an error). "
                "Please try again."
            ),
        }
    response = LlmResponse(raw)
    # ``as_dict`` returns {} on unparseable output; the regex below is
    # the salvage path for a non-JSON response.
    parsed = response.as_dict()
    if not parsed:
        m = re.search(
            r"\"?type\"?\s*[:=]\s*\"([a-z_]+)\"", str(response), flags=re.IGNORECASE
        )
        if m:
            parsed = {"type": m.group(1)}
    return _sanitize_classification(parsed)
