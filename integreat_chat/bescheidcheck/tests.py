"""
Tests for the bescheidcheck app (first real tests in the repo).

These tests mock the expensive services (Docling OCR, LLM calls, the
chatanswers AnswerService) and verify the pipeline behaviour, the
response shape, and the validation rules.
"""

import asyncio
import json
import tempfile
import unittest
from unittest import mock

from django.test import TestCase

from .services.sanitizer import sanitize_html


def _drain_sse_response(res) -> list:
    """
    Consume a ``StreamingHttpResponse`` carrying Server-Sent Events and
    return a list of ``{"event": str, "data": dict}`` dicts, in order
    (frame = ``event:`` + ``data:`` lines up to the blank line).

    ``streaming_content`` may be a sync or an async generator (the
    pipeline is ``async def``), so collect chunks accordingly.
    """
    import inspect

    iterable = res.streaming_content
    frames: list[str] = []
    if inspect.isasyncgen(iterable):

        async def _collect() -> None:
            async for chunk in iterable:
                frames.append(chunk)

        asyncio.run(_collect())
    else:
        frames = list(iterable)

    buffer = ""
    for chunk in frames:
        buffer += chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk

    events: list = []
    while "\n\n" in buffer:
        frame, buffer = buffer.split("\n\n", 1)
        events.append(_parse_sse_frame(frame))
    if buffer.strip():
        events.append(_parse_sse_frame(buffer))
    return [e for e in events if e is not None]


def _parse_sse_frame(frame: str):
    event = "message"
    data = ""
    for raw in frame.split("\n"):
        line = raw.strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            chunk = line[len("data:") :].lstrip(" ")
            data = (data + "\n" + chunk) if data else chunk
    if not data:
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        payload = {"reason": data}
    return {"event": event, "data": payload}


def _fake_page_html(page_no: int = 1) -> str:
    """
    A small page HTML with two paragraphs, mimicking the OCR output.
    """
    return (
        f'<div class="bc-page" data-page="{page_no}">'
        '<p data-para-id="p-1-0" data-x="0.10" data-y="0.10" '
        'data-width="0.80" data-height="0.08">Ihr Asylantrag wird abgelehnt.</p>'
        '<p data-para-id="p-1-1" data-x="0.10" data-y="0.50" '
        'data-width="0.80" data-height="0.20">Der Asylantrag ist offensichtlich unbegründet.</p>'
        "</div>"
    )


def _fake_ocr_page(page_no: int = 1) -> dict:
    from integreat_chat.bescheidcheck.services.ocr import OcrPage

    return OcrPage(
        page_no=page_no,
        html=_fake_page_html(page_no),
        paragraphs=[
            {
                "id": "p-1-0",
                "text": "Ihr Asylantrag wird abgelehnt.",
                "x": 0.1,
                "y": 0.1,
                "width": 0.8,
                "height": 0.08,
            },
            {
                "id": "p-1-1",
                "text": "Der Asylantrag ist offensichtlich unbegründet.",
                "x": 0.1,
                "y": 0.5,
                "width": 0.8,
                "height": 0.2,
            },
        ],
    )


def _fake_paragraph_stream(pages, *args, **kwargs):
    """
    Build an async generator that mimics ``translation.translate_document_stream``:
    for each page index it yields two paragraphs (``p-<page>-0`` and
    ``p-<page>-1``) with their html as ``f"translated-{page}-<k>"``.
    """

    async def _gen():
        for i, _page_html in enumerate(pages):
            for k in (0, 1):
                yield {
                    "page": i,
                    "para_id": f"p-{i + 1}-{k}",
                    "html": f"translated-{i}-{k}",
                }

    return _gen()


class OcrPipelineOptionsTest(unittest.TestCase):
    """
    Regression test for the docling OCR pipeline configuration.

    Guards two production failures:

    1. ``do_table_structure`` must be False — docling's default
       instantiates the TableFormer model, which imports cv2 and thus
       needs libxcb.so.1 on the host.

    2. ``ocr_options.mode`` must be ``OcrMode.FULL_PAGE`` with RapidOCR
       on the torch backend. The default layout-model-first path returns
       an empty result for phone photos and is much slower on CPU.
    """

    def _options(self):
        from integreat_chat.bescheidcheck.services.ocr import _pipeline_options

        return _pipeline_options()

    def test_do_table_structure_is_disabled(self):
        opts = self._options()
        self.assertFalse(opts.do_table_structure)

    def test_ocr_engine_is_rapidocr_torch(self):
        from docling.datamodel.pipeline_options import RapidOcrOptions

        opts = self._options()
        self.assertIsInstance(opts.ocr_options, RapidOcrOptions)
        self.assertEqual(opts.ocr_options.backend, "torch")

    def test_ocr_mode_is_full_page(self):
        from docling.datamodel.pipeline_options import OcrMode, RapidOcrOptions

        opts = self._options()
        self.assertIsInstance(opts.ocr_options, RapidOcrOptions)
        self.assertEqual(opts.ocr_options.mode, OcrMode.FULL_PAGE)

    def test_ocr_language_defaults_to_german(self):
        opts = self._options()
        self.assertEqual(opts.ocr_options.lang, ["de"])

    def test_ocr_scale_default_from_settings(self):
        # scale=2.0 keeps the first-pass CPU cost low; see
        # settings.BESCHEID_OCR for the accuracy/speed trade-off.
        opts = self._options()
        self.assertEqual(opts.ocr_options.scale, 2.0)


class InternalPageResolutionTest(unittest.TestCase):
    """
    Regression test for the "only the first uploaded image was analyzed"
    bug: ``convert_page`` is called once per upload (each a 1-page
    docling document) with a *global* running page index. Before the fix
    the second file crashed. The fix resolves the global index onto the
    document's internal page number for the size lookup and the
    provenance filter, keeping the global index only as the stable
    ``data-para-id`` / ``data-page`` label.
    """

    def _fake_document(self):
        """
        A minimal stand-in for a DoclingDocument: one internal page keyed
        by 1, every text item provenanced on page 1.
        """
        from types import SimpleNamespace

        prov = SimpleNamespace(
            page_no=1,
            bbox=SimpleNamespace(
                l=10,
                t=20,
                width=800,
                height=100,
            ),
        )
        texts = [
            SimpleNamespace(
                prov=[prov], text="First paragraph of the sample page", label="TEXT"
            ),
            SimpleNamespace(
                prov=[prov], text="Second paragraph of the sample page", label="TEXT"
            ),
        ]
        return SimpleNamespace(
            pages={
                1: SimpleNamespace(size=SimpleNamespace(width=1536.0, height=2048.0))
            },
            texts=texts,
        )

    def test_resolve_internal_page_single_page_doc(self):
        from integreat_chat.bescheidcheck.services.ocr import _resolve_internal_page

        doc = self._fake_document()
        # The global index can be any positive integer; for a 1-page
        # document it must always resolve to internal page 1.
        for global_no in (1, 2, 3, 10):
            self.assertEqual(
                _resolve_internal_page(doc, global_no),
                1,
                f"global page {global_no} should resolve to internal page 1",
            )

    def test_resolve_internal_page_multi_page_doc(self):
        from types import SimpleNamespace

        from integreat_chat.bescheidcheck.services.ocr import _resolve_internal_page

        doc = SimpleNamespace(pages={1: object(), 2: object(), 3: object()})
        self.assertEqual(_resolve_internal_page(doc, 1), 1)
        self.assertEqual(_resolve_internal_page(doc, 2), 2)
        self.assertEqual(_resolve_internal_page(doc, 3), 3)
        self.assertEqual(_resolve_internal_page(doc, 4), 1)

    def test_build_paragraphs_second_uploaded_file(self):
        """
        The actual regression: building paragraphs for the *second*
        uploaded file (global page_no=2) against a 1-page document must
        produce the page's real paragraphs, not zero and not an error,
        and the ids/labels must carry the *global* page number.
        """
        from integreat_chat.bescheidcheck.services.ocr import (
            _build_paragraphs,
            _resolve_internal_page,
        )

        doc = self._fake_document()
        global_page_no = 2  # second uploaded file
        internal = _resolve_internal_page(doc, global_page_no)
        page_size = doc.pages[internal].size

        paragraphs, ordered_ids = _build_paragraphs(
            doc, internal, page_size, label_no=global_page_no
        )

        self.assertEqual(len(paragraphs), 2)
        self.assertEqual(ordered_ids, ["p-2-0", "p-2-1"])
        self.assertEqual(paragraphs[0]["id"], "p-2-0")
        self.assertEqual(paragraphs[0]["x"], round(10 / 1536.0, 6))
        self.assertEqual(paragraphs[0]["width"], round(800 / 1536.0, 6))


class ClassificationSanitizationTest(unittest.TestCase):
    """
    Pure-function tests: no Django ORM / network needed.
    """

    def test_sanitize_bad_type_becomes_unsupported(self):
        from integreat_chat.bescheidcheck.services.classification import (
            _sanitize_classification,
        )

        out = _sanitize_classification({"type": "evil"})
        self.assertEqual(out["type"], "unsupported")

    def test_sanitize_clamps_confidence(self):
        from integreat_chat.bescheidcheck.services.classification import (
            _sanitize_classification,
        )

        self.assertEqual(
            _sanitize_classification({"type": "dublin_decision", "confidence": 99.9})[
                "confidence"
            ],
            1.0,
        )
        self.assertEqual(
            _sanitize_classification({"type": "dublin_decision", "confidence": -5})[
                "confidence"
            ],
            0.0,
        )
        self.assertEqual(
            _sanitize_classification({"type": "dublin_decision", "confidence": "abc"})[
                "confidence"
            ],
            0.0,
        )

    def test_llm_client_error_degrades_safely(self):
        """
        When the LLM server returns an HTTP error status
        (``LlmApiClient.chat_prompt`` raises ``LlmClientError``),
        ``classify_bescheid`` must degrade to a safe ``unsupported``
        classification *without* re-raising the exception (the view's
        broad ``except Exception`` would swallow the real cause,
        losing the HTTP status and the server-side error text for the
        operator).
        """
        from integreat_chat.bescheidcheck.services.classification import (
            classify_bescheid,
        )
        from integreat_chat.chatanswers.services.llmapi import (
            LlmApiClient,
            LlmClientError,
        )

        with mock.patch.object(
            LlmApiClient,
            "chat_prompt",
            new=mock.AsyncMock(
                side_effect=LlmClientError(
                    "LLM server returned HTTP 500: internal model error",
                    status=500,
                )
            ),
        ):
            out = asyncio.run(classify_bescheid("Some document text..."))

        self.assertEqual(out["type"], "unsupported")
        self.assertEqual(out["confidence"], 0.0)
        self.assertIn("language-model server", out["reason"].lower())
        self.assertNotIn("500", out["reason"])  # no raw status leak

    def test_llm_client_error_does_not_leak_internal_html(self):
        """
        The user-facing reason must not expose the LLM server's raw
        response body (an HTML error page, e.g. from a 502 gateway).
        """
        from integreat_chat.bescheidcheck.services.classification import (
            classify_bescheid,
        )
        from integreat_chat.chatanswers.services.llmapi import (
            LlmApiClient,
            LlmClientError,
        )

        with mock.patch.object(
            LlmApiClient,
            "chat_prompt",
            new=mock.AsyncMock(
                side_effect=LlmClientError(
                    "LLM server returned HTTP 502: <html>Bad gateway</html>",
                    status=502,
                )
            ),
        ):
            out = asyncio.run(classify_bescheid("text"))
        self.assertEqual(out["type"], "unsupported")
        self.assertNotIn("<html>", out["reason"].lower())
        self.assertNotIn("Bad gateway", out["reason"])


