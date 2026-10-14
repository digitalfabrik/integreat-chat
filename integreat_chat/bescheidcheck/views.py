"""
Views for the bescheidcheck app (issues #494, #495, #498).

Two endpoints under /bescheidcheck/:

- ``GET /bescheidcheck/``          -> the standalone user interface
- ``POST /bescheidcheck/analyze/`` -> full pipeline (OCR, translate,
                                        classify, RAG-based counseling
                                        lookup); stateless

The analyze endpoint is a synchronous request/response so the browser can
show a spinner for the duration it takes, without poll endpoints for
jobs (chosen during planning).

Counseling (issue #498) is now part of the analyze response:
the pipeline builds a generic question from the classified Bescheid
type ("Where can I find [Flüchtlingsberatung]?") and asks the existing
``AnswerService`` of the ``chatanswers`` app for an answer in the
user's region, which is then returned in the JSON response
("counseling" key).
"""

import json
import logging
import os
import re
import secrets
import shutil
import tempfile
import time

import aiohttp
from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from .services import (
    classification,
    counselor,
    extraction,
    ocr,
    page_order,
    translation,
)
from .services.sanitizer import sanitize_html

LOGGER = logging.getLogger(__name__)

ALLOWED_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".heic")
ALLOWED_PDF_EXT = ".pdf"


def _content_security_policy(nonce: str) -> str:
    """Build a per-request Content-Security-Policy for the bescheidcheck UI."""
    return (
        "default-src 'none'; "
        f"script-src 'nonce-{nonce}'; "
        "style-src 'unsafe-inline'; "
        "img-src data: blob:; "
        "connect-src 'self'; "
        "base-uri 'none'; "
        "form-action 'none'"
    )


def _slug_token(value: str) -> str:
    """
    Keep only ``[A-Za-z0-9-]`` in ``value`` and drop everything else.

    ``region_slug`` is reflected into SSE events that the UI splices into
    HTML, so it must be taint-cleaned at ingest (reflected-XSS).
    """
    return re.sub(r"[^A-Za-z0-9-]", "", value or "")


def ui(request):
    """
    Render the standalone user interface (issue #495).
    """
    counseling_regions = [
        {"slug": slug, "name": info.get("name", slug)}
        for slug, info in (settings.INTEGREAT_REGIONS or {}).items()
        if info.get("human_counseling")
    ]
    csp_nonce = secrets.token_urlsafe(16)
    response = render(
        request,
        "bescheidcheck/bescheidcheck.html",
        {
            "max_images": settings.BESCHEID_MAX_IMAGES,
            "max_pdf_pages": settings.BESCHEID_MAX_PDF_PAGES,
            "supported_languages": list(settings.TRANSLATION_MODEL_SUPPORTED_LANGUAGES),
            "supported_languages_js": json.dumps(
                settings.TRANSLATION_MODEL_SUPPORTED_LANGUAGES
            ),
            "counseling_regions": counseling_regions,
            "supported_types": settings.BESCHEID_SUPPORTED_TYPES,
            "csp_nonce": csp_nonce,
        },
    )
    response["Content-Security-Policy"] = _content_security_policy(csp_nonce)
    return response


def _safe_name(f) -> str:
    """
    Attacker-controlled ``f.name`` may carry ``..`` or ``/`` segments
    (path traversal). Strip any directory part and lower-case so the
    name is safe to join onto the temp dir and the duplicate check
    stays case-insensitive.
    """
    return os.path.basename((f.name or "upload").lower())


