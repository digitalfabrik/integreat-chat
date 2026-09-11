"""
Structured data extraction for the Bescheidcheck pipeline (issue #504).

"""

import logging

import aiohttp

from integreat_chat.chatanswers.services.llmapi import (
    LlmApiClient,
    LlmClientError,
    LlmMessage,
    LlmPrompt,
    LlmResponse,
)

LOGGER = logging.getLogger(__name__)


def _text_from_html(html: str, max_chars: int = 20000) -> str:
    """
    Convert OCR HTML into plain text before sending it to the LLM.
    """
    import re

    html = re.sub(
        r"<(script|style)\b.*?</\1>",
        " ",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", html)
    text = " ".join(text.split())

    if len(text) > max_chars:
        text = text[:max_chars] + " …"

    return text


_EXTRACTION_SCHEMA = {
    "type": "object",
    "name": "bescheid_structured_extraction",
    "schema": {
        "type": "object",
        "properties": {
            "authority": {
                "type": ["string", "null"],
            },
            "topic": {
                "type": ["string", "null"],
            },
            "required_action": {
                "type": ["string", "null"],
            },
            "requested_documents": {
                "type": "array",
                "items": {"type": "string"},
            },
            "deadline_detected": {
                "type": "boolean",
            },
            "deadline_date": {
                "type": ["string", "null"],
            },
            "deadline_text": {
                "type": ["string", "null"],
            },
            "consequences": {
                "type": "array",
                "items": {"type": "string"},
            },
            "appointment": {
                "type": ["string", "null"],
            },
            "legal_procedure": {
                "type": ["string", "null"],
            },
            "risk_level": {
                "type": ["string", "null"],
                "enum": ["low", "medium", "high", None],
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
        },
        "required": [
            "authority",
            "topic",
            "required_action",
            "requested_documents",
            "deadline_detected",
            "deadline_date",
            "deadline_text",
            "consequences",
            "appointment",
            "legal_procedure",
            "risk_level",
            "confidence",
        ],
    },
}

_SUPPORTED_BESCHEID_TYPES = {
    "bamf_simple_rejection",
    "obviously_unfounded_inadmissible",
    "dublin_decision",
}


def get_extraction_schema(bescheid_type: str) -> dict | None:
    """
    Return the MVP extraction schema for supported Bescheid types.
    """
    if bescheid_type not in _SUPPORTED_BESCHEID_TYPES:
        return None

    return _EXTRACTION_SCHEMA


def _nullable_string(value: object) -> str | None:
    """
    Return a stripped string or None for missing/invalid values.
    """
    if not isinstance(value, str):
        return None

    value = value.strip()
    return value or None


def _string_list(value: object) -> list[str]:
    """
    Return only non-empty string items from a list.
    """
    if not isinstance(value, list):
        return []

    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _normalize_extracted_data(data: dict, bescheid_type: str) -> dict:
    """
    Normalize LLM extraction output before exposing it to the frontend.
    """
    confidence = data.get("confidence")

    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        confidence = 0.0

    confidence = max(0.0, min(1.0, float(confidence)))

    risk_level = _nullable_string(data.get("risk_level"))
    if risk_level is not None:
        risk_level = risk_level.lower()

    if risk_level not in {"low", "medium", "high"}:
        risk_level = None

    return {
        "authority": _nullable_string(data.get("authority")),
        "document_type": bescheid_type,
        "topic": _nullable_string(data.get("topic")),
        "required_action": _nullable_string(data.get("required_action")),
        "requested_documents": _string_list(data.get("requested_documents")),
        "deadline_detected": data.get("deadline_detected") is True,
        "deadline_date": _nullable_string(data.get("deadline_date")),
        "deadline_text": _nullable_string(data.get("deadline_text")),
        "consequences": _string_list(data.get("consequences")),
        "appointment": _nullable_string(data.get("appointment")),
        "legal_procedure": _nullable_string(data.get("legal_procedure")),
        "risk_level": risk_level,
        "confidence": confidence,
    }


async def _run_extraction_prompt(
    prompt_text: str,
    json_schema: dict,
    model: str,
    session: aiohttp.ClientSession | None = None,
) -> dict:
    """
    Run a prompt and parse the structured JSON response.
    """
    prompt = LlmPrompt(
        model,
        [LlmMessage(prompt_text)],
        json_schema=json_schema,
    )
    llm = LlmApiClient()

    try:
        if session is None:
            async with aiohttp.ClientSession() as owned_session:
                raw = await llm.chat_prompt(owned_session, prompt)
        else:
            raw = await llm.chat_prompt(session, prompt)
    except LlmClientError as exc:
        LOGGER.warning("Structured extraction failed: %s", exc)
        return {}

    return LlmResponse(raw).as_dict()


async def extract_structured_data(
    document_text: str,
    bescheid_type: str,
    model: str,
    session: aiohttp.ClientSession | None = None,
) -> dict:
    """
    Extract structured information from an OCR'd Bescheid.

    The extraction schema is selected based on the classified
    document type.
    """
    text = _text_from_html(document_text)

    if not text:
        return {}

    json_schema = get_extraction_schema(bescheid_type)
    if json_schema is None:
        return {}

    prompt_text = (
        "You extract structured information from OCR'd German administrative "
        "documents (Bescheide).\n\n"
        "Rules:\n"
        "- Extract only information that is explicitly supported by the document.\n"
        "- Do not guess, invent, or complete missing facts.\n"
        "- Use null for missing scalar values.\n"
        "- Use [] for missing list values.\n"
        "- authority: the issuing authority, only if it can be identified from "
        "the document.\n"
        "- topic: a short description of the administrative topic supported by "
        "the document.\n"
        "- required_action: only an action explicitly required from the recipient; "
        "otherwise null.\n"
        "- requested_documents: include only documents explicitly requested from "
        "the recipient.\n"
        "- deadline_detected: true only if the document explicitly contains a "
        "deadline or time limit.\n"
        "- deadline_date: use YYYY-MM-DD only if a concrete calendar date is "
        "explicitly stated as the deadline. Do not calculate a date from relative "
        "phrases such as 'innerhalb einer Woche'.\n"
        "- deadline_text: preserve the original wording of the deadline or time "
        "limit from the document; otherwise null.\n"
        "- consequences: include only consequences explicitly stated in the "
        "document.\n"
        "- appointment: include appointment information only if explicitly stated; "
        "otherwise null.\n"
        "- legal_procedure: include only a legal remedy or procedure explicitly "
        "mentioned in the document; otherwise null.\n"
        "- risk_level: use only low, medium, or high based on information present "
        "in the document. If the level cannot be determined reliably, use null.\n"
        "- confidence: return a number from 0 to 1 representing confidence in the "
        "extracted information, not confidence in document classification.\n\n"
        f"Classified document type: {bescheid_type}\n\n"
        f"Document:\n{text}"
    )

    extracted_data = await _run_extraction_prompt(
        prompt_text=prompt_text,
        json_schema=json_schema,
        model=model,
        session=session,
    )

    if not extracted_data:
        return {}

    return _normalize_extracted_data(
        extracted_data,
        bescheid_type,
    )
