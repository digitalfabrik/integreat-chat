"""
OCR pipeline for the bescheidcheck app (issue #492).

Docling is the primary OCR engine. Importing docling is expensive
(loads torch etc.), so we import it lazily inside the functions.
If docling is not installed, callers can catch the resulting
exceptions and return a 503 with a clear error message.

Pages are converted one by one via ``DocumentConverter.convert`` so that
the per-page bounding boxes are produced against a 1-page image.
The converter is created once and cached on the module.
"""

import html
import logging
import re
import threading
import time

from bs4 import BeautifulSoup

from .sanitizer import sanitize_html

LOGGER = logging.getLogger(__name__)

_converter = None
_converter_lock = threading.Lock()


class OcrPage:
    """
    One OCR'd page.

    page_no: 1-based page number within the original source document
    html: HTML markup, one <p data-para-id=...> per paragraph
    paragraphs: list of dicts with keys id/text/x/y/width/height.
        x/y/width/height are normalized to [0, 1] relative to the page.
    """

    def __init__(
        self,
        page_no: int,
        html: str,
        paragraphs: list[dict] | None = None,
    ) -> None:
        self.page_no = page_no
        self.html = html
        self.paragraphs = paragraphs or []

    def as_dict(self) -> dict:
        """
        Return JSON-serializable dict
        """
        return {
            "page_no": self.page_no,
            "html": self.html,
            "paragraphs": self.paragraphs,
        }


def _pipeline_options():
    """
    Docling pipeline options for our use case (PDF pages and images).

    * ``do_table_structure=False`` avoids instantiating the TableFormer
      model, whose backend imports OpenCV and thus requires
      libxcb.so.1 on the host.
    * ``ocr_options`` pins the RapidOCR engine instead of docling's
      "auto" selector, which can silently fall through to *no engine at
      all* if every import probe fails.
    * ``mode=OcrMode.FULL_PAGE`` feeds the whole page image to RapidOCR
      directly. The default layout-model-first path can return an empty
      result for phone photos (no detected regions) and is much slower
      on CPU.

    The remaining knobs (``lang``, ``scale``, ``text_score``,
    ``rapidocr_params``) come from ``settings.BESCHEID_OCR``.
    """
    from django.conf import settings
    from docling.datamodel import pipeline_options as _po

    ocr_cfg = dict(getattr(settings, "BESCHEID_OCR", {}) or {})
    ocr_cfg.setdefault("lang", "de")
    ocr_cfg.setdefault("scale", 2.0)
    ocr_cfg.setdefault("backend", "torch")
    ocr_cfg.setdefault("text_score", 0.5)
    rapidocr_kwargs = {
        "lang": [ocr_cfg["lang"]],
        "scale": ocr_cfg["scale"],
        "backend": ocr_cfg["backend"],
        "text_score": ocr_cfg["text_score"],
        "mode": _po.OcrMode.FULL_PAGE,
    }
    if ocr_cfg.get("rapidocr_params"):
        rapidocr_kwargs["rapidocr_params"] = dict(ocr_cfg["rapidocr_params"])

    return _po.PdfPipelineOptions(
        do_table_structure=False,
        ocr_options=_po.RapidOcrOptions(**rapidocr_kwargs),
    )


def _get_converter():
    """
    Lazy singleton for the Docling DocumentConverter.
    """
    global _converter
    if _converter is None:
        with _converter_lock:
            if _converter is None:
                # Imported lazily: docling pulls in torch etc.
                from docling import document_converter as _dc
                from docling.datamodel.base_models import InputFormat

                options = _pipeline_options()
                _converter = _dc.DocumentConverter(
                    format_options={
                        InputFormat.PDF: _dc.PdfFormatOption(pipeline_options=options),
                        InputFormat.IMAGE: _dc.ImageFormatOption(
                            pipeline_options=options
                        ),
                    }
                )
    return _converter


def _get_docling_types():
    """
    Import the heavy docling_core types once.
    """
    from docling_core.types.doc import CoordOrigin

    return CoordOrigin


def _resolve_internal_page(document, page_no: int) -> int:
    """
    Map the caller's (global/1-based) ``page_no`` onto document's own
    internal 1-based page numbering.

    Docling numbers its own pages 1..N per document and always 1 for a
    single-page document, while callers pass a *global* running index
    (1, 2, 3, ...) that can point past the end of a 1-page document.
    Resolve onto the internal numbering so the size lookup and the
    provenance filter stay consistent.
    """
    pages = getattr(document, "pages", {}) or {}
    n_docs = len(pages)
    if n_docs and 1 <= page_no <= n_docs:
        return page_no
    if n_docs == 1:
        return 1
    return min(pages) if pages else 1