def _validate_files(files: list) -> None:
    """
    Raise ValueError with a user-facing message if the files are
    not acceptable. Returns nothing on success.
    """
    if not files:
        raise ValueError("Please upload at least one image or one PDF.")
    if len(files) > settings.BESCHEID_MAX_IMAGES:
        raise ValueError(
            f"You uploaded {len(files)} files; the maximum is "
            f"{settings.BESCHEID_MAX_IMAGES}."
        )
    seen = set()
    for f in files:
        name = _safe_name(f)
        ext = os.path.splitext(name)[1]
        if ext not in (*ALLOWED_IMAGE_EXTS, ALLOWED_PDF_EXT):
            raise ValueError(
                f"Unsupported file type: '{ext or '?'}'. "
                "Allowed: PNG, JPEG, HEIC, or PDF."
            )
        if name in seen:
            raise ValueError(f"Duplicate file name: '{name}'.")
        seen.add(name)
        size = getattr(f, "size", None)
        if size is not None and size > settings.BESCHEID_MAX_UPLOAD_BYTES:
            raise ValueError(
                f"File '{name}' is {size} bytes; the maximum is "
                f"{settings.BESCHEID_MAX_UPLOAD_BYTES}."
            )


def _extract_all_text(ocr_pages: list) -> str:
    """
    Concatenate the text of every page for the classification prompt.
    """
    from bs4 import BeautifulSoup

    parts: list[str] = []
    for page in ocr_pages:
        text = ""
        if page.paragraphs:
            text = "\n".join(p["text"] for p in page.paragraphs if p.get("text"))
        if not text:
            soup = BeautifulSoup(page.html, "lxml")
            text = soup.get_text() if soup is not None else ""
        parts.append(text.strip())
    return "\n\n".join(part for part in parts if part)


def _write_uploads_to(files: list, tmpdir: str) -> tuple[list[str], list[str]]:
    """
    Write the uploaded files to ``tmpdir`` and classify them as
    (image_paths, pdf_paths). Raises ValueError on any I/O error.
    """
    image_paths: list[str] = []
    pdf_paths: list[str] = []

    for f in files:
        name = _safe_name(f)
        ext = os.path.splitext(name)[1]
        dest = os.path.join(tmpdir, name)
        try:
            with open(dest, "wb") as out:
                out.writelines(f.chunks())
        except OSError as exc:
            LOGGER.warning("Failed to store upload '%s': %s", name, exc)
            raise ValueError(
                f"Failed to store the upload '{name}'. Please try again."
            ) from exc
        if ext == ALLOWED_PDF_EXT:
            pdf_paths.append(dest)
        elif ext in ALLOWED_IMAGE_EXTS:
            image_paths.append(dest)
        else:
            raise ValueError(f"Unsupported file type: '{ext}'.")
    return image_paths, pdf_paths


