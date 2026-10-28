"""Classify Bescheide using structured LLM responses."""

import logging
import re
from contextlib import nullcontext

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
from .taxonomy import render_classification_taxonomy_context

LOGGER = logging.getLogger(__name__)

_TYPE_ALLOWLIST = set(settings.BESCHEID_SUPPORTED_TYPES)


def _safe_clamp_float(value, default: float = 0.0) -> float:
    """Convert a value to a float and clamp it to [0, 1]."""
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
    """Normalize the response type, confidence, and reason."""
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
    """Strip HTML, collapse whitespace, and limit the text length."""
    html = re.sub(
        r"<(script|style)\b.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(r"<[^>]+>", " ", html)
    text = " ".join(text.split())
    if len(text) > max_chars:
        text = text[:max_chars] + " …"
    return text


def _build_json_schema() -> dict:
    """Build the classification response schema."""
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
    """Classify OCR text and return type, confidence, and reason.

    Args:
        document_text: Document text, optionally containing HTML.
        session: Optional shared HTTP session.
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
        [
            LlmMessage(
                Prompts.BESCHEID_CLASSIFICATION.format(
                    document_text,
                    allowed_types=" | ".join(
                        f'"{document_type}"'
                        for document_type in sorted(_TYPE_ALLOWLIST)
                    ),
                    taxonomy_context=render_classification_taxonomy_context(),
                )
            )
        ],
        json_schema=_build_json_schema(),
    )
    llm = LlmApiClient()
    session_context = (
        aiohttp.ClientSession() if session is None else nullcontext(session)
    )
    async with session_context as active_session:
        try:
            raw = await llm.chat_prompt(active_session, prompt)
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
                r"\"?type\"?\s*[:=]\s*\"([a-z_-]+)\"", str(response), flags=re.IGNORECASE
            )
            if m:
                parsed = {"type": m.group(1)}
        return _sanitize_classification(parsed)