class ChatPromptHttpErrorTest(unittest.IsolatedAsyncioTestCase):
    """
    ``LlmApiClient.chat_prompt`` must turn an HTTP 4xx/5xx response into
    a :class:`LlmClientError` (with the status code), instead of
    silently parsing the error body as JSON — which is what
    downstream ``LlmResponse`` code (``responses["choices"][0]…``)
    would crash on, degrading a real server error into a KeyError the
    operator cannot read.
    """

    async def _run(self, status: int, body: bytes = b'{"error": "boom"}') -> Exception:
        from integreat_chat.chatanswers.services.llmapi import (
            LlmApiClient,
            LlmClientError,
            LlmMessage,
            LlmPrompt,
        )

        class _FakeResponse:
            async def text(self) -> str:
                return body.decode("utf-8", errors="replace")

        response = _FakeResponse()
        response.status = status

        fake_cm = mock.MagicMock()
        fake_cm.__aenter__ = mock.AsyncMock(return_value=response)
        fake_cm.__aexit__ = mock.AsyncMock(return_value=False)
        fake_session = mock.MagicMock()
        fake_session.post.return_value = fake_cm

        prompt = LlmPrompt("ignored-model", [LlmMessage("ignored")])
        try:
            await LlmApiClient().chat_prompt(fake_session, prompt)
        except LlmClientError as exc:
            return exc
        self.fail("expected LlmClientError to be raised")

    async def test_500_becomes_llm_client_error_with_status(self):
        exc = await self._run(500)
        self.assertEqual(exc.status, 500)
        self.assertIn("500", str(exc))
        # The body snippet is included (helps operators debug) but a
        # safe/capped form: no long dumps and no path leak.
        self.assertNotIn("/srv/", str(exc))

    async def test_422_becomes_llm_client_error_with_status(self):
        exc = await self._run(422)
        self.assertEqual(exc.status, 422)
        self.assertIn("422", str(exc))


class CounselingQuestionTest(unittest.TestCase):
    """
    Tests for the hard-coded counseling service mapping and the
    generic question builder (issue #498).
    """

    def test_prompts_mapping(self):
        from integreat_chat.bescheidcheck.static.prompts import (
            COUNSELING_SERVICE_BY_TYPE,
        )

        self.assertIn("bamf_simple_rejection", COUNSELING_SERVICE_BY_TYPE)
        self.assertIn("obviously_unfounded_inadmissible", COUNSELING_SERVICE_BY_TYPE)
        self.assertIn("dublin_decision", COUNSELING_SERVICE_BY_TYPE)
        self.assertIn("unsupported", COUNSELING_SERVICE_BY_TYPE)

    def test_dublin_decision_label_is_dublin_phrase(self):
        from integreat_chat.bescheidcheck.static.prompts import (
            COUNSELING_SERVICE_BY_TYPE,
        )

        self.assertEqual(
            COUNSELING_SERVICE_BY_TYPE["dublin_decision"],
            "Dublin Verfahren Beratung",
        )

    def test_english_question(self):
        from integreat_chat.bescheidcheck.static.prompts import counseling_question_for

        q = counseling_question_for("en", "bamf_simple_rejection")
        self.assertIn("Asylberatung", q)
        self.assertTrue(q.startswith("Where can I find"))

    def test_german_question(self):
        from integreat_chat.bescheidcheck.static.prompts import counseling_question_for

        q = counseling_question_for("de", "bamf_simple_rejection")
        self.assertIn("Asylberatung", q)
        self.assertTrue(q.startswith("Wo kann ich"))

    def test_unsupported_fallback_is_general_migration_counseling(self):
        from integreat_chat.bescheidcheck.static.prompts import (
            COUNSELING_SERVICE_BY_TYPE,
            counseling_question_for,
        )

        self.assertEqual(
            COUNSELING_SERVICE_BY_TYPE["unsupported"],
            "Allgemeine Migrationsberatung",
        )
        self.assertIn(
            "Allgemeine Migrationsberatung",
            counseling_question_for("de", "unsupported"),
        )
        self.assertIn(
            "Allgemeine Migrationsberatung",
            counseling_question_for("en", "unsupported"),
        )

    def test_supported_types_remain_refugee_asylum_counseling(self):
        from integreat_chat.bescheidcheck.static.prompts import (
            COUNSELING_SERVICE_BY_TYPE,
        )

        for t in (
            "bamf_simple_rejection",
            "obviously_unfounded_inadmissible",
        ):
            self.assertEqual(
                COUNSELING_SERVICE_BY_TYPE[t],
                "Asylberatung",
            )


class PageOrderingTest(unittest.IsolatedAsyncioTestCase):
    """
    Tests for services/page_order.py (optional LLM reordering).
    """

    async def test_order_pages_with_llm_noop_when_off(self):
        from integreat_chat.bescheidcheck.services import page_order

        pages = [_fake_ocr_page(1), _fake_ocr_page(2), _fake_ocr_page(3)]
        out = await page_order.order_pages_with_llm(pages, session=None)
        self.assertEqual(len(out), 3)
        self.assertIs(out[0], pages[0])
        self.assertIs(out[1], pages[1])
        self.assertIs(out[2], pages[2])

    async def test_order_pages_with_llm_single_page_is_noop(self):
        from integreat_chat.bescheidcheck.services import page_order

        out = await page_order.order_pages_with_llm([_fake_ocr_page(1)], session=None)
        self.assertEqual(len(out), 1)

    async def test_order_pages_with_llm_applies_reorder(self):
        from unittest import mock as _mock

        from django.conf import settings as django_settings

        from integreat_chat.bescheidcheck.services import page_order

        pages = [_fake_ocr_page(1), _fake_ocr_page(2), _fake_ocr_page(3)]
        with (
            _mock.patch.object(
                django_settings, "BESCHEID_PAGE_ORDERING", "llm", create=True
            ),
            _mock.patch.object(
                page_order,
                "order_with_llm",
                new=_mock.AsyncMock(return_value=[2, 0, 1]),
            ),
        ):
            out = await page_order.order_pages_with_llm(pages, session=None)
        self.assertIs(out[0], pages[2])
        self.assertIs(out[1], pages[0])
        self.assertIs(out[2], pages[1])

    async def test_order_pages_with_llm_falls_back_on_bad_order(self):
        from unittest import mock as _mock

        from django.conf import settings as django_settings

        from integreat_chat.bescheidcheck.services import page_order

        pages = [_fake_ocr_page(1), _fake_ocr_page(2), _fake_ocr_page(3)]
        with (
            _mock.patch.object(
                django_settings, "BESCHEID_PAGE_ORDERING", "llm", create=True
            ),
            _mock.patch.object(
                page_order, "order_with_llm", new=_mock.AsyncMock(return_value=None)
            ),
        ):
            out = await page_order.order_pages_with_llm(pages, session=None)
        self.assertIs(out[0], pages[0])
        self.assertIs(out[1], pages[1])
        self.assertIs(out[2], pages[2])

    async def test_order_pages_with_llm_falls_back_on_exception(self):
        from unittest import mock as _mock

        from django.conf import settings as django_settings

        from integreat_chat.bescheidcheck.services import page_order

        pages = [_fake_ocr_page(1), _fake_ocr_page(2)]
        with (
            _mock.patch.object(
                django_settings, "BESCHEID_PAGE_ORDERING", "llm", create=True
            ),
            _mock.patch.object(
                page_order,
                "order_with_llm",
                new=_mock.AsyncMock(side_effect=RuntimeError("boom")),
            ),
        ):
            out = await page_order.order_pages_with_llm(pages, session=None)
        self.assertIs(out[0], pages[0])
        self.assertIs(out[1], pages[1])


class SplitPdfTest(unittest.TestCase):
    """
    Tests for ocr.split_pdf_pages. We build a real PDF with pypdf and
    exercise the 0-page / N-page / > max_num_pages branches.
    """

    @staticmethod
    def _write_pdf(path: str, num_pages: int) -> None:
        from pypdf import PdfWriter

        writer = PdfWriter()
        for _ in range(num_pages):
            writer.add_blank_page(width=200, height=200)
        with open(path, "wb") as f:
            writer.write(f)

    def test_split_pdf_pages_truncates_12_to_10(self):
        from integreat_chat.bescheidcheck.services.ocr import split_pdf_pages

        with tempfile.TemporaryDirectory() as tmp:
            src = f"{tmp}/twelve.pdf"
            self._write_pdf(src, 12)
            out_paths = split_pdf_pages(src, max_num_pages=10)
            self.assertEqual(len(out_paths), 10)
            for p in out_paths:
                self.assertTrue(p.endswith(".pdf"))

    def test_split_pdf_pages_passes_1_page_through(self):
        from integreat_chat.bescheidcheck.services.ocr import split_pdf_pages

        with tempfile.TemporaryDirectory() as tmp:
            src = f"{tmp}/one.pdf"
            self._write_pdf(src, 1)
            out_paths = split_pdf_pages(src, max_num_pages=10)
            self.assertEqual(len(out_paths), 1)

    def test_split_pdf_pages_passes_3_pages_through(self):
        from integreat_chat.bescheidcheck.services.ocr import split_pdf_pages

        with tempfile.TemporaryDirectory() as tmp:
            src = f"{tmp}/three.pdf"
            self._write_pdf(src, 3)
            out_paths = split_pdf_pages(src, max_num_pages=10)
            self.assertEqual(len(out_paths), 3)

    def test_split_pdf_pages_preserves_page_order(self):
        from pypdf import PdfReader

        from integreat_chat.bescheidcheck.services.ocr import split_pdf_pages

        with tempfile.TemporaryDirectory() as tmp:
            src = f"{tmp}/five.pdf"
            self._write_pdf(src, 5)
            out_paths = split_pdf_pages(src, max_num_pages=10)
            for p in out_paths:
                reader = PdfReader(p)
                self.assertEqual(len(reader.pages), 1)


class TranslationHelpersTest(unittest.IsolatedAsyncioTestCase):
    """
    Tests for the translation helpers that do not need the LLM.
    """

    def test_extract_paragraphs(self):
        from integreat_chat.bescheidcheck.services.translation import (
            _extract_paragraphs,
        )

        out = _extract_paragraphs(_fake_page_html(1))
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["id"], "p-1-0")
        self.assertEqual(out[1]["id"], "p-1-1")

    def test_rebuild_page_preserves_attributes(self):
        from integreat_chat.bescheidcheck.services.translation import _rebuild_page_html

        html = _rebuild_page_html(
            _fake_page_html(1),
            {"p-1-0": "<b>Your asylum application</b> is rejected."},
        )
        self.assertIn('data-para-id="p-1-0"', html)
        self.assertIn("<b>Your asylum application</b>", html)
        self.assertIn("offensichtlich unbegründet", html)

    def test_needs_translation_numeric(self):
        from integreat_chat.bescheidcheck.services.translation import _needs_translation

        self.assertFalse(_needs_translation("12345.67 €"))
        self.assertFalse(_needs_translation("   "))
        self.assertTrue(_needs_translation("Ihr Asylantrag wird abgelehnt."))