def _build_paragraphs(
    document,
    page_no: int,
    page_size,
    label_no: int | None = None,
):
    """
    Extract paragraphs (text + normalized bounding boxes) for a single
    page.

    param document: DoclingDocument
    param page_no: *internal* 1-based page number (see
        _resolve_internal_page)
    param page_size: docling_core.types.doc.Size (width, height)
    param label_no: 1-based page number for the generated
        ``data-para-id`` / ``data-page`` attributes. Defaults to
        ``page_no``.
    return: (sorted list of paragraph dicts, list of paragraph ids in order)
    """
    CoordOrigin = _get_docling_types()
    label_no = page_no if label_no is None else label_no

    page_width = float(page_size.width or 0) or 1.0
    page_height = float(page_size.height or 0) or 1.0

    paragraphs: list[dict] = []
    ordered_ids: list[str] = []

    # Body tree traversal in reading order via the `texts` list is fine
    # for the MVP: we skip furniture items (header/footer) and keep
    # paragraphs and section headers.
    for index, item in enumerate(document.texts):
        try:
            provs = item.prov or []
        except AttributeError:
            provs = item.prov
        if not provs:
            continue
        # Keep items with this page's provenance plus page-neutral items
        # (``page_no`` is None / missing).
        page_provs = [
            p for p in provs if getattr(p, "page_no", None) in (page_no, None)
        ]
        if not page_provs:
            continue
        bbox = page_provs[0].bbox
        if bbox is None:
            continue
        try:
            if bbox.coord_origin != CoordOrigin.TOPLEFT:
                bbox = bbox.to_top_left_origin(page_height)
        except AttributeError:
            pass
        x = float(getattr(bbox, "l", 0) or 0) / page_width
        y = float(getattr(bbox, "t", 0) or 0) / page_height
        w = float(getattr(bbox, "width", 0) or 0) / page_width
        h = float(getattr(bbox, "height", 0) or 0) / page_height
        x, y, w, h = (max(0.0, min(1.0, v)) for v in (x, y, max(w, 1e-6), max(h, 1e-6)))

        text = (item.text or "").strip()
        if not text:
            continue

        label_str = str(getattr(item, "label", "") or "")
        if label_str in ("PAGE_HEADER", "PAGE_FOOTER"):
            continue

        para_id = f"p-{label_no}-{index}"
        paragraphs.append(
            {
                "id": para_id,
                "text": text,
                "x": round(x, 6),
                "y": round(y, 6),
                "width": round(w, 6),
                "height": round(h, 6),
            }
        )
        ordered_ids.append(para_id)

    return paragraphs, ordered_ids


def _render_page_html(paragraphs: list[dict], page_no: int) -> str:
    """
    Render the HTML for one page as a list of <p data-para-id=...> blocks,
    carrying normalized bounding boxes as data-* attributes for the
    highlight overlays.

    All values are HTML-escaped: the UI inserts this string via
    ``innerHTML``, so OCR text containing ``<``, ``>``, ``&`` must not
    produce markup.
    """

    def esc(value: object) -> str:
        return html.escape(str(value), quote=True)

    parts = [f'<div class="bc-page" data-page="{esc(page_no)}">']
    ordered = sorted(
        paragraphs,
        key=lambda p: (round(p["y"], 4), round(p["x"], 4), p["id"]),
    )
    for para in ordered:
        body = esc(re.sub(r"\s+", " ", para["text"]).strip())
        parts.append(
            f'<p data-para-id="{esc(para["id"])}" '
            f'data-x="{esc(para["x"])}" data-y="{esc(para["y"])}" '
            f'data-width="{esc(para["width"])}" data-height="{esc(para["height"])}">'
            f"{body}</p>"
        )
    parts.append("</div>")
    return "".join(parts)


