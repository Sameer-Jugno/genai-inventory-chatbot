"""Generic XLSX inventory parser for scraper exports and asset workbooks."""

from __future__ import annotations

import csv
import io
import logging
import re
from collections import defaultdict
from dataclasses import replace
from io import BytesIO
from typing import Any

import openpyxl

from services.ingestion.errors import InventoryFormatError
from services.ingestion.parsers.csv_parser import CsvRow, EmbeddedImage, parse_csv
from shared.schema import infer_category

logger = logging.getLogger(__name__)

_NAME_HEADERS = ("product_title", "product_link", "name", "item_name", "title")
_CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}
_CANONICAL_FIELDS = (
    "product_name",
    "source_item_id",
    "description",
    "quantity",
    "unit_price",
    "dimensions",
    "tags",
    "category",
    "subcategory",
    "features",
    "colors",
    "product_url",
    "image_url",
    "model_3d_url",
)


def parse_xlsx_inventory(
    *,
    data: bytes,
    vendor: str,
    source_ref: str,
) -> list[CsvRow]:
    workbook = openpyxl.load_workbook(
        BytesIO(data),
        read_only=False,
        data_only=True,
    )
    parsed_rows: list[CsvRow] = []
    try:
        for sheet in workbook.worksheets:
            parsed_rows.extend(
                _parse_sheet(
                    sheet=sheet,
                    vendor=vendor,
                    source_ref=source_ref,
                )
            )
    finally:
        workbook.close()

    if not parsed_rows:
        raise InventoryFormatError("XLSX contains no recognizable inventory rows")
    return parsed_rows


def _parse_sheet(*, sheet: Any, vendor: str, source_ref: str) -> list[CsvRow]:
    values = list(sheet.iter_rows(values_only=True))
    header_index = _find_header_row(values)
    if header_index is None:
        logger.info("xlsx_skip_sheet_without_inventory_headers sheet=%s", sheet.title)
        return []

    headers = [_normalize_header(value) for value in values[header_index]]
    images_by_row = _extract_embedded_images(sheet)
    records: list[dict[str, str]] = []
    source_rows: list[int] = []

    for excel_row, values_row in enumerate(
        values[header_index + 1 :],
        start=header_index + 2,
    ):
        source = {
            header: value
            for header, value in zip(headers, values_row, strict=False)
            if header
        }
        name = _first(source, *_NAME_HEADERS)
        if not name:
            continue

        category_text = _first(source, "product_categories", "category")
        item_text = _first(source, "item", "subcategory", "sub_category")
        environment = _first(source, "environment", "contexts")
        collection_url = _first(source, "web_scraper_start_url")
        canonical_category = infer_category(
            category_text,
            item_text,
            name,
            environment,
            collection_url,
        ) or _normalize_value(category_text)
        subcategory = _hierarchy_leaf(category_text) or _normalize_value(item_text)

        tags = _join(
            _first(source, "product_tags"),
            _first(source, "tags"),
            category_text,
            item_text,
            environment,
            _first(source, "colors", "color", "colour"),
        )
        record = {
            "product_name": name,
            "source_item_id": _first(
                source,
                "inventory_id",
                "source_item_id",
                "sku",
                "product_id",
            ),
            "description": _first(source, "product_description", "description"),
            "quantity": _first(
                source,
                "product_quantity",
                "quantity",
                "available_quantity",
            ),
            "unit_price": _first(source, "product_price", "unit_price", "price"),
            "dimensions": _first(
                source,
                "product_dimensions",
                "dimensions",
                "size",
            ),
            "tags": tags,
            "category": canonical_category,
            "subcategory": subcategory,
            "features": _join(environment, _first(source, "features")),
            "colors": _first(source, "colors", "color", "colour"),
            "product_url": _first(
                source,
                "product_link_href",
                "product_url",
                "weblink_reference",
                "url",
            ),
            "image_url": _first(
                source,
                "product_image_formatted",
                "image",
                "product_image",
                "product_image_src_src",
                "image_url",
            ),
            "model_3d_url": _first(source, "3d_link", "model_3d_url", "3d_url"),
        }
        records.append({key: _string(value) for key, value in record.items()})
        source_rows.append(excel_row)

    if not records:
        return []

    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=_CANONICAL_FIELDS)
    writer.writeheader()
    writer.writerows(records)
    rows = parse_csv(
        content=csv_buffer.getvalue(),
        vendor=vendor,
        source_ref=source_ref,
    )
    if len(rows) != len(source_rows):
        raise InventoryFormatError(
            f"XLSX parser lost rows in sheet {sheet.title}: "
            f"{len(source_rows)} source vs {len(rows)} parsed"
        )

    parsed_source_rows = set(source_rows)
    unassociated_images = sum(
        len(images)
        for source_row, images in images_by_row.items()
        if source_row not in parsed_source_rows
    )
    if unassociated_images:
        logger.warning(
            "xlsx_unassociated_images sheet=%s count=%s",
            sheet.title,
            unassociated_images,
        )

    return [
        replace(row, embedded_images=tuple(images_by_row.get(source_row, [])))
        for row, source_row in zip(rows, source_rows, strict=True)
    ]


def _find_header_row(rows: list[tuple[Any, ...]]) -> int | None:
    for index, row in enumerate(rows[:25]):
        headers = {_normalize_header(value) for value in row if value is not None}
        if headers.intersection(_NAME_HEADERS):
            return index
    return None


def _extract_embedded_images(sheet: Any) -> dict[int, list[EmbeddedImage]]:
    result: dict[int, list[EmbeddedImage]] = defaultdict(list)
    for index, image in enumerate(getattr(sheet, "_images", []), start=1):
        anchor = getattr(image, "anchor", None)
        marker = getattr(anchor, "_from", None)
        if marker is None:
            continue
        extension = str(getattr(image, "format", "png") or "png").lower()
        content_type = _CONTENT_TYPES.get(extension)
        if content_type is None:
            logger.warning("xlsx_skip_embedded_image_type type=%s", extension)
            continue
        try:
            body = image._data()  # openpyxl exposes embedded binary data here.
        except Exception:
            logger.exception("xlsx_embedded_image_read_failed index=%s", index)
            continue
        excel_row = int(marker.row) + 1
        result[excel_row].append(
            EmbeddedImage(
                filename=f"workbook-{excel_row}-{index}.{extension}",
                body=body,
                content_type=content_type,
            )
        )
    return result


def _normalize_header(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _first(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None and str(value).strip():
            return value
    return None


def _join(*values: Any) -> str | None:
    parts = [str(value).strip() for value in values if value is not None and str(value).strip()]
    return "\n".join(parts) if parts else None


def _hierarchy_leaf(value: Any) -> str | None:
    if value is None:
        return None
    parts = [
        re.sub(r"\s+", " ", part).strip(" »-")
        for part in str(value).splitlines()
        if re.sub(r"\s+", " ", part).strip(" »-")
    ]
    return _normalize_value(parts[-1]) if len(parts) > 1 else None


def _normalize_value(value: Any) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")
    return normalized or None


def _string(value: Any) -> str:
    return "" if value is None else str(value)
