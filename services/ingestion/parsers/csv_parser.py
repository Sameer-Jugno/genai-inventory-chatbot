"""CSV → InventoryItem rows (Module 2.3)."""

from __future__ import annotations

import csv
import io
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from services.ingestion.errors import InventoryFormatError
from services.ingestion.ids import stable_item_id
from services.ingestion.parsers.dimensions_parser import parse_dimensions
from shared.schema import (
    COLOR_TAGS,
    InventoryItem,
    SourceType,
    TagSource,
    derive_tags,
    infer_category,
    merge_tags,
)


@dataclass(frozen=True)
class EmbeddedImage:
    filename: str
    body: bytes
    content_type: str


@dataclass(frozen=True)
class CsvRow:
    """Parsed CSV row: catalog item plus optional remote image URL to fetch."""

    item: InventoryItem
    source_image_url: str | None = None
    embedded_images: tuple[EmbeddedImage, ...] = ()


def parse_csv(
    *,
    content: str,
    vendor: str,
    source_ref: str,
) -> list[CsvRow]:
    """
    Best-effort CSV parse.

    Expected flexible headers (case-insensitive), e.g.:
      description, dimensions, quantity, tags, image_url
    """
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise InventoryFormatError("CSV is empty or has no header row")

    field_map = {_norm(h): h for h in reader.fieldnames if h}
    name_header = _find_header(
        field_map,
        "name",
        "product_name",
        "product_link",
        "item",
        "title",
        "description",
        "desc",
    )
    if name_header is None:
        raise InventoryFormatError(
            "CSV needs a name/description column; "
            f"received headers: {', '.join(field_map)}"
        )
    rows: list[CsvRow] = []

    for idx, row in enumerate(reader):
        name_raw = _get(
            row,
            field_map,
            "name",
            "product_name",
            "product_link",
            "item",
            "title",
            "description",
            "desc",
        )
        if not name_raw:
            continue
        source_item_id, name = _split_source_item_id(name_raw)
        explicit_source_item_id = _get(
            row,
            field_map,
            "source_item_id",
            "inventory_id",
            "sku",
            "product_id",
        )
        source_item_id = explicit_source_item_id or source_item_id
        source_page_raw = _get(row, field_map, "source_page", "page")
        description = _get(row, field_map, "description", "product_description", "desc")
        description = description or name

        dimensions_text = _get(
            row,
            field_map,
            "dimensions",
            "product_dimensions",
            "dimension",
            "size",
        )
        quantity_raw = _get(
            row,
            field_map,
            "quantity",
            "product_quantity",
            "qty",
            "count",
            "available_quantity",
        )
        price_raw = _get(
            row,
            field_map,
            "unit_price",
            "product_price",
            "price",
            "rental_price",
        )
        tags_raw = _get(row, field_map, "tags", "tag", "categories")
        category = _get(row, field_map, "category", "product_category")
        subcategory = _get(row, field_map, "subcategory", "sub_category")
        features_raw = _get(
            row,
            field_map,
            "features",
            "feature",
            "environment",
            "contexts",
        )
        colors_raw = _get(row, field_map, "colors", "colour", "color")
        product_url = _get(
            row,
            field_map,
            "product_url",
            "product_link_href",
            "url",
            "link",
        )
        model_3d_url = _get(
            row,
            field_map,
            "model_3d_url",
            "3d_link",
            "3d_url",
            "model_url",
        )
        image_url = _get(
            row,
            field_map,
            "image_url",
            "product_image_url",
            "image",
            "img",
        )

        file_tags = _split_values(tags_raw)
        features = _split_values(features_raw)
        derived = derive_tags(
            name,
            description,
            category,
            subcategory,
            tags_raw,
            colors_raw,
            *features,
        )
        colors = [
            tag
            for tag in derive_tags(name, description, tags_raw, colors_raw)
            if tag in COLOR_TAGS
        ]
        normalized_category = _normalized_optional(category) or infer_category(
            name,
            description,
        )
        tags, tag_source_str = merge_tags(
            file_tags=file_tags,
            llm_tags=[],
            derived_tags=derived,
        )

        item_id = stable_item_id(
            vendor,
            source_ref,
            idx,
            name,
            source_item_id=source_item_id,
            product_url=_optional_http_url(product_url),
        )
        item = InventoryItem(
            item_id=item_id,
            vendor=vendor,
            source_type=SourceType.UPLOAD,
            source_ref=source_ref,
            source_item_id=source_item_id,
            source_page=_to_int(source_page_raw),
            name=name,
            description=description.strip(),
            category=normalized_category,
            subcategory=_normalized_optional(subcategory),
            product_url=_optional_http_url(product_url),
            model_3d_url=_optional_reference(model_3d_url),
            dimensions_text=dimensions_text.strip() if dimensions_text else None,
            dimensions=parse_dimensions(dimensions_text),
            quantity=_to_float(quantity_raw),
            unit_price=_to_float(price_raw),
            currency="USD" if price_raw else None,
            features=features,
            colors=colors,
            tags=tags,
            tag_source=TagSource(tag_source_str),
            image_refs=[],
            ingested_at=int(time.time()),
        )
        rows.append(CsvRow(item=item, source_image_url=image_url))
    return rows


def _norm(header: str) -> str:
    return (
        header.strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
        .replace("*", "")
    )


def _find_header(field_map: dict[str, str], *candidates: str) -> str | None:
    for candidate in candidates:
        if candidate in field_map:
            return field_map[candidate]
    return None


def _get(row: dict, field_map: dict[str, str], *candidates: str) -> str | None:
    for c in candidates:
        original = field_map.get(c)
        if original is None:
            continue
        value = row.get(original)
        text = _optional(str(value)) if value is not None else None
        if text:
            return text
    return None


def _to_float(value: str | None) -> float | None:
    if _optional(value) is None:
        return None
    match = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?", str(value))
    if match is None:
        return None
    return float(match.group(0).replace(",", ""))


def _to_int(value: str | None) -> int | None:
    parsed = _to_float(value)
    return int(parsed) if parsed is not None and parsed >= 1 else None


def _split_source_item_id(value: str) -> tuple[str | None, str]:
    value = value.strip()
    parts = value.split(maxsplit=1)
    if len(parts) == 2 and _looks_like_sku(parts[0]):
        return parts[0], parts[1]
    return None, value


def _looks_like_sku(value: str) -> bool:
    compact = value.replace("-", "")
    return (
        3 <= len(compact) <= 20
        and compact.isalnum()
        and any(char.isalpha() for char in compact)
        and any(char.isdigit() for char in compact)
    )


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "n/a", "none", "null"}:
        return None
    return text


def _normalized_optional(value: str | None) -> str | None:
    text = _optional(value)
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") if text else None


def _split_values(value: str | None) -> list[str]:
    text = _optional(value)
    if not text:
        return []
    return [
        part.strip()
        for part in re.split(r"[,;/|\n]+", text)
        if part.strip()
    ]


def _optional_http_url(value: str | None) -> str | None:
    text = _optional(value)
    if not text or not text.lower().startswith(("http://", "https://")):
        return None
    parts = urlsplit(text)
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"gclid", "fbclid"}
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _optional_reference(value: str | None) -> str | None:
    text = _optional(value)
    if not text or text.lower() in {"is", "link"}:
        return None
    return text