def convert_page(path: str, page_no: int = 1, max_num_pages: int = 1) -> OcrPage:
    """
    Convert a single page of a PDF (or the whole file, for images) to
    an OcrPage with HTML + normalized bounding boxes.

    param path: filesystem path to the source file (PDF or image)
    param page_no: 1-based page index within the source file to treat
        as "this page" (1 by default; used when the source is an image
        or a 1-page PDF)
    param max_num_pages: hard limit passed to docling
    return: OcrPage instance
    """
    converter = _get_converter()
    started = time.monotonic()
    result = converter.convert(
        path,
        max_num_pages=max_num_pages,
        raises_on_error=True,
    )
    docling_elapsed = time.monotonic() - started
    document = result.document
    if document is None:
        raise RuntimeError(f"docling returned no document for {path}")

    internal_page_no = _resolve_internal_page(document, page_no)

    # Find the page size for the page we are looking at.
    pages = getattr(document, "pages", {}) or {}
    page_info = pages.get(internal_page_no)
    if page_info is None:
        page_info = next(iter(pages.values()), None)
    page_size = getattr(page_info, "size", None) if page_info else None

    n_text_items = len(getattr(document, "texts", ()) or ())
    build_started = time.monotonic()
    paragraphs, _ordered = _build_paragraphs(
        document,
        internal_page_no,
        page_size,
        label_no=page_no,
    )
    html = _render_page_html(paragraphs, page_no)
    build_elapsed = time.monotonic() - build_started
    total_elapsed = time.monotonic() - started
    LOGGER.info(
        "ocr.convert(%s) docling=%.2fs (text_items=%s) build=%.2fs "
        "paragraphs=%s total=%.2fs",
        path,
        round(docling_elapsed, 2),
        n_text_items,
        round(build_elapsed, 2),
        len(paragraphs),
        round(total_elapsed, 2),
    )

    # Best-effort fallback: if the per-page extraction above produced
    # nothing, use the global HTML export instead of an empty page.
    if not paragraphs:
        LOGGER.warning(
            "Per-page paragraph extraction was empty for page %s of %s, "
            "falling back to the global HTML export.",
            page_no,
            path,
        )
        try:
            html = document.export_to_html() or ""
            # Docling's HTML export is not escaped and document text can
            # contain markup; sanitize it (issue #499).
            html = sanitize_html(html)
            soup = BeautifulSoup(html, "lxml")
            if soup is not None:
                # Attach para ids so the highlight overlay still works;
                # operate on the sanitized fragment.
                # lxml wraps a fragment in <html><body> for block-level
                # content.
                body = soup.find("body")
                if body is not None:
                    soup_root = body
                else:
                    soup_root = soup
                for i, p in enumerate(soup_root.find_all("p")):
                    p["data-para-id"] = f"p-{page_no}-fallback-{i}"
                if body is not None:
                    html = body.decode_contents()
                else:
                    html = soup.decode()
                html = sanitize_html(html)
        except Exception:
            LOGGER.exception("Fallback HTML export failed for %s", path)
            html = ""

    return OcrPage(page_no=page_no, html=html, paragraphs=paragraphs)


def split_pdf_pages(
    pdf_path: str, max_num_pages: int, out_dir: str | None = None
) -> list[str]:
    """
    Split a PDF into individual 1-page PDFs in a temp dir.
    Returns a list of page file paths, in original page order.

    ``out_dir`` defaults to a fresh temp dir which the *caller* must
    remove (the view writes these next to the uploads in its own
    temp dir and removes it in ``finally``); pass ``out_dir`` to own
    the cleanup yourself.

    Uses pypdf (lightweight); raises ImportError if pypdf is missing.
    """
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as exc:
        raise RuntimeError("pypdf is required to split PDFs") from exc

    import os
    import tempfile

    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    if total == 0:
        # Do NOT include the disk path: the view surfaces str(exc) to the
        # client, and absolute temp paths are an information leak.
        raise ValueError(
            "The PDF is empty or malformed (it contains no pages). "
            "Please upload a different file."
        )
    if total > max_num_pages:
        LOGGER.warning(
            "PDF %s has %d pages, only the first %d will be processed",
            pdf_path,
            total,
            max_num_pages,
        )

    out_dir = out_dir or tempfile.mkdtemp(prefix="bescheidcheck-")
    out_paths: list[str] = []
    for idx in range(min(total, max_num_pages)):
        writer = PdfWriter()
        writer.add_page(reader.pages[idx])
        out_path = os.path.join(out_dir, f"page-{idx + 1:03d}.pdf")
        with open(out_path, "wb") as f:
            writer.write(f)
        out_paths.append(out_path)
    return out_paths
