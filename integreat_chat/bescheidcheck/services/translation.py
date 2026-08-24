"""
Translation service for the bescheidcheck pipeline (issue #493).

Takes the per-page HTML produced by the OCR pipeline and translates
each <p data-para-id=...> paragraph to the target language,
preserving the para id and the bounding-box attributes so the browser
can keep the highlight overlay aligned.

Docling's HTML fallback for photos (see ocr.convert_page) also carries
``data-para-id`` (shape p-<page>-fallback-<i>) on each <p>, so those
pages remain translatable; those paragraphs carry no bounding boxes,
so highlight overlays are unavailable for them.

We reuse the existing LanguageService for the LLM call (it already
handles caching, URL sanitization, and the keep_html flag).
"""

import asyncio
import logging
import re
import time

import aiohttp
from bs4 import BeautifulSoup
from django.conf import settings

from integreat_chat.chatanswers.services.llmapi import LlmClientError
from integreat_chat.translate.services.language import LanguageService

LOGGER = logging.getLogger(__name__)

MAX_CONCURRENT_TRANSLATIONS = int(
    getattr(settings, "BESCHEID_TRANSLATION_CONCURRENCY", 4)
)

# Matches digits, whitespace, common numeric punctuation / currency symbols.
_NUM_RE = re.compile(r"^[0-9\s+\.\,\:;%€\$/\-]*$")


def _extract_paragraphs(page_html: str) -> list[dict]:
    """
    Parse a page HTML string into a list of paragraph dicts
    with id + body (body keeps inner markup).
    """
    soup = BeautifulSoup(page_html, "lxml")
    paragraphs: list[dict] = []
    for p in soup.find_all("p"):
        para_id = p.get("data-para-id")
        if para_id is None:
            continue
        body = p.decode_contents()
        paragraphs.append({"id": para_id, "body": body})
    return paragraphs


def _rebuild_page_html(
    page_html: str,
    translations: dict[str, str],
) -> str:
    """
    Replace <p> bodies with translated content, keeping all attributes.
    Paragraphs that have no translation are left untouched.

    Translations may contain HTML (keep_html=True), so the replacement
    is parsed as a fragment and spliced into the element.
    """
    soup = BeautifulSoup(page_html, "lxml")
    for p in soup.find_all("p"):
        para_id = p.get("data-para-id")
        if para_id is None or para_id not in translations:
            continue
        p.clear()
        # BeautifulSoup's Tag has no set-inner-html helper, so parse a
        # wrapper <span> and move the inner content out.
        wrapper = BeautifulSoup(f"<span>{translations[para_id]}</span>", "lxml")
        for child in list(wrapper.span.children):
            node = child.extract() if hasattr(child, "extract") else child
            p.append(node)
    return str(soup)


def _needs_translation(body: str) -> bool:
    """
    Skip translation for empty / purely numerical bodies.
    """
    text = " ".join(body.split())
    if not text:
        return False
    return not _NUM_RE.match(text)


async def _translate_one_paragraph(
    language_service: LanguageService,
    session: aiohttp.ClientSession,
    source_language: str,
    target_language: str,
    para_id: str,
    body: str,
) -> tuple[str, str] | None:
    """
    Translate one paragraph. Returns (para_id, translated_html) or None
    if no translation was needed.

    A paragraph can transiently time out when the shared model worker is
    busy: retry once with a short backoff, then keep the original text
    so nothing is lost.
    """
    try:
        translated = await language_service.translate_message(
            source_language,
            target_language,
            body,
            keep_html=True,
            session=session,
        )
    except ValueError as exc:
        LOGGER.warning("Skipping translation of paragraph %s: %s", para_id, exc)
        return None
    except TimeoutError as exc:
        LOGGER.warning(
            "Timeout translating paragraph %s, retrying once: %s", para_id, exc
        )
        try:
            await asyncio.sleep(1.0)
            translated = await language_service.translate_message(
                source_language,
                target_language,
                body,
                keep_html=True,
                session=session,
            )
        except TimeoutError as retried_exc:
            LOGGER.warning(
                "Paragraph %s still failed after retry (%s); keeping original text",
                para_id,
                retried_exc,
            )
            return None
    return (para_id, translated)


