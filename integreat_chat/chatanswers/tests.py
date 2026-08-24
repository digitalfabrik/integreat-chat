"""
Regression tests for the chat / translate views: when the LLM server
returns an HTTP >= 400, ``LlmApiClient.chat_prompt`` raises
``LlmClientError``. The views must catch this and return a clean
``{"status": "error", ...}`` JSON response (500 / 503) - NOT an
unhandled traceback.

Before the fix (commit c102063), only ``bescheidcheck`` caught this
exception; the existing chat / translate endpoints would 500 /
traceback the moment the LLM server returned an error.

``decode_byte_tokens`` tests lock in the regex fix (missing closing
paren on the per-token capture group in commit c102063).
"""

import unittest
from unittest import mock

from django.test import TestCase

from integreat_chat.chatanswers.services.answer import AnswerService
from integreat_chat.chatanswers.services.llmapi import LlmClientError


class DecodeByteTokensTest(unittest.TestCase):
    """
    ``decode_byte_tokens`` must handle byte-fallback token runs like
    ``<0xE2><0x80><0xAF>``. The per-token capture group had a missing
    closing paren in commit c102063, so the regex did not compile.

    These tests would raise ``re.PatternError`` on the pre-fix code.
    """

    def setUp(self):
        from integreat_chat.chatanswers.services.llmapi import decode_byte_tokens

        self.decode = decode_byte_tokens

    def test_single_byte_token(self):
        # "<0x21>" is "!" in UTF-8; a single token should decode.
        self.assertEqual(self.decode("<0x21>"), "!")

    def test_multi_token_run(self):
        # UTF-8 for U+202F (narrow no-break space): 0xE2 0x80 0xAF.
        self.assertEqual(self.decode("a<0xE2><0x80><0xAF>b"), "a\u202fb")

    def test_dotted_run(self):
        # UTF-8 for U+00B7 (middle dot): 0xC2 0xB7.
        self.assertEqual(self.decode("a<0xC2><0xB7>b"), "a\xb7b")

    def test_plain_text_passes_through(self):
        self.assertEqual(self.decode("no tokens at all"), "no tokens at all")


class LlmClientErrorViewContractTest(TestCase):
    """
    When the LLM server errors, the chat endpoint must degrade
    gracefully instead of propagating the exception to Django
    (which would render a 500 with a traceback).
    """

    @mock.patch.object(
        AnswerService,
        "extract_answer",
        new=mock.AsyncMock(side_effect=LlmClientError("LLM server returned HTTP 500")),
    )
    def test_chat_view_catches_llm_client_error(self):
        res = self.client.post(
            "/chatanswers/chat/",
            data='{"message": "Hello?", "language": "en"}',
            content_type="application/json",
        )
        # Clean JSON - not a 500 traceback.
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "error")
        # The reason must not leak the raw status code.
        self.assertNotIn("500", body["message"].lower())


class ShallowSearchLlmClientErrorTest(TestCase):
    """
    The shallow-search fallback in ``AnswerService.get_documents`` re-enters
    the search and calls ``llm_api.simple_prompt`` to rewrite the query
    (``answer.py:199``). When the LLM server returns an HTTP >= 400, that
    raises ``LlmClientError``.

    This test drives the real view end-to-end with zero relevant documents
    (so the shallow-search fallback is entered) and the LLM mock raising
    ``LlmClientError``. The view's ``except LlmClientError`` (views.py:36)
    already turns this into a clean ``{"status": "error"}`` 200 response —
    this test locks in that contract for the *shallow-search path
    specifically*, so a regression that swallows or lets it 500 in
    ``get_documents`` would be caught.
    """

    @mock.patch.object(
        AnswerService,
        "get_documents",
        new=mock.AsyncMock(
            side_effect=LlmClientError("LLM server returned HTTP 500", status=500)
        ),
    )
    @mock.patch.object(
        AnswerService,
        "skip_rag_answer",
        new=mock.AsyncMock(return_value=False),
    )
    def test_shallow_search_failure_yields_clean_error_response(self):
        res = self.client.post(
            "/chatanswers/chat/",
            data='{"message": "Hello?", "language": "en"}',
            content_type="application/json",
        )
        # Clean JSON - not a 500 traceback, even on the shallow-search path.
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "error")
        # The reason must not leak the raw status code.
        self.assertNotIn("500", str(body).lower())


class TranslateLlmClientErrorContractTest(TestCase):
    """
    ``translate_message`` and ``message_to_region_languages`` must also
    catch ``LlmClientError`` and return a clean JSON 4xx/5xx instead of
    an unhandled traceback.
    """

    @mock.patch(
        "integreat_chat.translate.services.language.LanguageService.classify_language",
        new=mock.AsyncMock(side_effect=LlmClientError("LLM server returned HTTP 500")),
    )
    def test_translate_message_view_catches_llm_client_error(self):
        res = self.client.post(
            "/translate/message/",
            data='{"source_language": "de", "target_language": "en", "message": "Hallo Welt"}',
            content_type="application/json",
        )
        # Either 4xx (422) or 5xx (503) JSON - NOT a 500 with traceback.
        self.assertIn(res.status_code, (422, 503))
        body = res.json()
        self.assertEqual(body["status"], "error")
        # The reason must not leak the raw status code.
        self.assertNotIn("500", body["reason"].lower())

    @mock.patch(
        "integreat_chat.translate.views.async_get_region_languages",
        new=mock.AsyncMock(return_value=["en"]),
    )
    @mock.patch(
        "integreat_chat.translate.services.language.LanguageService.translate_message",
        new=mock.AsyncMock(side_effect=LlmClientError("LLM server returned HTTP 500")),
    )
    def test_message_to_region_languages_view_catches_llm_client_error(self):
        res = self.client.post(
            "/translate/message_to_region_languages/",
            data='{"source_language": "de", "region": "region-slug-1", "message": "Hallo Welt"}',
            content_type="application/json",
        )
        self.assertIn(res.status_code, (422, 503))
        body = res.json()
        self.assertEqual(body["status"], "error")
        self.assertNotIn("500", body["reason"].lower())