async def _run_ocr(files: list, tmpdir: str) -> list:
    """
    OCR all uploaded files (images or one PDF) in upload order.
    PDFs are split into 1-page PDFs and the pages are processed in that
    order. Images are processed in upload order.

    When ``settings.BESCHEID_PAGE_ORDERING`` is ``"llm"``, the OCR'd
    pages are additionally re-ordered into reading order via the LLM
    (see page_order.order_pages_with_llm); this happens *after* OCR
    because the LLM needs the extracted text as input. If the LLM
    returns a bad ordering the original upload order is kept.

    Docling is heavy and CPU/GPU bound; we call each conversion via
    sync_to_async(thread_sensitive=False) to release the event loop.
    """
    write_start = time.monotonic()
    image_paths, pdf_paths = await sync_to_async(
        _write_uploads_to, thread_sensitive=False
    )(files, tmpdir)
    LOGGER.info(
        "ocr: wrote %s files to disk in %.2fs (pdf=%s images=%s)",
        len(image_paths) + len(pdf_paths),
        round(time.monotonic() - write_start, 2),
        len(pdf_paths),
        len(image_paths),
    )

    ocr_pages: list = []
    next_page_no = 1
    remaining_pages = settings.BESCHEID_MAX_PDF_PAGES

    for pdf_index, pdf_path in enumerate(pdf_paths, start=1):
        if remaining_pages <= 0:
            break
        pages_dir = os.path.join(tmpdir, f"pages-{pdf_index}")
        os.makedirs(pages_dir, exist_ok=True)
        t0 = time.monotonic()
        page_paths = ocr.split_pdf_pages(
            pdf_path,
            max_num_pages=remaining_pages,
            out_dir=pages_dir,
        )
        LOGGER.info(
            "ocr: split PDF in %.2fs -> %s 1-page PDF(s)",
            round(time.monotonic() - t0, 2),
            len(page_paths),
        )
        for page_path in page_paths:
            if remaining_pages <= 0:
                break
            t0 = time.monotonic()
            ocr_page = await sync_to_async(ocr.convert_page, thread_sensitive=False)(
                page_path, page_no=next_page_no, max_num_pages=1
            )
            next_page_no += 1
            remaining_pages -= 1
            LOGGER.info(
                "ocr: converted page '%s' in %.2fs (%s paragraphs)",
                os.path.basename(page_path),
                round(time.monotonic() - t0, 2),
                len(ocr_page.paragraphs),
            )
            ocr_pages.append(ocr_page)

    for image_path in image_paths:
        if remaining_pages <= 0:
            break
        t0 = time.monotonic()
        ocr_page = await sync_to_async(ocr.convert_page, thread_sensitive=False)(
            image_path, page_no=next_page_no, max_num_pages=1
        )
        next_page_no += 1
        remaining_pages -= 1
        LOGGER.info(
            "ocr: converted image '%s' in %.2fs (%s paragraphs)",
            os.path.basename(image_path),
            round(time.monotonic() - t0, 2),
            len(ocr_page.paragraphs),
        )
        ocr_pages.append(ocr_page)

    if len(ocr_pages) >= 2:
        t0 = time.monotonic()
        async with aiohttp.ClientSession() as session:
            ocr_pages = await page_order.order_pages_with_llm(ocr_pages, session)
        LOGGER.info(
            "ocr: re-ordered %s pages via LLM in %.2fs",
            len(ocr_pages),
            round(time.monotonic() - t0, 2),
        )

    for index, page in enumerate(ocr_pages, start=1):
        page.page_no = index
    return ocr_pages


def sse_event(event: str, data: dict) -> str:
    """
    Encode a single Server-Sent Events frame.

    ``ensure_ascii=False`` so German umlauts render correctly; ``\\n\\n``
    terminates the frame.
    """
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _stage_event(payload: dict) -> str:
    """
    Convenience wrapper for stage-progress events.
    """
    return sse_event("stage", payload)


