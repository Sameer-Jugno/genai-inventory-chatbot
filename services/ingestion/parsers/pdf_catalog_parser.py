"""Deterministic parser for one-product-per-page rental catalog PDFs."""

from __future__ import annotations

import csv
import io
import re

from services.ingestion.parsers.csv_parser import CsvRow, parse_csv

_SKU_NAME = re.compile(
    r"^(?P<sku>[A-Z]{2,4}\d{2,5}(?:-[A-Z0-9]+)?)\s+(?P<name>.+)$"
)
_PRICE_QUANTITY = re.compile(
    r"\$(?P<price>\d+(?:\.\d+)?)"
    r"(?:\s+each)?\s*[—–-]\s*"
    r"(?P<quantity>\d+(?:\.\d+)?)\s+for\s+rent",
    re.IGNORECASE,
)
_DIMENSIONS = re.compile(
    r"\d+(?:\.\d+)?[″”\"]\s*[Hh].*[×x].*[″”\"]\s*[Ww]",
)


def parse_product_page_pdf(
    *,
    pages: list[tuple[int, str]],
    vendor: str,
    source_ref: str,
) -> list[CsvRow]:
    """
    Parse website-print PDFs where each product page has SKU, price, stock, dims.

    Returns an empty list when the template does not match, allowing the caller
    to use the general page-chunk + LLM extractor.
    """
    records: list[dict[str, str | int]] = []
    for page_number, text in pages:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        sku_match = next((_SKU_NAME.match(line) for line in lines if _SKU_NAME.match(line)), None)
        price_match = next(
            (_PRICE_QUANTITY.search(line) for line in lines if _PRICE_QUANTITY.search(line)),
            None,
        )
        if sku_match is None or price_match is None:
            continue
        dimensions = next((line for line in lines if _DIMENSIONS.search(line)), "")
        records.append(
            {
                "product_name": f"{sku_match.group('sku')} {sku_match.group('name')}",
                "source_item_id": sku_match.group("sku"),
                "description": sku_match.group("name"),
                "quantity": price_match.group("quantity"),
                "unit_price": price_match.group("price"),
                "dimensions": dimensions,
                "category": "seating",
                "tags": "seating, chair",
                "source_page": page_number,
            }
        )

    # Avoid false-positive template detection on arbitrary PDFs.
    if len(records) < 2:
        return []

    buffer = io.StringIO()
    fieldnames = (
        "product_name",
        "source_item_id",
        "description",
        "quantity",
        "unit_price",
        "dimensions",
        "category",
        "tags",
        "source_page",
    )
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(records)
    return parse_csv(content=buffer.getvalue(), vendor=vendor, source_ref=source_ref)