async def translate_page(
    page_html: str,
    source_language: str,
    target_language: str,
    session: aiohttp.ClientSession | None = None,
    language_service: LanguageService | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> str:
    """
    Translate one page's HTML from source to target language,
    preserving <p data-para-id=...> ids and their attributes.

    param page_html: HTML string of one page (from OCR pipeline)
    param source_language: BCP-47 source language (e.g. "de")
    param target_language: BCP-47 target language
    param session: optional shared aiohttp session
    param language_service: optional reused LanguageService instance
    param semaphore: optional shared concurrency gate; when omitted one
        is created locally for this page. Pass the same instance across
        concurrent page calls to cap *total* in-flight LLM calls.
    return: translated HTML string (or unchanged HTML on no-op)
    """
    if source_language == target_language:
        return page_html

    language_service = language_service or LanguageService()
    if session is None:
        async with aiohttp.ClientSession() as owned_session:
            return await translate_page(
                page_html,
                source_language,
                target_language,
                owned_session,
                language_service,
            )

    paragraphs = _extract_paragraphs(page_html)
    if not paragraphs:
        LOGGER.info("translate_page: nothing to do (no <p data-para-id>)")
        return page_html

    todo = [(p["id"], p["body"]) for p in paragraphs if _needs_translation(p["body"])]
    if not todo:
        LOGGER.info(
            "translate_page: %s paragraph(s) but none need translation",
            len(paragraphs),
        )
        return page_html

    semaphore = semaphore or asyncio.Semaphore(MAX_CONCURRENT_TRANSLATIONS)

    async def _limited(para_id: str, body: str) -> tuple[str, str] | None:
        async with semaphore:
            started = time.monotonic()
            try:
                result = await _translate_one_paragraph(
                    language_service,
                    session,
                    source_language,
                    target_language,
                    para_id,
                    body,
                )
            finally:
                LOGGER.info(
                    "translate: paragraph %s took %.2fs (len=%s)",
                    para_id,
                    round(time.monotonic() - started, 2),
                    len(body),
                )
            return result

    started = time.monotonic()
    tasks = [_limited(para_id, body) for para_id, body in todo]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    LOGGER.info(
        "translate_page: translated %s/%s paragraph(s) in %.2fs",
        sum(1 for r in results if isinstance(r, tuple)),
        len(todo),
        round(time.monotonic() - started, 2),
    )

    translations: dict[str, str] = {}
    for res in results:
        if isinstance(res, Exception):
            LOGGER.warning("A paragraph raised unexpectedly, skipping it: %s", res)
            continue
        if res is None:
            continue
        para_id, translated = res
        translations[para_id] = translated

    if not translations:
        return page_html

    return _rebuild_page_html(page_html, translations)


async def translate_page_stream(
    page_html: str,
    source_language: str,
    target_language: str,
    session: aiohttp.ClientSession,
    language_service: LanguageService,
):
    """
    Async generator: translate one page's paragraphs and yield ``(para_id,
    translated_html)`` for each paragraph **as soon as its LLM call
    completes** (so a front end can stream the result paragraph-by-
    paragraph), while preserving the same per-paragraph reliability
    guarantees as ``translate_page``:

    * at most ``MAX_CONCURRENT_TRANSLATIONS`` LLM calls in flight;
    * one retry on a transient timeout;
    * a paragraph that ultimately fails is skipped (left in its original
      text) and never sinks the page.
    """
    if source_language == target_language:
        return

    todos = []
    for p in _extract_paragraphs(page_html):
        if _needs_translation(p["body"]):
            todos.append((p["id"], p["body"]))

    if not todos:
        LOGGER.info(
            "translate_page_stream: %s paragraph(s) but none need translation",
            len(_extract_paragraphs(page_html)),
        )
        return
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TRANSLATIONS)

    tasks = []
    for para_id, body in todos:

        async def _run(pid=para_id, b=body):
            async with semaphore:
                started = time.monotonic()
                try:
                    return await _translate_one_paragraph(
                        language_service,
                        session,
                        source_language,
                        target_language,
                        pid,
                        b,
                    )
                finally:
                    LOGGER.info(
                        "translate: paragraph %s took %.2fs (len=%s)",
                        pid,
                        round(time.monotonic() - started, 2),
                        len(b),
                    )

        tasks.append(asyncio.ensure_future(_run()))

    try:
        for fut in asyncio.as_completed(tasks):
            try:
                res = await fut
            except LlmClientError as exc:
                LOGGER.warning(
                    "A paragraph failed (LLM server error); skipping it: %s", exc
                )
                continue
            except (aiohttp.ClientError, OSError, ValueError, TimeoutError) as exc:
                LOGGER.warning("A paragraph failed; skipping it: %s", exc)
                continue
            if res is None:
                continue
            yield res
    finally:
        for fut in tasks:
            if not fut.done():
                fut.cancel()


async def translate_document_stream(
    pages: list[str],
    source_language: str,
    target_language: str,
):
    """
    Translate a multi-page document and **yield** each finished paragraph
    as soon as it completes, in the form
    ``{"page": int, "para_id": str, "html": str}``.

    Pages are translated in order (so the user sees page 1 complete before
    page 2 starts), but inside a page the paragraphs complete in
    completion order (governed by ``MAX_CONCURRENT_TRANSLATIONS``) so the
    first N finished paragraphs stream out even while later ones are still
    in flight.

    ``page`` is the 0-based index into the input ``pages`` list; the
    caller owns both the source and translated sides of the document, so
    it can look up the original page by the same index and apply the
    paragraph (per ``para_id``) at the end to produce that page's
    finished HTML.

    param pages: list of per-page original HTML strings (in reading order)
    param source_language: BCP-47 source language
    param target_language: BCP-47 target language
    return: AsyncIterator[dict]  (an async generator, not a coroutine)
    """
    if source_language == target_language:
        return

    language_service = LanguageService()
    async with aiohttp.ClientSession() as session:
        for page_idx, page_html in enumerate(pages):
            async for para_id, html in translate_page_stream(
                page_html,
                source_language,
                target_language,
                session,
                language_service,
            ):
                yield {"page": page_idx, "para_id": para_id, "html": html}


async def translate_document(
    pages: list[str],
    source_language: str,
    target_language: str,
) -> list[str]:
    """
    Translate the HTML of every page of a document.

    param pages: list of per-page HTML strings (in reading order)
    param source_language: BCP-47 source language
    param target_language: BCP-47 target language
    return: list of translated per-page HTML strings (same length as input)
    """
    if source_language == target_language:
        return list(pages)
    started = time.monotonic()
    language_service = LanguageService()
    shared_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TRANSLATIONS)
    async with aiohttp.ClientSession() as session:
        tasks = [
            translate_page(
                page_html,
                source_language,
                target_language,
                session=session,
                language_service=language_service,
                semaphore=shared_semaphore,
            )
            for page_html in pages
        ]
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        pages_out = [
            original if isinstance(result, Exception) else result
            for original, result in zip(pages, raw)
        ]
    LOGGER.info(
        "translate_document: %s page(s) in %.2fs (source=%s target=%s)",
        len(pages_out),
        round(time.monotonic() - started, 2),
        source_language,
        target_language,
    )
    return pages_out
