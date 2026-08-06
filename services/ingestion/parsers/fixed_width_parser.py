"""Parser for fixed-width inventory exports produced by dataframe/table tooling."""

from __future__ import annotations

import csv
import io
import re

from services.ingestion.errors import InventoryFormatError
from services.ingestion.parsers.csv_parser import CsvRow, parse_csv

_SUPPORTED_HEADERS: dict[str, str] = {
    "product-link": "product_name",
    "product-link-href": "product_url",
    "product-description": "description",
    "product-quantity": "quantity",
    "product-price": "unit_price",
    "product-dimensions": "dimensions",
    "tags": "tags",
}


def parse_fixed_width_inventory(
    *,
    content: str,
    vendor: str,
    source_ref: str,
) -> list[CsvRow]:
    """
    Parse aligned text tables without requiring pandas in Lambda.

    The supplied sample is a pandas ``DataFrame.to_string`` export. In that
    format each header and value is right-aligned to the same column end, so
    header end positions are reliable field boundaries.
    """
    lines = content.splitlines()
    if not lines:
        raise InventoryFormatError("fixed-width inventory is empty")

    header_index = next((i for i, line in enumerate(lines) if "product-link" in line), None)
    if header_index is None:
        raise InventoryFormatError("text inventory is missing a product-link header")

    header = lines[header_index]
    columns = _column_boundaries(header)
    canonical_names = [canonical for _, _, canonical in columns]
    if "product_name" not in canonical_names:
        raise InventoryFormatError("text inventory is missing the product name column")

    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=canonical_names)
    writer.writeheader()

    for line in lines[header_index + 1 :]:
        if not line.strip():
            continue
        padded = line.ljust(columns[-1][1])
        record: dict[str, str] = {}
        start = 0
        for _, end, canonical in columns:
            value = padded[start:end].strip()
            record[canonical] = _clean_cell(value)
            start = end + 1
        if record.get("product_name"):
            writer.writerow(record)

    return parse_csv(
        content=csv_buffer.getvalue(),
        vendor=vendor,
        source_ref=source_ref,
    )


def _column_boundaries(header: str) -> list[tuple[int, int, str]]:
    located: list[tuple[int, int, str]] = []
    occupied: list[tuple[int, int]] = []

    # Match longer names first because product-link is a prefix of
    # product-link-href.
    for source_name in sorted(_SUPPORTED_HEADERS, key=len, reverse=True):
        match = re.search(rf"(?<![\w-]){re.escape(source_name)}(?![\w-])", header)
        if match is None:
            continue
        if any(match.start() < end and match.end() > start for start, end in occupied):
            continue
        occupied.append((match.start(), match.end()))
        located.append(
            (match.start(), match.end(), _SUPPORTED_HEADERS[source_name])
        )

    located.sort(key=lambda value: value[1])
    return located


def _clean_cell(value: str) -> str:
    if value.lower() in {"nan", "none", "null", "n/a"}:
        return ""
    # Some table exports escaped embedded newlines as the two characters "\\n".
    return re.sub(r"\s+", " ", value.replace("\\n", " ")).strip()