async def _analyze_stream(
    files: list, region_slug: str, target_language: str, tmpdir: str
):
    """
    Run the full bescheidcheck pipeline and yield Server-Sent Events as
    it progresses: ``stage`` events at each boundary, a single
    ``result`` event with the complete payload, or a single ``error``
    event on failure. ``tmpdir`` is always removed in ``finally``.
    """
    stages: dict[str, float] = {}
    start = time.monotonic()
    try:
        # -- stage 1: OCR ------------------------------------------------
        t0 = time.monotonic()
        yield _stage_event({"stage": "ocr", "index": 1, "status": "started"})
        try:
            ocr_pages = await _run_ocr(files, tmpdir)
        except (ValueError, RuntimeError) as exc:
            LOGGER.warning("OCR stage rejected the upload: %s", exc)
            yield sse_event(
                "error",
                {
                    "stage": "ocr",
                    "reason": (
                        "The document could not be processed. "
                        "Please try again with a valid PDF or set of "
                        "images."
                    ),
                },
            )
            return
        except Exception:
            LOGGER.exception("OCR stage failed")
            yield sse_event(
                "error",
                {
                    "stage": "ocr",
                    "reason": "OCR of the uploaded files failed. Please try again.",
                },
            )
            return
        ocr_elapsed = round(time.monotonic() - t0, 2)
        stages["ocr"] = ocr_elapsed
        LOGGER.info(
            "analyze: OCR stage finished in %.2fs (pages=%s paragraphs=%s)",
            ocr_elapsed,
            len(ocr_pages),
            sum(len(p.paragraphs) for p in ocr_pages),
        )
        yield _stage_event(
            {
                "stage": "ocr",
                "index": 1,
                "status": "done",
                "pages": len(ocr_pages),
                "paragraphs": sum(len(p.paragraphs) for p in ocr_pages),
                "seconds": ocr_elapsed,
            }
        )

        pages_html = [page.html for page in ocr_pages]

        yield sse_event(
            "pages",
            {
                "pages": [
                    {
                        "page_no": page.page_no,
                        "original_html": sanitize_html(page.html),
                        "translated_html": sanitize_html(page.html),
                        "paragraphs": page.paragraphs,
                    }
                    for page in ocr_pages
                ]
            },
        )

        t0 = time.monotonic()
        source_language = "de"
        yield _stage_event({"stage": "translate", "index": 2, "status": "started"})
        translations_by_page: list[dict] = [{} for _ in pages_html]
        paragraphs_done = 0
        try:
            async for para in translation.translate_document_stream(
                pages_html,
                source_language=source_language,
                target_language=target_language,
            ):
                page_idx = para["page"]
                para_id = para["para_id"]
                html = sanitize_html(para["html"])
                translations_by_page[page_idx][para_id] = html
                paragraphs_done += 1
                yield sse_event(
                    "para",
                    {
                        "page": page_idx,
                        "para_id": para_id,
                        "html": html,
                    },
                )
            translated_pages = [
                (
                    translation._rebuild_page_html(pages_html[i], trans)
                    if trans
                    else pages_html[i]
                )
                for i, trans in enumerate(translations_by_page)
            ]
        except Exception:
            LOGGER.exception("Translation stage failed; using original text")
            translated_pages = list(pages_html)

        tr_elapsed = round(time.monotonic() - t0, 2)
        stages["translate"] = tr_elapsed
        LOGGER.info(
            "analyze: translation finished in %.2fs (pages=%s "
            "source=%s target=%s streamed=%s)",
            tr_elapsed,
            len(translated_pages),
            source_language,
            target_language,
            paragraphs_done,
        )
        yield _stage_event(
            {
                "stage": "translate",
                "index": 2,
                "status": "done",
                "pages": len(translated_pages),
                "paragraphs": paragraphs_done,
                "seconds": tr_elapsed,
            }
        )

        t0 = time.monotonic()
        yield _stage_event({"stage": "classify", "index": 3, "status": "started"})
        try:
            full_text = _extract_all_text(ocr_pages)
            LOGGER.info("analyze: classification input is %s chars", len(full_text))
            async with aiohttp.ClientSession() as session:
                cls_result = await classification.classify_bescheid(
                    full_text, session=session
                )
        except Exception:
            LOGGER.exception("Classification stage failed")
            cls_result = {
                "type": "unsupported",
                "confidence": 0.0,
                "reason": (
                    "Classification failed. The document could not be "
                    "typed, so a specific counseling lookup was not run. "
                    "Please try again or contact your local counseling "
                    "office directly."
                ),
            }
        cls_elapsed = round(time.monotonic() - t0, 2)
        stages["classify"] = cls_elapsed
        LOGGER.info(
            "analyze: classification finished in %.2fs (type=%s confidence=%s)",
            cls_elapsed,
            cls_result.get("type"),
            cls_result.get("confidence"),
        )
        yield _stage_event(
            {
                "stage": "classify",
                "index": 3,
                "status": "done",
                "type": cls_result.get("type"),
                "confidence": cls_result.get("confidence"),
                "seconds": cls_elapsed,
            }
        )

        t0 = time.monotonic()
        yield _stage_event({"stage": "extraction", "index": 4, "status": "started"})

        extracted_data = await extraction.extract_structured_data(
            document_text=full_text,
            bescheid_type=cls_result.get("type", "unsupported"),
            model=settings.BESCHEID_CLASSIFICATION_MODEL,
        )

        extraction_elapsed = round(time.monotonic() - t0, 2)
        stages["extraction"] = extraction_elapsed

        LOGGER.info(
            "analyze: extraction finished in %.2fs",
            extraction_elapsed,
        )

        yield _stage_event(
            {
                "stage": "extraction",
                "index": 4,
                "status": "done",
                "seconds": extraction_elapsed,
            }
        )

        t0 = time.monotonic()
        yield _stage_event({"stage": "counseling", "index": 5, "status": "started"})
        counseling = None
        try:
            counseling = await counselor.find_counseling(
                region_slug=region_slug,
                bescheid_type=cls_result.get("type", "unsupported"),
                target_language=target_language,
            )
        except Exception:
            LOGGER.exception("Counseling (RAG) failed; returning an empty block")
            counseling = None
        else:
            if counseling is not None:
                LOGGER.info(
                    "analyze: counseling ready (automatic_answers=%s)",
                    counseling.get("automatic_answers"),
                )
        co_elapsed = round(time.monotonic() - t0, 2)
        stages["counseling"] = co_elapsed
        LOGGER.info("analyze: counseling finished in %.2fs", co_elapsed)
        yield _stage_event(
            {
                "stage": "counseling",
                "index": 5,
                "status": "done",
                "seconds": co_elapsed,
            }
        )

        total_elapsed = round(time.monotonic() - start, 2)
        LOGGER.info(
            "analyze: done in %.2fs total (stages: %s)",
            total_elapsed,
            stages,
        )

        result_payload = {
            "status": "success",
            "classification": cls_result,
            "extracted_data": extracted_data,
            "source_language": source_language,
            "target_language": target_language,
            "region": region_slug,
            "counseling": counseling,
            "pages": [
                {
                    "page_no": page.page_no,
                    "original_html": sanitize_html(page.html),
                    "translated_html": sanitize_html(translated_pages[i]),
                    "paragraphs": page.paragraphs,
                }
                for i, page in enumerate(ocr_pages)
            ],
            "stages": stages,
            "total_seconds": total_elapsed,
        }
        yield sse_event("result", result_payload)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@csrf_exempt
