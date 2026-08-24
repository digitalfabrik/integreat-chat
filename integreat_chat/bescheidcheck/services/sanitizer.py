"""
Sanitizer for HTML produced by the bescheidcheck pipeline.

OCR'd page text and LLM translation output are both untrusted: a PDF can
contain markup and a local LLM can be prompt-injected into emitting
``<script>`` or ``on*`` handlers. The output is inserted via
``innerHTML``, so :func:`sanitize_html` enforces a small allowlist:

* tags not in ``_ALLOWED_TAGS`` are unwrapped (text kept), and
  ``_DISCARDED_TAGS`` (``script``, ``style``, ``svg``, ``math``, ...)
  are removed entirely — including when nested inside another disallowed
  tag;
* comments, doctypes and processing instructions are stripped;
* attributes are limited to an allowlist — in particular ``on*``
  handlers and ``style`` are always stripped, and only the OCR pipeline's
  ``data-para-id`` (shape ``p-<page>-<index>`` or the fallback export's
  ``p-<page>-fallback-<index>``) on ``<p>`` survives, so
  no arbitrary ``data-*`` payload can ship through the response.

The front end depends on that single ``data-para-id`` (plus the
``bc-page`` wrapper) to match live paragraph translations and hover
highlighting, which is the only markup deliberately preserved.
"""

import re

from bs4 import BeautifulSoup, Tag
from bs4.element import (
    CData,
    Comment,
    Declaration,
    Doctype,
    ProcessingInstruction,
)

_DISCARDED_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "object",
    "embed",
    "svg",
    "math",
}
_DISCARDED_STRING_TYPES = (
    Comment,
    Doctype,
    CData,
    ProcessingInstruction,
    Declaration,
)
_ALLOWED_TAGS = {
    "b",
    "i",
    "em",
    "strong",
    "u",
    "a",
    "br",
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
}
_CLASS_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_ALLOWED_URL_PREFIXES = ("http://", "https://", "data:image/")
# The OCR pipeline (ocr.py ``_build_paragraphs``) generates paragraph ids
# of the form ``p-<page_no>-<index>`` (e.g. ``p-1-0``); the Docling HTML
# fallback in ocr.py ``convert_page`` generates ``p-<page_no>-fallback-<i>``.
# Only those two shapes are kept in ``data-para-id``, so no arbitrary
# data-* payload can ship out.
_PARA_ID_RE = re.compile(r"^p-\d+-(?:\d+|fallback-\d+)$")


def _is_safe_url(value: str) -> bool:
    """
    True if the URL starts with an allowed web or image-data scheme.
    """
    stripped = re.sub(r"[\x00-\x20]+", "", value)
    return stripped.lower().startswith(_ALLOWED_URL_PREFIXES)


def _clean_attributes(tag: Tag) -> None:
    """
    Remove every attribute on ``tag`` that is not in the allowlist.
    """
    name = tag.name.lower() if tag.name else ""
    for attr in list(tag.attrs):
        if attr == "class":
            raw = tag.attrs["class"]
            if isinstance(raw, str):
                kept = [c for c in raw.split() if _CLASS_RE.match(c)]
            elif isinstance(raw, (list, tuple)):
                kept = [c for c in raw if isinstance(c, str) and _CLASS_RE.match(c)]
            else:
                kept = []
            if kept:
                tag.attrs["class"] = kept
            else:
                del tag.attrs["class"]
        elif attr == "href" and name == "a":
            value = tag.attrs["href"]
            if isinstance(value, str) and _is_safe_url(value):
                tag.attrs["href"] = value.strip()
            else:
                del tag.attrs["href"]
        elif attr == "src":
            value = tag.attrs["src"]
            if isinstance(value, str) and _is_safe_url(value):
                tag.attrs["src"] = value.strip()
            else:
                del tag.attrs["src"]
        elif attr == "data-para-id" and name == "p":
            value = tag.attrs["data-para-id"]
            if isinstance(value, str) and _PARA_ID_RE.match(value):
                pass
            else:
                del tag.attrs["data-para-id"]
        else:
            del tag.attrs[attr]


def _clean_children(node: Tag) -> None:
    """
    Remove or unwrap every direct child of ``node`` that is not allowed.
    Re-scans to a fixed point because ``Tag.unwrap`` promotes the
    child's own children into ``node`` after the iteration snapshot.
    """
    while True:
        changed = False
        for child in list(node.children):
            if isinstance(child, _DISCARDED_STRING_TYPES):
                child.extract()
                changed = True
            elif isinstance(child, Tag):
                name = (child.name or "").lower()
                if name in _DISCARDED_TAGS:
                    child.extract()
                    changed = True
                elif name not in _ALLOWED_TAGS:
                    child.unwrap()
                    changed = True
        if not changed:
            return


def _clean_tree(root: Tag) -> None:
    """
    Iteratively sanitize the tree rooted at ``root``.
    """
    pending: list[Tag] = [root]
    while pending:
        node = pending.pop()
        _clean_children(node)
        _clean_attributes(node)
        pending.extend(child for child in node.children if isinstance(child, Tag))


def sanitize_html(html: str) -> str:
    """
    Sanitize an untrusted HTML fragment down to the bescheidcheck
    allowlist.

    param html: HTML string (may contain script tags, on* handlers,
        javascript: URLs, arbitrary markup)
    return: sanitized HTML string, safe for ``innerHTML``
    """
    if not html or not html.strip():
        return ""
    soup = BeautifulSoup(html, "html.parser")
    _clean_tree(soup)
    return soup.decode().strip()
