"""PDF text extraction for inventory ingestion."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO

import pdfplumber
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PdfTextChunk:
    text: str
    first_page: int
    last_page: int


def extract_pdf_chunks(
    data: bytes,
    *,
    max_chars: int = 10_000,
    max_pages: int = 8,
) -> list[PdfTextChunk]:
    """
    Extract page-aware chunks suitable for bounded Bedrock requests.

    A supplied catalog is 60 pages, so one clipped prompt would silently omit
    most inventory. Chunks preserve page markers and never split a page.
    """
    pages = extract_pdf_pages(data)
    chunks = chunk_pdf_pages(pages, max_chars=max_chars, max_pages=max_pages)
    logger.info(
        "pdf_extracted pages=%s chunks=%s chars=%s",
        len(pages),
        len(chunks),
        sum(len(chunk.text) for chunk in chunks),
    )
    return chunks


def extract_pdf_pages(data: bytes) -> list[tuple[int, str]]:
    """Extract non-empty PDF pages once for deterministic or LLM parsing."""
    pages: list[tuple[int, str]] = []
    with pdfplumber.open(BytesIO(data)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append((page_number, text.strip()))
    return pages


def chunk_pdf_pages(
    pages: list[tuple[int, str]],
    *,
    max_chars: int = 10_000,
    max_pages: int = 8,
    listing_max_pages: int = 2,
) -> list[PdfTextChunk]:
    if max_chars < 1_000:
        raise ValueError("max_chars must be at least 1000")
    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")
    if listing_max_pages < 1:
        raise ValueError("listing_max_pages must be at least 1")

    chunks: list[PdfTextChunk] = []
    current: list[str] = []
    first_page: int | None = None
    last_page: int | None = None
    current_chars = 0
    current_page_limit = max_pages

    for page_number, text in pages:
        marked = f"[PAGE {page_number}]\n{text.strip()}"
        page_limit = (
            listing_max_pages if _looks_like_listing_page(text) else max_pages
        )
        if current and (
            current_chars + len(marked) + 2 > max_chars
            or len(current) >= min(current_page_limit, page_limit)
        ):
            chunks.append(
                PdfTextChunk(
                    text="\n\n".join(current),
                    first_page=first_page or page_number,
                    last_page=last_page or page_number,
                )
            )
            current = []
            first_page = None
            current_chars = 0
            current_page_limit = max_pages

        if first_page is None:
            first_page = page_number
        current_page_limit = min(current_page_limit, page_limit)
        current.append(marked)
        last_page = page_number
        current_chars += len(marked) + 2

    if current:
        chunks.append(
            PdfTextChunk(
                text="\n\n".join(current),
                first_page=first_page or 1,
                last_page=last_page or first_page or 1,
            )
        )
    return chunks


def _looks_like_listing_page(text: str) -> bool:
    """
    Detect dense visual/listing pages that can produce many output records.

    Detail catalogs usually label their body ``Description:``. The supplied
    visual chair catalog instead presents many names per page with no detail
    marker, so it needs smaller chunks to stay within Claude output limits.
    """
    non_empty_lines = [line for line in text.splitlines() if line.strip()]
    return "description:" not in text.lower() and len(non_empty_lines) >= 5


def is_visual_catalog(pages: list[tuple[int, str]]) -> bool:
    """Identify short, dense visual-grid catalogs that need multimodal parsing."""
    if not pages or len(pages) > 50:
        return False
    listing_pages = sum(_looks_like_listing_page(text) for _, text in pages)
    return listing_pages / len(pages) >= 0.6


def split_pdf_pages(
    data: bytes,
    page_numbers: list[int],
) -> list[tuple[int, bytes]]:
    """Return one valid PDF document per requested 1-based source page."""
    reader = PdfReader(BytesIO(data))
    result: list[tuple[int, bytes]] = []
    for page_number in page_numbers:
        if page_number < 1 or page_number > len(reader.pages):
            continue
        writer = PdfWriter()
        writer.add_page(reader.pages[page_number - 1])
        buffer = BytesIO()
        writer.write(buffer)
        result.append((page_number, buffer.getvalue()))
    return result