async def analyze(request):
    """
    Run the full bescheidcheck pipeline (OCR, classify, translate, and
    RAG-based counseling lookup).

    Input validation failures return plain ``JsonResponse`` (404/422);
    otherwise the pipeline streams ``stage`` / ``result`` / ``error``
    SSE events (see ``_analyze_stream``).
    """
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "reason": "Method not allowed. Use POST."},
            status=405,
        )

    region_slug = _slug_token(request.POST.get("region") or "")
    target_language = _slug_token(request.POST.get("target_language") or "")
    files: list = []
    for _key, uploads in request.FILES.lists():
        if isinstance(uploads, (list, tuple)):
            files.extend(uploads)
        else:
            files.append(uploads)

    if region_slug not in (settings.INTEGREAT_REGIONS or {}):
        return JsonResponse(
            {
                "status": "error",
                "reason": "Unknown region. Please pick a valid region.",
            },
            status=404,
        )
    if (
        not target_language
        or target_language not in settings.TRANSLATION_MODEL_SUPPORTED_LANGUAGES
    ):
        return JsonResponse(
            {
                "status": "error",
                "reason": (
                    "The selected target language is not supported. "
                    "Please choose one of the languages in the form."
                ),
            },
            status=422,
        )
    try:
        _validate_files(files)
    except ValueError as exc:
        LOGGER.warning("File validation failed: %s", exc)
        return JsonResponse(
            {
                "status": "error",
                "reason": (
                    "The uploaded files could not be validated. "
                    "Please check the list of supported file types "
                    "(PNG, JPEG, HEIC, PDF) and the maximum file "
                    "count, and retry."
                ),
            },
            status=422,
        )

    LOGGER.info(
        "analyze: starting pipeline (files=%s region=%s target_language=%s)",
        len(files),
        region_slug,
        target_language,
    )

    tmpdir = tempfile.mkdtemp(prefix="bescheidcheck-")
    response = StreamingHttpResponse(
        _analyze_stream(files, region_slug, target_language, tmpdir),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    response["Connection"] = "keep-alive"
    return response