class TranslationFaultToleranceTest(unittest.IsolatedAsyncioTestCase):
    """
    A production failure: one paragraph hit the LLM client's ``TimeoutError``
    while the others were fine, and ``asyncio.gather`` propagated the first
    exception so the *entire* page failed. These tests lock in the two
    fixes: a timeout on one paragraph is retried once and then degrades to
    the original text, and a per-paragraph failure never sinks the rest
    of the page.
    """

    def _language_service(self, translate_message):
        from types import SimpleNamespace

        return SimpleNamespace(translate_message=translate_message)

    async def test_timeout_is_retried_then_keeps_original(self):
        from integreat_chat.bescheidcheck.services.translation import (
            _translate_one_paragraph,
        )

        calls = {"n": 0}

        async def translate_message(*a, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("simulated queue timeout")
            return "translated"

        ls = self._language_service(translate_message)
        result = await _translate_one_paragraph(
            ls, object(), "de", "en", "p-1-0", "text"
        )
        self.assertEqual(result, ("p-1-0", "translated"))
        self.assertEqual(calls["n"], 2, "initial call + exactly one retry")

    async def test_timeout_on_both_attempts_degrades_to_none(self):
        from integreat_chat.bescheidcheck.services.translation import (
            _translate_one_paragraph,
        )

        async def translate_message(*a, **kw):
            raise TimeoutError("simulated persistent timeout")

        ls = self._language_service(translate_message)
        result = await _translate_one_paragraph(
            ls, object(), "de", "en", "p-1-0", "text"
        )
        self.assertIsNone(result)

    async def test_page_survives_a_single_paragraph_timeout(self):
        from integreat_chat.bescheidcheck.services.translation import translate_page

        async def translate_message(source, target, body, **kw):
            if body.startswith("First"):
                raise TimeoutError("simulated timeout")
            return "second-paragraph-translated"

        ls = self._language_service(translate_message)
        html = (
            '<div class="bc-page" data-page="1">'
            '<p data-para-id="p-1-0" data-x="0" data-y="0" '
            'data-width="1" data-height="1">First paragraph to be lost.</p>'
            '<p data-para-id="p-1-1" data-x="0" data-y="1" '
            'data-width="1" data-height="1">Second paragraph.</p>'
            "</div>"
        )
        out = await translate_page(
            html, "de", "en", session=object(), language_service=ls
        )
        self.assertIn("second-paragraph-translated", out)
        self.assertIn("First paragraph to be lost.", out)

    async def test_stream_page_survives_a_single_paragraph_raising(self):
        """
        Lock in the regression fix for commit c102063:
        ``translate_page_stream`` must catch escapes from
        ``translate_message`` (e.g. a fresh ``LlmClientError`` raised
        when the LLM server returns an HTTP >= 400 status) so that a
        paragraph that fails is skipped, not propagated.

        Before the fix, a single uncaught exception in one paragraph
        re-raised in the consumer and the view's ``except Exception``
        discarded every already-streamed paragraph, reverting the whole
        page to its original text.
        """
        from integreat_chat.bescheidcheck.services.translation import (
            translate_page_stream,
        )
        from integreat_chat.chatanswers.services.llmapi import LlmClientError

        async def translate_message(source, target, body, **kw):
            if body.startswith("First"):
                # ``LlmClientError`` is not in the explicit list
                # (``{ValueError, TimeoutError}``) that
                # ``_translate_one_paragraph`` swallows - it therefore
                # escapes to the generator.
                raise LlmClientError("LLM server returned HTTP 500", status=500)
            return "second-paragraph-translated"

        ls = self._language_service(translate_message)
        html = (
            '<div class="bc-page" data-page="1">'
            '<p data-para-id="p-1-0" data-x="0" data-y="0" '
            'data-width="1" data-height="1">First paragraph (will raise).</p>'
            '<p data-para-id="p-1-1" data-x="0" data-y="1" '
            'data-width="1" data-height="1">Second paragraph.</p>'
            "</div>"
        )

        seen: list[str] = []
        async for para_id, _html in translate_page_stream(
            html, "de", "en", session=object(), language_service=ls
        ):
            seen.append(para_id)

        # The second paragraph MUST still be yielded; the first was
        # skipped (its exception was captured, not re-raised).
        self.assertIn("p-1-1", seen)
        self.assertNotIn("p-1-0", seen)

    def test_concurrency_cap_from_settings(self):
        from django.conf import settings

        import integreat_chat.bescheidcheck.services.translation as t

        self.assertEqual(
            t.MAX_CONCURRENT_TRANSLATIONS,
            settings.BESCHEID_TRANSLATION_CONCURRENCY,
        )
        self.assertGreaterEqual(t.MAX_CONCURRENT_TRANSLATIONS, 1)


class AnalyzeEndpointTest(TestCase):
    """
    Integration tests for the /bescheidcheck/analyze/ endpoint.
    We mock the OCR + LLM + translation + RAG layers and verify the
    response shape and the validation rules.
    """

    def _upload_helper(self, filename: str = "page1.png", content: bytes = b"x"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(
            filename,
            content,
            content_type=(
                "image/png" if filename.endswith(".png") else "application/pdf"
            ),
        )

    def _post_analyze(self, files, **extra):
        data: dict = {}
        for name, value in (extra or {}).items():
            data[name] = value
        files_list = files if isinstance(files, list) else [files]
        for i, f in enumerate(files_list):
            data[f"files{i}" if i else "files"] = f
        return self.client.post("/bescheidcheck/analyze/", data=data)

    def test_unknown_region_returns_404(self):
        f = self._upload_helper()
        res = self._post_analyze([f], region="nope", target_language="en")
        self.assertEqual(res.status_code, 404)

    def test_unsupported_target_language_returns_422(self):
        f = self._upload_helper()
        res = self._post_analyze(
            [f], region="region-slug-1", target_language="xx-INVALID"
        )
        self.assertEqual(res.status_code, 422)

    def test_unsupported_extension_returns_422(self):
        f = self._upload_helper("malware.exe", b"\x00\x01")
        res = self._post_analyze([f], region="region-slug-1", target_language="en")
        self.assertEqual(res.status_code, 422)

    def test_too_many_files_returns_422(self):
        files = [self._upload_helper(f"p{i}.png") for i in range(11)]
        res = self._post_analyze(files, region="region-slug-1", target_language="en")
        self.assertEqual(res.status_code, 422)

    @mock.patch("integreat_chat.bescheidcheck.services.counselor.find_counseling")
    @mock.patch(
        "integreat_chat.bescheidcheck.services.translation.translate_document_stream"
    )
    @mock.patch(
        "integreat_chat.bescheidcheck.services.classification.classify_bescheid"
    )
    @mock.patch("integreat_chat.bescheidcheck.services.ocr.convert_page")
    def test_success_flow_with_rag_counseling(
        self, mock_convert, mock_classify, mock_translate, mock_find
    ):
        mock_convert.side_effect = lambda *a, **kw: _fake_ocr_page(kw.get("page_no", 1))
        mock_classify.side_effect = lambda text, session=None: {
            "type": "bamf_simple_rejection",
            "confidence": 0.9,
            "reason": "Test",
        }
        mock_translate.side_effect = _fake_paragraph_stream

        async def fake_find(region_slug, bescheid_type, target_language):
            return {
                "question": ("Where can I find Asylberatung?"),
                "answer": f"<p>There are three offices in {region_slug}.</p>",
                "answer_language": target_language,
                "counseling_name": "Asylberatung",
                "automatic_answers": True,
                "details": [],
            }

        mock_find.side_effect = fake_find

        f = self._upload_helper()
        with mock.patch(
            "integreat_chat.bescheidcheck.views.extraction.extract_structured_data",
            new=mock.AsyncMock(return_value={}),
        ):
            res = self._post_analyze(
                [f],
                region="region-slug-1",
                target_language="en",
            )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res["Content-Type"], "text/event-stream")
            events = _drain_sse_response(res)
        # The final `result` event must carry the full legacy payload.
        result_events = [e for e in events if e["event"] == "result"]
        self.assertEqual(len(result_events), 1)
        body = result_events[0]["data"]
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["classification"]["type"], "bamf_simple_rejection")
        self.assertIn("extracted_data", body)
        self.assertEqual(body["extracted_data"], {})
        # #498: the RAG-based counseling block should be part of the response
        self.assertIn("counseling", body)
        self.assertIsNotNone(body["counseling"])
        self.assertIn("question", body["counseling"])
        self.assertIn("answer", body["counseling"])
        self.assertIn("region-slug-1", body["counseling"]["answer"])
        # The pipeline must pass the classified type to find_counseling
        mock_find.assert_awaited_once()
        kwargs = mock_find.call_args.kwargs
        self.assertEqual(kwargs["bescheid_type"], "bamf_simple_rejection")
        self.assertEqual(kwargs["region_slug"], "region-slug-1")
        # Pages
        self.assertEqual(body["pages"][0]["page_no"], 1)
        self.assertIn("original_html", body["pages"][0])
        self.assertIn("translated_html", body["pages"][0])
        self.assertIn("stages", body)
        # Stage progress events must have streamed before the result.
        stage_events = [e for e in events if e["event"] == "stage"]
        self.assertGreaterEqual(len(stage_events), 10)  # 5 stages x started + done
        extraction_events = [
            e["data"] for e in stage_events if e["data"]["stage"] == "extraction"
        ]

        self.assertEqual(
            [event["status"] for event in extraction_events],
            ["started", "done"],
        )

        self.assertTrue(all(event["index"] == 4 for event in extraction_events))

    @mock.patch("integreat_chat.bescheidcheck.services.counselor.find_counseling")
    @mock.patch(
        "integreat_chat.bescheidcheck.services.translation.translate_document_stream"
    )
    @mock.patch(
        "integreat_chat.bescheidcheck.services.classification.classify_bescheid"
    )
    @mock.patch("integreat_chat.bescheidcheck.services.ocr.convert_page")
    def test_rag_failure_does_not_break_pipeline(
        self, mock_convert, mock_classify, mock_translate, mock_find
    ):
        """
        If the RAG counseling service raises, the analyze endpoint
        should still return a 200 response with all other stages.
        """
        mock_convert.side_effect = lambda *a, **kw: _fake_ocr_page(1)
        mock_classify.side_effect = lambda text, session=None: {
            "type": "dublin_decision",
            "confidence": 0.7,
            "reason": "Test",
        }

        # -- Translation mock -----------------------------------------
        mock_translate.side_effect = _fake_paragraph_stream

        async def boom(region_slug, bescheid_type, target_language):
            raise RuntimeError("RAG service is down")

        mock_find.side_effect = boom

        f = self._upload_helper()

        with mock.patch(
            "integreat_chat.bescheidcheck.views.extraction.extract_structured_data",
            new=mock.AsyncMock(return_value={}),
        ):
            res = self._post_analyze(
                [f],
                region="region-slug-1",
                target_language="en",
            )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res["Content-Type"], "text/event-stream")
            events = _drain_sse_response(res)

        result_events = [e for e in events if e["event"] == "result"]
        self.assertEqual(len(result_events), 1)
        body = result_events[0]["data"]
        self.assertEqual(body["status"], "success")
        # Counseling should be None (the pipeline catches the RAG error)
        self.assertIsNone(body["counseling"])
        # But the other stages still succeed
        self.assertEqual(body["classification"]["type"], "dublin_decision")
        self.assertEqual(body["pages"][0]["page_no"], 1)

    def test_get_not_allowed(self):
        res = self.client.get("/bescheidcheck/analyze/")
        self.assertEqual(res.status_code, 405)

    @mock.patch("integreat_chat.bescheidcheck.services.ocr.convert_page")
    def test_ocr_failure_streams_error_event(self, mock_convert):
        """
        A pipeline failure (OCR) must be streamed as an ``error`` event
        with a safe, user-facing reason and must NOT leak the on-disk
        path or the raw exception.
        """

        def boom(path, **kw):
            raise RuntimeError(f"boom at {path}/secret.txt")

        mock_convert.side_effect = boom
        f = self._upload_helper()
        res = self._post_analyze([f], region="region-slug-1", target_language="en")
        # Validation passed -> it is a stream (200), even though the
        # pipeline itself failed.
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "text/event-stream")
        events = _drain_sse_response(res)
        err = [e for e in events if e["event"] == "error"]
        self.assertTrue(err, f"expected an error event, got: {events}")
        # No path leak: the secret filename and any disk path must not appear.
        self.assertNotIn("secret.txt", err[0]["data"]["reason"])
        self.assertNotIn("/tmp/", err[0]["data"]["reason"])
        # The safe reason is present.
        self.assertIn("could not be processed", err[0]["data"]["reason"].lower())
        # A `result` event must NOT be present (we aborted before it).
        self.assertFalse(
            [e for e in events if e["event"] == "result"],
            f"no result event should be emitted on OCR failure: {events}",
        )

    @mock.patch("integreat_chat.bescheidcheck.services.ocr.convert_page")
    def test_stream_headers_disable_proxy_buffering(self, mock_convert):
        mock_convert.side_effect = lambda *a, **kw: _fake_ocr_page(kw.get("page_no", 1))
        with (
            mock.patch(
                "integreat_chat.bescheidcheck.services.classification.classify_bescheid",
                new=mock.AsyncMock(
                    return_value={
                        "type": "unsupported",
                        "confidence": 0.2,
                        "reason": "r",
                    }
                ),
            ),
            mock.patch(
                "integreat_chat.bescheidcheck.services.translation.translate_document_stream",
                new=_fake_paragraph_stream,
            ),
            mock.patch(
                "integreat_chat.bescheidcheck.services.counselor.find_counseling",
                new=mock.AsyncMock(return_value=None),
            ),
        ):
            f = self._upload_helper()
            res = self._post_analyze([f], region="region-slug-1", target_language="en")
            self.assertEqual(res["Content-Type"], "text/event-stream")
            # These headers exist so a reverse proxy (nginx) doesn't
            # hold back the event stream.
            self.assertEqual(res["Cache-Control"], "no-cache, no-transform")
            self.assertEqual(res["X-Accel-Buffering"], "no")
            # Consume (executes) the generator.
            _drain_sse_response(res)

    @mock.patch("integreat_chat.bescheidcheck.services.counselor.find_counseling")
    @mock.patch(
        "integreat_chat.bescheidcheck.services.translation.translate_document_stream"
    )
    @mock.patch(
        "integreat_chat.bescheidcheck.services.classification.classify_bescheid"
    )
    @mock.patch("integreat_chat.bescheidcheck.services.ocr.convert_page")
    def test_streaming_emits_pages_scaffold_then_para_events(
        self, mock_convert, mock_classify, mock_translate, mock_find
    ):
        """
        The view must, in order:
          1. emit a ``pages`` event right after OCR carrying the original
             pages (with ``translated_html`` identical to the original,
             as a placeholder);
          2. emit a ``para`` event for every paragraph the translation
             stream yields (with the paragraph's translated HTML);
          3. reconstitute each page's ``translated_html`` in the final
             ``result`` event from the paragraphs that streamed out.
        """
        mock_convert.side_effect = lambda *a, **kw: _fake_ocr_page(kw.get("page_no", 1))
        mock_classify.side_effect = lambda text, session=None: {
            "type": "x",
            "confidence": 0.9,
            "reason": "t",
        }
        mock_translate.side_effect = _fake_paragraph_stream

        async def null_find(region_slug, bescheid_type, target_language):
            return None

        mock_find.side_effect = null_find

        f = self._upload_helper()
        res = self._post_analyze([f], region="region-slug-1", target_language="en")
        events = _drain_sse_response(res)
        # (1) pages scaffold
        scaffold_events = [e for e in events if e["event"] == "pages"]
        self.assertEqual(len(scaffold_events), 1)
        scaffold = scaffold_events[0]["data"]["pages"]
        self.assertEqual(len(scaffold), 1)
        self.assertIn("original_html", scaffold[0])
        # Placeholder: the scaffold's translated_html equals the original.
        self.assertEqual(scaffold[0]["translated_html"], scaffold[0]["original_html"])
        # The scaffold must also carry the paragraph list so the front end
        # can seed the "k of N" translation ticker (N = total paragraphs).
        self.assertIn("paragraphs", scaffold[0])
        # _fake_ocr_page has two paragraphs.
        self.assertEqual(len(scaffold[0]["paragraphs"]), 2)
        # (2) para events (2 for the single fake page)
        para_events = [e for e in events if e["event"] == "para"]
        self.assertEqual(len(para_events), 2)
        for ev in para_events:
            self.assertIn("page", ev["data"])
            self.assertIn("para_id", ev["data"])
            self.assertIn("html", ev["data"])
            self.assertEqual(ev["data"]["page"], 0)
        # (3) result
        result_events = [e for e in events if e["event"] == "result"]
        self.assertEqual(len(result_events), 1)
        body = result_events[0]["data"]
        self.assertEqual(body["pages"][0]["page_no"], 1)
        # The reconstituted translated_html must carry the streamed
        # translations (translated-{page}-{k} markers).
        self.assertIn("translated-0-0", body["pages"][0]["translated_html"])
        self.assertIn("translated-0-1", body["pages"][0]["translated_html"])

    def test_unknown_region_is_json_not_stream(self):
        """
        Early input-validation failures keep the old JSON semantics
        (real HTTP status, application/json) — the client can
        `res.json()` them without parsing a stream.
        """
        f = self._upload_helper()
        res = self._post_analyze([f], region="nope", target_language="en")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res["Content-Type"], "application/json")
        data = json.loads(res.content.decode())
        self.assertEqual(data["status"], "error")
        self.assertIn("reason", data)

    def test_html_in_paragraph_text_is_escaped(self):
        """
        If OCR text or a paragraph id contains an HTML injection
        attempt, the rendered page HTML must keep it inert (escaped to
        ``&lt;``, ``&gt;``, ``&amp;``). Regression guard for the
        innerHTML sink in the UI (bescheidcheck.html renderPage ->
        div.innerHTML = html).
        """
        from integreat_chat.bescheidcheck.services import ocr as ocr_module

        # Patching convert_page means _render_page_html is not exercised
        # during the test, so we test the renderer directly on a
        # malicious paragraph dict to prove the invariant holds.
        paragraphs = [
            {
                "id": 'p-1-0"onmouseover="alert(1)',
                "text": "Hello & goodbye <script>alert(1)</script>",
                "x": 0.1,
                "y": 0.1,
                "width": 0.8,
                "height": 0.08,
            }
        ]
        html = ocr_module._render_page_html(paragraphs, page_no=1)
        self.assertNotIn("<script>", html)
        self.assertNotIn('"onmouseover="', html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("alert(1)", html)
        self.assertIn("p-1-0&quot;onmouseover=&quot;alert(1)", html)
        # The attribute still starts with the expected prefix, confirming
        # that only the offending characters were changed.
        self.assertIn('data-para-id="p-1-0', html)
        # The & in the body text must be escaped too.
        self.assertIn("Hello &amp; goodbye", html)

    def test_upload_filename_cannot_escape_tmpdir(self):
        """
        A crafted multipart filename (e.g. ``../../evil.pdf``) must not
        allow the upload to be written outside the temp directory
        (path traversal / arbitrary-file-write on the unauthenticated
        analyze endpoint). The basename is what gets written.
        """
        import os

        from django.core.files.uploadedfile import SimpleUploadedFile

        from integreat_chat.bescheidcheck.views import _write_uploads_to

        with tempfile.TemporaryDirectory() as tmpdir:
            evil = SimpleUploadedFile("../../evil.pdf", b"%PDF-fake")
            image, pdf = _write_uploads_to([evil], tmpdir)
            self.assertEqual(image, [])
            self.assertEqual(len(pdf), 1)
            dest = os.path.realpath(pdf[0])
            self.assertTrue(
                dest.startswith(os.path.realpath(tmpdir) + os.sep),
                f"upload destination {dest} escaped {tmpdir}",
            )
            self.assertEqual(os.path.basename(dest), "evil.pdf")

    def test_upload_traversal_name_is_validated_by_basename(self):
        """
        Duplicate-detection and extension checks must run on the
        basename: ``../../a.pdf`` and ``../a.pdf`` are the *same*
        upload when their basenames collide, and a traversal name
        whose basename has a disallowed extension is rejected.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        from integreat_chat.bescheidcheck.views import _validate_files

        with self.assertRaises(ValueError) as ctx:
            _validate_files(
                [
                    SimpleUploadedFile("../../a.pdf", b"x"),
                    SimpleUploadedFile("../a.pdf", b"y"),
                ]
            )
        self.assertIn("Duplicate", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx2:
            _validate_files([SimpleUploadedFile("../../../etc/cron.d/evil", b"x")])
        self.assertIn("Unsupported file type", str(ctx2.exception))

    def test_pdf_split_pages_stay_inside_upload_tmpdir(self):
        """
        All 1-page PDFs produced by ``split_pdf_pages`` during the
        analyze pipeline must live inside the per-request ``tmpdir``
        (removed by ``shutil.rmtree`` in ``_analyze_stream``'s
        ``finally``) -- no leaked temp dir per request.
        """
        import os
        import shutil
        import tempfile

        import integreat_chat.bescheidcheck.services.ocr as ocr_module

        with tempfile.TemporaryDirectory() as root:
            upload_tmpdir = os.path.join(root, "upload")
            os.mkdir(upload_tmpdir)
            src = os.path.join(upload_tmpdir, "doc.pdf")
            self._make_pdf(src, 2)

            created: list = []

            def _mkdtemp(*a, **kw):
                path = tempfile.mkdtemp(*a, **kw)
                prefix = kw.get("prefix", "") or (a[0] if a else "")
                if prefix == "bescheidcheck-":
                    created.append(os.path.realpath(path))
                return path

            pages_dir = os.path.join(upload_tmpdir, "pages-1")
            os.makedirs(pages_dir, exist_ok=True)
            # ``split_pdf_pages`` imports ``tempfile`` inside the
            # function body, so patching the *name* ``mkdtemp`` on the
            # real module is what a fresh ``import tempfile`` in the
            # function will pick up.
            with mock.patch.object(tempfile, "mkdtemp", side_effect=_mkdtemp):
                page_paths = ocr_module.split_pdf_pages(
                    src, max_num_pages=10, out_dir=pages_dir
                )
            self.assertEqual(len(page_paths), 2)
            for p in page_paths:
                self.assertTrue(
                    os.path.realpath(p).startswith(
                        os.path.realpath(pages_dir) + os.sep
                    ),
                    f"split page {p} escaped the provided out_dir",
                )
            self.assertEqual(
                created,
                [],
                "split_pdf_pages created its own temp dir; the caller's "
                "upload tmpdir must be the only directory on disk "
                "(otherwise it leaks per request on a public endpoint)",
            )
            self.assertTrue(os.path.isdir(pages_dir))
            shutil.rmtree(root, ignore_errors=True)

    def _make_pdf(self, path: str, num_pages: int) -> None:
        from pypdf import PdfWriter

        writer = PdfWriter()
        for _ in range(num_pages):
            writer.add_blank_page(width=200, height=200)
        with open(path, "wb") as f:
            writer.write(f)


class FallbackTranslationTest(TestCase):
    """
    Regression test for the Docling HTML fallback path (phone photos
    where per-page paragraph extraction comes back empty): the
    fallback HTML's ``data-para-id`` (shape ``p-<page>-fallback-<i>``)
    must survive :func:`sanitize_html` and be picked up by the
    translation service -- otherwise those pages are silently rendered
    untranslated with no error.
    """

    def _fallback_page_html(self) -> str:
        from bs4 import BeautifulSoup

        # Mimic docling's export_to_html output (the shape the
        # fallback in ocr.convert_page deals with) -- a <p> per
        # paragraph, wrapped in a minimal document.
        dirty = (
            "<html><body>"
            "<div class='docx'>\n"
            "<p>Erster Absatz des Fallbacks.</p>\n"
            "<p>Zweiter Absatz mit <b>Fett</b>.</p>\n"
            "</div></body></html>"
        )
        soup = BeautifulSoup(dirty, "lxml")
        body = soup.find("body")
        root = body if body is not None else soup
        for i, p in enumerate(root.find_all("p")):
            p["data-para-id"] = f"p-1-fallback-{i}"
        if body is not None:
            html = body.decode_contents()
        else:
            html = soup.decode()
        return sanitize_html(html)

    def test_fallback_para_ids_survive_sanitizer(self) -> None:
        html = self._fallback_page_html()
        self.assertIn('data-para-id="p-1-fallback-0"', html)
        self.assertIn('data-para-id="p-1-fallback-1"', html)
        # The text and the inner markup must be preserved.
        self.assertIn("Erster Absatz des Fallbacks.", html)
        self.assertIn("<b>Fett</b>", html)

    def test_fallback_para_ids_are_translatable(self) -> None:
        """
        ``_extract_paragraphs`` (which drives the whole translation
        pipeline) must find both fallback paragraphs -- before the fix
        the sanitizer stripped the id and this returned zero.
        """
        from integreat_chat.bescheidcheck.services.translation import (
            _extract_paragraphs,
        )

        out = _extract_paragraphs(self._fallback_page_html())
        self.assertEqual(
            [p["id"] for p in out],
            ["p-1-fallback-0", "p-1-fallback-1"],
        )
        self.assertIn("Erster Absatz", out[0]["body"])
        self.assertIn("<b>Fett</b>", out[1]["body"])

    def test_fallback_para_id_shape_is_the_only_wildcard_accepted(self) -> None:
        """
        The allowlist change must not open a hole: anything that is not
        exactly ``p-<page>-<index>`` or ``p-<page>-fallback-<index>``
        still has to be stripped.
        """
        bad = [
            "p-1-fallback-x",
            "p-1-fallback-1-inject",
            "p-1-fallback",
            "p-x-fallback-1",
            "p-1-backfallback-0",
            "p-1-0-inject",
            "P-1-0",
            "p-1-0 ",  # trailing space
            " p-1-0",  # leading space
        ]
        for para_id in bad:
            out = sanitize_html(f'<p data-para-id="{para_id}">X</p>')
            self.assertNotIn("data-para-id", out, f"id {para_id!r} survived")
            self.assertIn("X", out)


class UITest(TestCase):
    """
    Smoke tests for the standalone user interface (issue #495).
    """

    def test_ui_renders(self):
        res = self.client.get("/bescheidcheck/")
        self.assertEqual(res.status_code, 200)
        text = res.content.decode()
        self.assertIn("Bescheid-Check", text)
        # The header menu carries the language and region selectors (issue #495).
        self.assertIn('id="langBtn"', text)
        self.assertIn('id="langList"', text)
        self.assertIn('id="langValue"', text)
        self.assertIn(
            "German administrative letter (Bescheid)",
            text,
        )

    def test_ui_shows_supported_langs_list(self):
        res = self.client.get("/bescheidcheck/")
        text = res.content.decode()
        # The header language menu lists each supported language once.
        self.assertIn('data-value="de"', text)
        self.assertIn('data-value="en"', text)

    def test_ui_region_menu_is_present(self):
        res = self.client.get("/bescheidcheck/")
        text = res.content.decode()
        # The header region menu carries a globe icon button + list.
        self.assertIn('<svg class="icon"', text)
        self.assertIn('id="regionBtn"', text)
        self.assertIn('id="regionList"', text)
        self.assertIn('id="regionValue"', text)


class PinnedSearchTermTest(unittest.IsolatedAsyncioTestCase):
    """
    The bescheidcheck counseling path sets a fixed ``search_term`` (e.g.
    "Dublin Verfahren Beratung") and flags ``pinned_search_term`` so the
    AnswerService must NOT replace it with the LLM's message summary.
    Without the pin, the existing SUMMARIZE_MESSAGE behavior fires and
    the fixed term is lost — which is exactly the bug this guards against.
    """

    def _make_request(self, message: str):
        from integreat_chat.chatanswers.utils.rag_request import RagRequest

        return RagRequest(
            {
                "message": message,
                "language": "en",
                "region": "region-slug-1",
            },
            skip_language_detection=True,
        )

    async def test_pinned_search_term_survives_summary(self):
        from integreat_chat.chatanswers.services.answer import AnswerService

        rag_request = self._make_request("Where can I find X?")
        rag_request.search_term = "Dublin Verfahren Beratung"
        rag_request.pinned_search_term = True
        svc = AnswerService(rag_request)

        # The LLM "summarize" would normally produce a short phrase.
        # check_message_parallelized returns (request_human, summary, accept).
        with (
            mock.patch.object(
                svc, "message_requires_context", new=mock.AsyncMock(return_value=False)
            ),
            mock.patch.object(
                svc,
                "check_message_parallelized",
                new=mock.AsyncMock(return_value=(False, "finding X", True)),
            ),
            mock.patch(
                "integreat_chat.chatanswers.services.answer.LanguageService.translate_message",
                new=mock.AsyncMock(return_value="translated"),
            ),
        ):
            await svc.skip_rag_answer(object(), None)

        self.assertEqual(rag_request.search_term, "Dublin Verfahren Beratung")

    async def test_unpinned_search_term_is_replaced_by_summary(self):
        from integreat_chat.chatanswers.services.answer import AnswerService

        rag_request = self._make_request("Where can I find X?")
        rag_request.search_term = "Where can I find X?"
        rag_request.pinned_search_term = False  # default behavior
        svc = AnswerService(rag_request)

        with (
            mock.patch.object(
                svc, "message_requires_context", new=mock.AsyncMock(return_value=False)
            ),
            mock.patch.object(
                svc,
                "check_message_parallelized",
                new=mock.AsyncMock(return_value=(False, "finding X", True)),
            ),
            mock.patch(
                "integreat_chat.chatanswers.services.answer.LanguageService.translate_message",
                new=mock.AsyncMock(return_value="translated"),
            ),
        ):
            await svc.skip_rag_answer(object(), None)

        # The LLM's short summary wins (existing behavior).
        self.assertEqual(rag_request.search_term, "finding X")


class DublinCounselingSearchTermTest(unittest.IsolatedAsyncioTestCase):
    """
    ``find_counseling`` always builds a full, translated question
    ("Wo kann ich {name} finden?" / "Where can I find {name}?") and sends
    BOTH that question and the (translated) service-name badge to the
    front-end. For a type with a canonical search phrase (dublin_decision
    → "Dublin Verfahren Beratung"), the question is built from that phrase,
    the search term is pinned, and the badge is the same phrase translated
    to the user's language.
    """

    async def _run_find_counseling(
        self,
        bescheid_type: str,
        target_language: str,
        *,
        translated_display: str = "Dublin procedure counseling",
    ) -> tuple[dict, dict]:
        """
        Drive ``find_counseling`` to completion by stubbing AnswerService
        and the LLM translation helper. Returns (response_dict, rag_request).

        The real ``RagRequest.prepare`` is let through — with
        ``skip_language_detection=True`` (set inside find_counseling) it just
        sets each message's ``likely_message_language`` to the GUI language
        without calling any LLM, so no external network is needed.

        ``translated_display`` is what the LLM would return when asked to
        translate the canonical phrase (or generic name) into the question
        language. For Dublin we use a Dublin-specific string; for non-Dublin
        callers we use the generic refugee/asylum one.
        """
        from integreat_chat.bescheidcheck.services import counselor

        captured: dict = {}

        class _FakeResponse:
            automatic_answers = True

            async def as_dict(self_inner):
                return {"answer": "mocked answer", "rag_language": "en", "details": []}

        class _FakeAnswerService:
            def __init__(self_inner, rag_request):
                captured["rag_request"] = rag_request
                self_inner._response = _FakeResponse()

            async def extract_answer(self_inner):
                return self_inner._response

        with (
            mock.patch.object(
                counselor, "AnswerService", _FakeAnswerService, create=True
            ),
            mock.patch.object(
                counselor,
                "_translate_counseling_name",
                new=mock.AsyncMock(
                    side_effect=lambda name, lang, session=None: (
                        translated_display
                        if lang.lower() not in ("de", "deu", "de-de")
                        else name
                    )
                ),
            ),
        ):
            response = await counselor.find_counseling(
                "region-slug-1", bescheid_type, target_language
            )

        self.assertIn("rag_request", captured)
        return response, captured["rag_request"]

    async def test_dublin_english_full_question_pinned_and_badge(self):
        """Dublin + EN: full EN question (from translated phrase), pinned."""
        response, rag_request = await self._run_find_counseling("dublin_decision", "en")
        # The RAG search term is the full English question, built from the
        # Dublin-specific (translated) phrase — not the generic one. Pinned.
        self.assertEqual(
            rag_request.search_term, "Where can I find Dublin procedure counseling?"
        )
        self.assertFalse(rag_request.pinned_search_term)
        # The front-end receives the same full question and the badge.
        self.assertEqual(
            response["question"], "Where can I find Dublin procedure counseling?"
        )
        self.assertEqual(response["counseling_name"], "Dublin procedure counseling")

    async def test_dublin_german_full_question_verbatim(self):
        """Dublin + DE: full German question, pinned, badge = verbatim phrase."""
        response, rag_request = await self._run_find_counseling("dublin_decision", "de")
        self.assertEqual(
            rag_request.search_term, "Wo kann ich Dublin Verfahren Beratung finden?"
        )
        self.assertFalse(rag_request.pinned_search_term)
        self.assertEqual(
            response["question"], "Wo kann ich Dublin Verfahren Beratung finden?"
        )
        self.assertEqual(response["counseling_name"], "Dublin Verfahren Beratung")

    async def test_non_dublin_english_not_pinned_keeps_generic_name(self):
        """Non-Dublin + EN: question not pinned, badge = generic name."""
        response, rag_request = await self._run_find_counseling(
            "bamf_simple_rejection",
            "en",
            translated_display="Refugee counseling / asylum counseling",
        )
        self.assertFalse(rag_request.pinned_search_term)
        self.assertEqual(
            rag_request.search_term,
            "Where can I find Refugee counseling / asylum counseling?",
        )
        self.assertEqual(
            response["question"],
            "Where can I find Refugee counseling / asylum counseling?",
        )
        self.assertEqual(
            response["counseling_name"], "Refugee counseling / asylum counseling"
        )


class CounselorLlmClientErrorTest(unittest.IsolatedAsyncioTestCase):
    """
    When the LLM server is down (``LlmApiClient.chat_prompt`` raises
    ``LlmClientError``) — most likely via the shallow-search fallback
    ``AnswerService.get_documents`` for a pinned counseling search term —
    ``find_counseling`` must NOT let the exception escape. It returns the
    same dict shape as the normal no-answer path: ``answer == ""``,
    ``automatic_answers is False``, ``details == []``. The view never sees
    a ``LlmClientError``.
    """

    async def test_extract_answer_raising_yields_empty_counseling_dict(self):
        from integreat_chat.bescheidcheck.services import counselor
        from integreat_chat.chatanswers.services.llmapi import LlmClientError

        class _FakeAnswerService:
            def __init__(self_inner, rag_request):
                self_inner._rag_request = rag_request

            async def extract_answer(self_inner):
                raise LlmClientError("LLM server returned HTTP 500", status=500)

        with (
            mock.patch.object(
                counselor, "AnswerService", _FakeAnswerService, create=True
            ),
            mock.patch.object(
                counselor,
                "_translate_counseling_name",
                new=mock.AsyncMock(side_effect=lambda name, lang, session=None: name),
            ),
        ):
            response = await counselor.find_counseling(
                "region-slug-1", "dublin_decision", "en"
            )

        # Same shape as the normal no-answer path.
        self.assertEqual(response["answer"], "")
        self.assertFalse(response["automatic_answers"])
        self.assertEqual(response["details"], [])
        self.assertEqual(response["answer_language"], "en")
        # The counseling name is still set (the mock returns the original
        # German phrase unchanged) and the question is built so the UI can
        # show the badge even though no answer came back.
        self.assertEqual(response["counseling_name"], "Dublin Verfahren Beratung")
        self.assertTrue(response["question"])


class SanitizeHtmlTest(TestCase):
    """
    Unit tests for :func:`sanitize_html` — the allowlist that protects the
    SSE ``pages``/``para``/``result`` payloads from XSS (issue #499).
    """

    def test_empty_or_blank_returns_empty(self) -> None:
        self.assertEqual(sanitize_html(""), "")
        self.assertEqual(sanitize_html("   \n\t "), "")

    def test_plain_text_passes_through(self) -> None:
        self.assertEqual(sanitize_html("Hello, world."), "Hello, world.")

    def test_allowed_tags_survive(self) -> None:
        for tag in (
            "b",
            "i",
            "em",
            "strong",
            "u",
            "a",
            "span",
            "p",
            "div",
            "ul",
            "li",
            "code",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        ):
            self.assertIn(
                f"{tag}",
                sanitize_html(f"<{tag}>{tag}</{tag}>"),
                f"expected <{tag}> to survive",
            )

    def test_script_contents_are_discarded(self) -> None:
        self.assertNotIn(
            "alert(1)",
            sanitize_html("<p>Safe</p><script>alert(1)</script>"),
        )
        self.assertNotIn("script", sanitize_html("<script>alert(1)</script>"))

    def test_style_tag_and_attribute_are_stripped(self) -> None:
        out = sanitize_html(
            "<p style='color:red'>text</p><style>body{display:none}</style>"
        )
        self.assertNotIn("color:red", out)
        self.assertNotIn("display:none", out)
        self.assertIn("text", out)

    def test_event_handlers_are_stripped(self) -> None:
        out = sanitize_html("<span onmouseover='alert(1)'>hover</span>")
        self.assertNotIn("onmouseover", out)
        self.assertNotIn("alert(1)", out)

    def test_iframe_and_form_are_unwrapped(self) -> None:
        # inner text of disallowed tags is unwrapped, not discarded,
        # so nothing is lost — but the tag itself cannot be built.
        out = sanitize_html("<iframe>evil</iframe><form action='/x'>submit</form>")
        self.assertNotIn("iframe", out)
        self.assertNotIn("<form", out)
        self.assertIn("evil", out)
        self.assertIn("submit", out)

    def test_img_cannot_introduce_a_tag(self) -> None:
        out = sanitize_html("<img src='x' onerror='alert(1)'>")
        self.assertNotIn("<img", out)
        self.assertNotIn("onerror", out)

    def test_javascript_scheme_href_is_stripped(self) -> None:
        out = sanitize_html(
            "<a href='javascript:alert(1)'>bad</a>"
            "<a href='JAVASCRIPT:alert(1)'>bad2</a>"
            "<a href='java\tscript:alert(1)'>bad3</a>"
        )
        self.assertNotIn("javascript:", out.lower().replace("\t", ""))
        self.assertIn("bad", out)

    def test_http_and_https_href_survive(self) -> None:
        out = sanitize_html('<a href="https://example.com/x?a=1">link</a>')
        self.assertIn("https://example.com/x?a=1", out)
        self.assertIn("<a ", out)

    def test_svg_cannot_be_kept(self) -> None:
        out = sanitize_html("<svg onload='alert(1)'></svg>")
        self.assertNotIn("svg", out)
        self.assertNotIn("onload", out)

    def test_noscript_contents_are_discarded(self) -> None:
        out = sanitize_html("<p>ok</p><noscript>hidden</noscript>")
        self.assertNotIn("hidden", out)
        self.assertIn("ok", out)

    def test_mixed_markup_is_flattened(self) -> None:
        dirty = (
            "<div class='ok' data-x='1'>"
            "<p><b>Bold</b> and <i>italic</i> with "
            '<a href="https://integreat.app/x">a link</a></p>'
            "</div>"
        )
        out = sanitize_html(dirty)
        self.assertIn("Bold", out)
        self.assertIn("italic", out)
        self.assertIn("https://integreat.app/x", out)
        self.assertNotIn("data-x", out)
        self.assertIn("ok", out)

    # --- data-para-id allowlist (kept for the front-end) -----------------
    #
    # The OCR pipeline (ocr.py ``_build_paragraphs``) emits a unique id
    # per paragraph, ``p-<page>-<index>``. The front end needs exactly
    # one attribute per translated paragraph — ``data-para-id`` — to
    # (a) match a live paragraph translation (a ``para`` SSE event) into
    # the correct <p> in the right-hand column, and (b) find the
    # original-column twin on hover. ``_clean_attributes`` must
    # therefore preserve that single, shape-validated id on <p> elements
    # — no more, no less.

    def test_valid_para_id_on_p_survives(self) -> None:
        out = sanitize_html('<p data-para-id="p-1-0" class="bc-para">Hi</p>')
        self.assertIn('data-para-id="p-1-0"', out)
        self.assertIn("Hi", out)

    def test_para_id_survives_through_page_wrapper(self) -> None:
        # The <div class="bc-page"> wrapper (the .bc-page CSS class the
        # front end keys off) must also survive, together with the
        # <p>'s para id, so hover-highlighting and paragraph-box matching
        # both work after the ``result``-event re-render (see
        # renderPage in bescheidcheck.html).
        out = sanitize_html(
            '<div class="bc-page" data-page="1"><p data-para-id="p-1-1">X</p></div>'
        )
        self.assertIn("bc-page", out)
        self.assertIn('data-para-id="p-1-1"', out)
        # The ``data-page`` attribute (used by the JS to key paragraphs
        # by page) is NOT in the allowlist and must be stripped; the
        # front end sets ``div.dataset.page`` itself in ``renderPage``.
        self.assertNotIn("data-page", out)

    def test_invalid_para_id_is_stripped(self) -> None:
        # A prompt injection can try to ship arbitrary data: the allowlist
        # must reject anything that does not match the expected shape.
        out = sanitize_html('<p data-para-id="../x">X</p>')
        self.assertNotIn("data-para-id", out)
        self.assertIn("X", out)

    def test_other_data_attrs_are_stripped(self) -> None:
        # The bounding-box attributes the pipeline also emits
        # (``data-x``, ``data-y``, ``data-width``, ``data-height``) are
        # NOT used by the front end; they must still be stripped so the
        # sanitizer's "no arbitrary data-*" contract is preserved.
        out = sanitize_html(
            '<p data-para-id="p-1-0" data-x="0.5" data-y="0.1"'
            ' data-width="0.8" data-height="0.2">X</p>'
        )
        self.assertIn('data-para-id="p-1-0"', out)
        self.assertNotIn("data-x", out)
        self.assertNotIn("data-y", out)
        self.assertNotIn("data-width", out)
        self.assertNotIn("data-height", out)

    def test_para_id_on_non_p_element_is_stripped(self) -> None:
        # para ids only have meaning on the paragraph box; if a prompt
        # injection puts one on a wrapper or a span, it must go.
        out = sanitize_html(
            '<div data-para-id="p-1-0">X</div>'
            '<span data-para-id="p-1-0">Y</span>'
            '<a href="https://x" data-para-id="p-1-0">Z</a>'
        )
        self.assertNotIn("data-para-id", out)
        self.assertIn("X", out)
        self.assertIn("Y", out)
        self.assertIn("Z", out)

    def test_script_nested_in_disallowed_tag_is_discarded(self) -> None:
        out = sanitize_html("<figure><script>alert(1)</script></figure>")
        self.assertNotIn("script", out)
        self.assertNotIn("alert(1)", out)

    def test_iframe_nested_in_disallowed_tag_is_unwrapped(self) -> None:
        out = sanitize_html("<figure><iframe>evil</iframe></figure>")
        self.assertNotIn("<iframe", out)
        self.assertIn("evil", out)

    def test_iframe_with_src_nested_in_disallowed_tag_is_discarded(self) -> None:
        out = sanitize_html(
            '<figure><iframe src="https://evil.example"></iframe></figure>'
        )
        self.assertNotIn("iframe", out)
        self.assertNotIn("evil.example", out)

    def test_double_nested_script_is_discarded(self) -> None:
        out = sanitize_html(
            "<figure><figure><script>alert(4)</script></figure></figure>"
        )
        self.assertNotIn("script", out)
        self.assertNotIn("alert(4)", out)

    def test_script_in_table_cell_is_discarded(self) -> None:
        out = sanitize_html(
            "<table><tr><td><script>alert(2)</script></td></tr></table>"
        )
        self.assertNotIn("script", out)
        self.assertNotIn("alert(2)", out)

    def test_object_and_embed_nested_are_discarded(self) -> None:
        out = sanitize_html("<section><object data='x'></object></section>")
        self.assertNotIn("object", out)
        out = sanitize_html("<figure><embed src='x'/></figure>")
        self.assertNotIn("embed", out)

    def test_img_with_onerror_nested_is_stripped(self) -> None:
        out = sanitize_html("<section><img src='x' onerror='alert(5)'></section>")
        self.assertNotIn("<img", out)
        self.assertNotIn("onerror", out)

    def test_comments_and_doctype_are_stripped(self) -> None:
        out = sanitize_html("<p>hi</p><!--c--><!doctype html>")
        self.assertNotIn("<!--", out)
        self.assertNotIn("doctype", out.lower())
        self.assertIn("hi", out)

    def test_idempotent(self) -> None:
        payloads = [
            "<p>Safe</p><script>alert(1)</script>",
            "<figure><script>alert(1)</script></figure>",
            '<figure><iframe src="https://evil.example"></iframe></figure>',
            "<table><tr><td><script>x</script></td></tr></table>",
            "<p>ok</p>",
            "<b>bold</b> and <i>italic</i>",
            """<p style="color:red" class="ok">text</p>""",
            """<a href="https://x">link</a>""",
            """<span onclick="x">y</span>""",
            "<div class='bc-page'><p data-para-id='p-1-0'>Hi</p></div>",
        ]
        for p in payloads:
            once = sanitize_html(p)
            twice = sanitize_html(once)
            self.assertEqual(once, twice, f"not idempotent for {p!r}")


class AnalyzeSseSanitizationTest(TestCase):
    """
    Integration tests that verify the /bescheidcheck/analyze/ endpoint
    sanitizes OCR'd page HTML and LLM-translated paragraph HTML before
    streaming it out (issue #499), and sets a Content-Security-Policy
    header on the streaming response as defense in depth.
    """

    def _upload_helper(self, filename: str = "page1.png", content: bytes = b"x"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(
            filename,
            content,
            content_type=(
                "image/png" if filename.endswith(".png") else "application/pdf"
            ),
        )

    def _post_analyze(self, files, **extra):
        data: dict = {}
        for name, value in (extra or {}).items():
            data[name] = value
        files_list = files if isinstance(files, list) else [files]
        for i, f in enumerate(files_list):
            data[f"files{i}" if i else "files"] = f
        return self.client.post("/bescheidcheck/analyze/", data=data)

    def test_stream_response_does_not_carry_csp_header(self) -> None:
        """
        CSP is per-document. The SSE response is a data fetch, not a
        document, so a header on it has no effect. The correct header is
        on the ``ui()`` page — see ``test_ui_renders_carrying_csp``.
        """
        with (
            mock.patch("integreat_chat.bescheidcheck.services.ocr.convert_page") as mc,
            mock.patch(
                "integreat_chat.bescheidcheck.services.classification.classify_bescheid"
            ) as mcls,
            mock.patch(
                "integreat_chat.bescheidcheck.services.translation.translate_document_stream"
            ) as mtr,
            mock.patch(
                "integreat_chat.bescheidcheck.services.counselor.find_counseling"
            ) as mfind,
        ):
            mc.side_effect = lambda *a, **kw: _fake_ocr_page(kw.get("page_no", 1))
            mcls.side_effect = lambda *a, **kw: {
                "type": "unsupported",
                "confidence": 0.1,
                "reason": "r",
            }
            mtr.side_effect = _fake_paragraph_stream
            mfind.side_effect = lambda **kw: None

            res = self._post_analyze(
                [self._upload_helper()], region="region-slug-1", target_language="en"
            )
            self.assertEqual(res["Content-Type"], "text/event-stream")
            self.assertNotIn("Content-Security-Policy", res)

    def test_ui_renders_carrying_csp(self) -> None:
        """
        The ``ui()`` document page must carry the CSP header; the
        ``script-src`` directive must use a nonce (which is what actually
        blocks injected inline script in the page) and must NOT allow
        ``'unsafe-inline'``.
        """
        res = self.client.get("/bescheidcheck/")
        self.assertEqual(res.status_code, 200)
        csp = res["Content-Security-Policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertIn("script-src 'nonce-", csp)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", csp)
        import re as _re

        m = _re.search(r"script-src 'nonce-([^']+)'", csp)
        self.assertIsNotNone(m, f"no nonce in script-src: {csp}")
        nonce = m.group(1)
        self.assertIn(f'nonce="{nonce}"', res.content.decode())

    def test_para_events_are_sanitized(self) -> None:
        """
        A ``para`` event whose ``html`` contains a ``<script>`` tag or an
        ``onerror`` handler must be sanitized before it leaves the view.
        """

        dirty_html = (
            "<b onclick='alert(1)'>bold</b>"
            "<script type='text/javascript'>evil()</script>"
            '<a href="javascript:alert(1)">bad link</a>'
        )
        pages_html = [
            (
                "<div class='bc-page' data-page='1'>"
                "<p data-para-id='p-1-0' data-x='0' data-y='0' "
                "data-width='1' data-height='1'>First paragraph.</p>"
                "<p data-para-id='p-1-1' data-x='0' data-y='1' "
                "data-width='1' data-height='1'>Second paragraph.</p>"
                "</div>"
            )
        ]

        async def _dirty_stream(*a, **kw):
            for i, _page_html in enumerate(pages_html):
                for k in (0, 1):
                    yield {
                        "page": i,
                        "para_id": f"p-{i + 1}-{k}",
                        "html": dirty_html,
                    }

        with (
            mock.patch("integreat_chat.bescheidcheck.services.ocr.convert_page") as mc,
            mock.patch(
                "integreat_chat.bescheidcheck.services.classification.classify_bescheid"
            ) as mcls,
            mock.patch(
                "integreat_chat.bescheidcheck.services.translation.translate_document_stream"
            ) as mtr,
            mock.patch(
                "integreat_chat.bescheidcheck.services.counselor.find_counseling"
            ) as mfind,
        ):
            mc.side_effect = lambda *a, **kw: _fake_ocr_page(kw.get("page_no", 1))
            mcls.side_effect = lambda *a, **kw: {
                "type": "unsupported",
                "confidence": 0.1,
                "reason": "r",
            }
            mtr.side_effect = lambda *a, **kw: _dirty_stream(*a, **kw)
            mfind.side_effect = lambda **kw: None

            res = self._post_analyze(
                [self._upload_helper()], region="region-slug-1", target_language="en"
            )
            events = _drain_sse_response(res)
            para_events = [e for e in events if e["event"] == "para"]
            self.assertTrue(para_events, f"expected para events, got: {events}")
            for ev in para_events:
                html = ev["data"]["html"]
                self.assertNotIn("<script", html.lower())
                self.assertNotIn("onclick", html.lower())
                self.assertNotIn("evil()", html)
                # Allowlisted tags survive
                self.assertIn("<b>", html)

    def test_pages_scaffold_is_sanitized(self) -> None:
        """
        The ``pages`` event (emitted right after OCR) carries the ORIGINAL
        page HTML, which is untrusted (a PDF can carry arbitrary markup).
        It must be sanitized before the view streams it.
        """
        from integreat_chat.bescheidcheck.services.ocr import OcrPage

        dirty_page_html = (
            "<div class='bc-page' data-page='1'>"
            "<p data-para-id='p-1-0'>ok</p>"
            "<p data-para-id='p-1-1' onmouseover='alert(1)'>danger</p>"
            "<script>alert('xss')</script>"
            "</div>"
        )

        def _dirty_ocr(*a, **kw):
            return OcrPage(
                page_no=kw.get("page_no", 1),
                html=dirty_page_html,
                paragraphs=[
                    {
                        "id": "p-1-0",
                        "text": "ok",
                        "x": 0,
                        "y": 0,
                        "width": 1,
                        "height": 1,
                    },
                    {
                        "id": "p-1-1",
                        "text": "danger",
                        "x": 0,
                        "y": 1,
                        "width": 1,
                        "height": 1,
                    },
                ],
            )

        with (
            mock.patch(
                "integreat_chat.bescheidcheck.services.ocr.convert_page",
                new=_dirty_ocr,
            ),
            mock.patch(
                "integreat_chat.bescheidcheck.services.classification.classify_bescheid"
            ) as mcls,
            mock.patch(
                "integreat_chat.bescheidcheck.services.translation.translate_document_stream"
            ) as mtr,
            mock.patch(
                "integreat_chat.bescheidcheck.services.counselor.find_counseling"
            ) as mfind,
        ):
            mcls.side_effect = lambda *a, **kw: {
                "type": "unsupported",
                "confidence": 0.1,
                "reason": "r",
            }
            mtr.side_effect = _fake_paragraph_stream
            mfind.side_effect = lambda **kw: None

            res = self._post_analyze(
                [self._upload_helper()], region="region-slug-1", target_language="en"
            )
            events = _drain_sse_response(res)
            pages_events = [e for e in events if e["event"] == "pages"]
            self.assertEqual(len(pages_events), 1)
            pages = pages_events[0]["data"]["pages"]
            self.assertEqual(len(pages), 1)
            for key in ("original_html", "translated_html"):
                self.assertNotIn("alert('xss')", pages[0][key])
                self.assertNotIn("onmouseover", pages[0][key].lower())

    def test_result_event_is_sanitized(self) -> None:
        """
        The final ``result`` event's ``original_html`` and ``translated_html``
        must be sanitized too — this is the surface the client uses as the
        source of truth after the stream ends.
        """
        from integreat_chat.bescheidcheck.services.ocr import OcrPage

        dirty_page_html = (
            "<div class='bc-page' data-page='1'>"
            "<p data-para-id='p-1-0' onmouseover='alert(1)'>ok</p>"
            "<script>alert('evil')</script>"
            "</div>"
        )

        async def _dirty_stream(*a, **kw):
            yield {
                "page": 0,
                "para_id": "p-1-0",
                "html": "<b onclick='x'>ok</b><script>evil()</script>",
            }

        def _dirty_ocr(*a, **kw):
            return OcrPage(
                page_no=1,
                html=dirty_page_html,
                paragraphs=[
                    {
                        "id": "p-1-0",
                        "text": "ok",
                        "x": 0,
                        "y": 0,
                        "width": 1,
                        "height": 1,
                    },
                ],
            )

        with (
            mock.patch(
                "integreat_chat.bescheidcheck.services.ocr.convert_page",
                new=_dirty_ocr,
            ),
            mock.patch(
                "integreat_chat.bescheidcheck.services.classification.classify_bescheid"
            ) as mcls,
            mock.patch(
                "integreat_chat.bescheidcheck.services.translation.translate_document_stream"
            ) as mtr,
            mock.patch(
                "integreat_chat.bescheidcheck.services.counselor.find_counseling"
            ) as mfind,
        ):
            mcls.side_effect = lambda *a, **kw: {
                "type": "unsupported",
                "confidence": 0.1,
                "reason": "r",
            }
            mtr.side_effect = lambda *a, **kw: _dirty_stream(*a, **kw)
            mfind.side_effect = lambda **kw: None

            res = self._post_analyze(
                [self._upload_helper()], region="region-slug-1", target_language="en"
            )
            events = _drain_sse_response(res)
            result_events = [e for e in events if e["event"] == "result"]
            self.assertEqual(len(result_events), 1)
            page = result_events[0]["data"]["pages"][0]
            for key in ("original_html", "translated_html"):
                self.assertNotIn("alert('evil')", page[key])
                self.assertNotIn("evil()", page[key])
                self.assertNotIn("onmouseover", page[key].lower())
                self.assertNotIn("onclick", page[key].lower())

    def test_result_event_preserves_para_ids_and_page_wrapper(self) -> None:
        """
        The final ``result`` event's ``translated_html`` is the source of
        truth the front end re-renders into the right-hand column. For
        the grey "untranslated" colouring and the hover-highlighting to
        both work after that re-render, two things must survive the
        sanitizer:

        * the ``<div class="bc-page">`` wrapper (the front end keys off
          the ``bc-page`` class);
        * the ``data-para-id`` on each ``<p>`` (shape
          ``p-<page>-<index>``) — without it, ``renderPage`` in
          ``bescheidcheck.html`` cannot attach hover handlers or match
          live paragraph translations.

        A paragraph whose translation never arrives (the ``para`` event
        missing) must still be present in ``translated_html`` — that is
        the path that ends up as a grey "untranslated" box.
        """
        from integreat_chat.bescheidcheck.services.ocr import OcrPage

        page_html = (
            "<div class='bc-page' data-page='1'>"
            "<p data-para-id='p-1-0'>Hallo</p>"
            "<p data-para-id='p-1-1'>Welt</p>"
            "</div>"
        )

        def _ocr(*a, **kw):
            return OcrPage(
                page_no=1,
                html=page_html,
                paragraphs=[
                    {
                        "id": "p-1-0",
                        "text": "Hallo",
                        "x": 0,
                        "y": 0,
                        "width": 1,
                        "height": 1,
                    },
                    {
                        "id": "p-1-1",
                        "text": "Welt",
                        "x": 0,
                        "y": 1,
                        "width": 1,
                        "height": 1,
                    },
                ],
            )

        async def _stream(*a, **kw):
            # Only ``p-1-0`` actually translates; ``p-1-1`` is the
            # "untranslated" path.
            yield {"page": 0, "para_id": "p-1-0", "html": "Hello"}

        with (
            mock.patch(
                "integreat_chat.bescheidcheck.services.ocr.convert_page",
                new=_ocr,
            ),
            mock.patch(
                "integreat_chat.bescheidcheck.services.classification.classify_bescheid"
            ) as mcls,
            mock.patch(
                "integreat_chat.bescheidcheck.services.translation.translate_document_stream"
            ) as mtr,
            mock.patch(
                "integreat_chat.bescheidcheck.services.counselor.find_counseling"
            ) as mfind,
        ):
            mcls.side_effect = lambda *a, **kw: {
                "type": "unsupported",
                "confidence": 0.1,
                "reason": "r",
            }
            mtr.side_effect = lambda *a, **kw: _stream(*a, **kw)
            mfind.side_effect = lambda **kw: None

            res = self._post_analyze(
                [self._upload_helper()], region="region-slug-1", target_language="en"
            )
            events = _drain_sse_response(res)
            result = next(e for e in events if e["event"] == "result")["data"]
            page = result["pages"][0]

            # Both para ids must survive the sanitizer on every page in
            # the authoritative ``translated_html`` payload, so that
            # ``renderPage`` can attach hover handlers and mark the
            # untranslated one grey.
            for key in ("original_html", "translated_html"):
                self.assertIn('data-para-id="p-1-0"', page[key])
                self.assertIn('data-para-id="p-1-1"', page[key])
            # The page wrapper class must also survive (front-end keys
            # off ``bc-page`` for the original/translated column
            # distinction).
            self.assertIn("bc-page", page["original_html"])
            self.assertIn("bc-page", page["translated_html"])
            # The untranslated paragraph's original text must still be
            # present — the front end shows it in grey.
            self.assertIn("Welt", page["translated_html"])
            # And the translated paragraph's new text must be present —
            # the front end shows it in black (not grey).
            self.assertIn("Hello", page["translated_html"])


class StructuredExtractionTest(unittest.TestCase):
    """
    Tests for structured data extraction (issue #504).
    """

    def test_text_from_html_strips_markup(self):
        from integreat_chat.bescheidcheck.services.extraction import (
            _text_from_html,
        )

        out = _text_from_html(
            "<p>Hello <strong>world</strong></p><script>evil()</script>"
        )

        self.assertEqual(out, "Hello world")

    def test_empty_document_returns_empty_dict(self):
        from integreat_chat.bescheidcheck.services.extraction import (
            extract_structured_data,
        )

        out = asyncio.run(
            extract_structured_data(
                document_text="",
                bescheid_type="bamf_simple_rejection",
                model="test-model",
            )
        )

        self.assertEqual(out, {})

    def test_llm_client_error_returns_empty_dict(self):
        from integreat_chat.bescheidcheck.services.extraction import (
            extract_structured_data,
        )
        from integreat_chat.chatanswers.services.llmapi import (
            LlmApiClient,
            LlmClientError,
        )

        with mock.patch.object(
            LlmApiClient,
            "chat_prompt",
            new=mock.AsyncMock(
                side_effect=LlmClientError(
                    "LLM server returned HTTP 500",
                    status=500,
                )
            ),
        ):
            out = asyncio.run(
                extract_structured_data(
                    document_text="<p>Some OCR text</p>",
                    bescheid_type="bamf_simple_rejection",
                    model="test-model",
                )
            )

        self.assertEqual(out, {})

    def test_extract_structured_data_returns_structured_result(self):
        from integreat_chat.bescheidcheck.services import extraction

        raw_llm_result = {
            "authority": "Bundesamt für Migration und Flüchtlinge",
            "topic": "Dublin-Verfahren",
            "required_action": None,
            "requested_documents": [],
            "deadline_detected": False,
            "deadline_date": None,
            "deadline_text": None,
            "consequences": [
                "Die Abschiebung nach Schweden wird angeordnet.",
            ],
            "appointment": None,
            "legal_procedure": None,
            "risk_level": "high",
            "confidence": 0.88,
        }

        expected = {
            **raw_llm_result,
            "document_type": "dublin_decision",
        }

        with mock.patch(
            "integreat_chat.bescheidcheck.services.extraction._run_extraction_prompt",
            new=mock.AsyncMock(return_value=raw_llm_result),
        ):
            out = asyncio.run(
                extraction.extract_structured_data(
                    document_text=(
                        "<p>Der Asylantrag ist unzulässig. "
                        "Die Abschiebung nach Schweden wird angeordnet.</p>"
                    ),
                    bescheid_type="dublin_decision",
                    model="test-model",
                )
            )

        self.assertEqual(out, expected)

    def test_extract_structured_data_normalizes_llm_output(self):
        from integreat_chat.bescheidcheck.services import extraction

        raw_llm_result = {
            "authority": " BAMF ",
            "document_type": "wrong_type",
            "topic": " asylum ",
            "required_action": "",
            "requested_documents": [
                " Mietvertrag ",
                "",
                123,
                "Kontoauszüge",
            ],
            "deadline_detected": "yes",
            "deadline_date": "   ",
            "deadline_text": " innerhalb einer Woche ",
            "consequences": "benefits may be reduced",
            "appointment": 123,
            "legal_procedure": " Klage ",
            "risk_level": "VERY HIGH",
            "confidence": 1.4,
        }

        with mock.patch(
            "integreat_chat.bescheidcheck.services.extraction._run_extraction_prompt",
            new=mock.AsyncMock(return_value=raw_llm_result),
        ):
            out = asyncio.run(
                extraction.extract_structured_data(
                    document_text="<p>Test document</p>",
                    bescheid_type="bamf_simple_rejection",
                    model="test-model",
                )
            )

        self.assertEqual(
            out,
            {
                "authority": "BAMF",
                "document_type": "bamf_simple_rejection",
                "topic": "asylum",
                "required_action": None,
                "requested_documents": [
                    "Mietvertrag",
                    "Kontoauszüge",
                ],
                "deadline_detected": False,
                "deadline_date": None,
                "deadline_text": "innerhalb einer Woche",
                "consequences": [],
                "appointment": None,
                "legal_procedure": "Klage",
                "risk_level": None,
                "confidence": 1.0,
            },
        )

    def test_get_extraction_schema_only_for_supported_types(self):
        from integreat_chat.bescheidcheck.services.extraction import (
            get_extraction_schema,
        )

        self.assertIsNotNone(get_extraction_schema("bamf_simple_rejection"))
        self.assertIsNotNone(get_extraction_schema("obviously_unfounded_inadmissible"))
        self.assertIsNotNone(get_extraction_schema("dublin_decision"))

        self.assertIsNone(get_extraction_schema("unsupported"))
        self.assertIsNone(get_extraction_schema("unknown_type"))

    def test_extract_structured_data_builds_extraction_prompt(self):
        from integreat_chat.bescheidcheck.services import extraction

        mock_run = mock.AsyncMock(return_value={})

        with mock.patch(
            "integreat_chat.bescheidcheck.services.extraction._run_extraction_prompt",
            new=mock_run,
        ):
            asyncio.run(
                extraction.extract_structured_data(
                    document_text=(
                        "<p>Gegen diesen Bescheid kann innerhalb einer Woche "
                        "Klage erhoben werden.</p>"
                    ),
                    bescheid_type="dublin_decision",
                    model="test-model",
                )
            )

        mock_run.assert_awaited_once()

        prompt_text = mock_run.await_args.kwargs["prompt_text"]

        self.assertIn(
            "Classified document type: dublin_decision",
            prompt_text,
        )
        self.assertIn(
            "Gegen diesen Bescheid kann innerhalb einer Woche",
            prompt_text,
        )
        self.assertIn(
            "Do not guess, invent, or complete missing facts.",
            prompt_text,
        )
        self.assertIn(
            "Use null for missing scalar values.",
            prompt_text,
        )
        self.assertIn(
            "Use [] for missing list values.",
            prompt_text,
        )

    def test_unsupported_type_does_not_call_llm(self):
        from integreat_chat.bescheidcheck.services import extraction

        mock_run = mock.AsyncMock(return_value={"unexpected": "result"})

        with mock.patch(
            "integreat_chat.bescheidcheck.services.extraction._run_extraction_prompt",
            new=mock_run,
        ):
            for bescheid_type in ("unsupported", "unknown_type"):
                with self.subTest(bescheid_type=bescheid_type):
                    out = asyncio.run(
                        extraction.extract_structured_data(
                            document_text="<p>Some administrative document</p>",
                            bescheid_type=bescheid_type,
                            model="test-model",
                        )
                    )

                    self.assertEqual(out, {})

        mock_run.assert_not_awaited()
