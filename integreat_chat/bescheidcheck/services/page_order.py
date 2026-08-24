"""
Page ordering for the bescheidcheck pipeline.

Pages arrive in caller order (PDF pages split into 1-page files, images
in upload order).

When ``settings.BESCHEID_PAGE_ORDERING`` is ``"llm"``, the LLM reads
short per-page summaries and proposes a reading order. This happens
after OCR (the text is the prompt input). A malformed response
(wrong length, missing numbers, ...) falls back to the original order.
"""

import logging

import aiohttp
from django.conf import settings

from integreat_chat.chatanswers.services.llmapi import (
    LlmApiClient,
    LlmMessage,
    LlmPrompt,
    LlmResponse,
)

from ..static.prompts import Prompts

LOGGER = logging.getLogger(__name__)


def _page_summary_from_paragraphs(paragraphs: list[dict]) -> str:
    """
    Build a short per-page summary from the OCR paragraphs of one page
    (joined text, truncated to 500 characters).
    """
    texts = [p.get("text", "") for p in paragraphs if p.get("text")]
    joined = " ".join(t.strip() for t in texts).strip()
    if len(joined) > 500:
        joined = joined[:500] + "…"
    return joined


async def order_with_llm(
    page_summaries: list[str], session: aiohttp.ClientSession
) -> list[int] | None:
    """
    Ask the LLM to reorder pages into reading order.

    param page_summaries: per-page short text summaries (one per page,
        in the current order)
    param session: shared aiohttp session
    return: list of 0-based indices indicating the new order, or ``None``
        if the LLM could not or did not produce a sensible ordering.
    """
    joined = "\n---\n".join(
        f"[page {i + 1}]\n{summary}" for i, summary in enumerate(page_summaries)
    )
    prompt = LlmPrompt(
        settings.BESCHEID_CLASSIFICATION_MODEL,
        [
            LlmMessage(
                Prompts.PAGE_ORDERING.format(joined, str(len(page_summaries))),
                role="user",
            )
        ],
    )
    llm = LlmApiClient()
    response = LlmResponse(await llm.chat_prompt(session, prompt))
    text = str(response).strip()

    # Models sometimes append trailing tokens, so walk the lines from the
    # end and use the last one that parses as a full permutation of
    # {1..n}; anything else keeps the original order.
    expected_1based = set(range(1, len(page_summaries) + 1))
    for line in reversed(text.splitlines()):
        line = line.strip().strip(",")
        if not line:
            continue
        pieces = [part.strip() for part in line.split(",") if part.strip()]
        try:
            numbers = [int(p) for p in pieces]
        except ValueError:
            continue
        if set(numbers) == expected_1based and len(numbers) == len(expected_1based):
            return [n - 1 for n in numbers]
    LOGGER.warning(
        "LLM page ordering response %r does not contain a valid "
        "permutation of %s; keeping the original order",
        text[:200],
        sorted(expected_1based),
    )
    return None


async def order_pages_with_llm(pages: list, session: aiohttp.ClientSession) -> list:
    """
    Reorder ``pages`` (list of OcrPage or any object with a
    ``paragraphs`` attribute) into the LLM's suggested reading order.

    If ``settings.BESCHEID_PAGE_ORDERING`` is not ``"llm"``, or if the
    LLM call fails / returns a bad ordering, this returns the input
    list unchanged. The input list is not mutated; a new list is
    returned.
    """
    strategy = getattr(settings, "BESCHEID_PAGE_ORDERING", "off")
    if strategy != "llm":
        return list(pages)
    if len(pages) < 2:
        return list(pages)

    summaries = [_page_summary_from_paragraphs(p.paragraphs) for p in pages]
    try:
        new_order = await order_with_llm(summaries, session)
    except Exception:
        LOGGER.exception("LLM page ordering call failed; keeping original page order")
        return list(pages)

    if new_order is None or len(new_order) != len(pages):
        return list(pages)
    return [pages[i] for i in new_order]
