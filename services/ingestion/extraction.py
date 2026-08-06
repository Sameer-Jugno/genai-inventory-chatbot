"""LLM-assisted extraction for messy PDF/HTML into inventory items (Groq)."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from services.ingestion.errors import InventoryFormatError
from services.ingestion.ids import stable_item_id
from services.ingestion.parsers.dimensions_parser import parse_dimensions
from shared.providers.groq import GroqKeyPool
from shared.schema import (
    COLOR_TAGS,
    InventoryItem,
    SourceType,
    TagSource,
    derive_tags,
    infer_category,
    merge_tags,
)
from shared.schema.tag_taxonomy import STARTER_TAGS

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "llama-3.3-70b-versatile"


class ExtractionClient:
    def __init__(
        self,
        *,
        model_id: str | None = None,
        api_key: str | None = None,
        region: str | None = None,  # unused; kept for call-site compatibility
    ) -> None:
        del region
        self._model_id = (model_id or _DEFAULT_MODEL).strip()
        self._groq = GroqKeyPool.from_env(explicit=api_key)

    def extract_items_from_text(
        self,
        *,
        text: str,
        vendor: str,
        source_ref: str,
        source_type: SourceType,
        default_source_page: int | None = None,
    ) -> list[InventoryItem]:
        prompt = self._build_prompt(text)
        raw = self._invoke_llm(prompt)
        records = self._parse_json_array(raw)
        return self._records_to_items(
            records=records,
            vendor=vendor,
            source_ref=source_ref,
            source_type=source_type,
            default_source_page=default_source_page,
        )

    def _records_to_items(
        self,
        *,
        records: list[dict[str, Any]],
        vendor: str,
        source_ref: str,
        source_type: SourceType,
        default_source_page: int | None,
    ) -> list[InventoryItem]:
        items: list[InventoryItem] = []
        for idx, record in enumerate(records):
            name = _optional_str(record.get("name"))
            if not name:
                continue
            description = _optional_str(record.get("description")) or name
            source_item_id = _optional_str(record.get("source_item_id"))
            product_url = _optional_str(record.get("product_url"))
            category = _optional_str(record.get("category"))
            subcategory = _optional_str(record.get("subcategory"))
            features = _string_list(record.get("features"))
            llm_tags = [str(t) for t in record.get("tags", []) if t]
            derived = derive_tags(name, description, category, subcategory, *features)
            colors = [tag for tag in derived if tag in COLOR_TAGS]
            normalized_category = _normalize_category(category) or infer_category(
                name,
                description,
                *features,
            )
            tags, tag_source = merge_tags(
                file_tags=[],
                llm_tags=llm_tags,
                derived_tags=derived,
            )
            source_page = _optional_int(record.get("source_page")) or default_source_page
            dimensions_text = _optional_str(record.get("dimensions"))

            items.append(
                InventoryItem(
                    item_id=stable_item_id(
                        vendor,
                        source_ref,
                        idx,
                        name,
                        source_item_id=source_item_id,
                        product_url=product_url,
                    ),
                    vendor=vendor,
                    source_type=source_type,
                    source_ref=source_ref,
                    source_item_id=source_item_id,
                    source_page=source_page,
                    name=name,
                    description=description,
                    category=normalized_category,
                    subcategory=_normalize_category(subcategory),
                    product_url=product_url,
                    dimensions_text=dimensions_text,
                    dimensions=parse_dimensions(dimensions_text),
                    quantity=_optional_float(record.get("quantity")),
                    unit_price=_optional_float(record.get("unit_price")),
                    currency=_optional_str(record.get("currency")),
                    features=features,
                    colors=colors,
                    tags=tags,
                    tag_source=TagSource(tag_source),
                    image_refs=[],
                    ingested_at=int(time.time()),
                    raw_excerpt=_optional_str(record.get("raw_excerpt")),
                )
            )
        return items

    def _instruction(self) -> str:
        allowed = ", ".join(STARTER_TAGS)
        return (
            "Extract actual rentable inventory items from the supplied catalog. "
            "Ignore tables of contents, headings with no item, marketing prose, and "
            "category-only pages. Never invent price, quantity, availability, location, "
            "SKU, URL, or dimensions. Return ONLY a JSON array. Each object must use: "
            "name (string), source_item_id (string|null), source_page (integer|null), "
            "category (string|null), subcategory (string|null), description (string), "
            "dimensions (string|null), quantity (number|null), unit_price (number|null), "
            "currency (string|null), product_url (string|null), features (array of short "
            f"strings), tags (array using only: {allowed}), raw_excerpt (string|null). "
            "Use USD only when the source clearly presents dollar pricing."
        )

    def _build_prompt(self, text: str) -> str:
        if len(text) > 12_000:
            raise ValueError("extraction text exceeds 12,000 characters; chunk it first")
        return (
            self._instruction()
            + "\nPreserve category context across item pages. The [PAGE N] markers "
            "provide source_page values.\n\n"
            f"TEXT:\n{text}"
        )

    def _invoke_llm(self, prompt: str) -> str:
        payload = self._groq.post_chat(
            body={
                "model": self._model_id,
                "temperature": 0,
                "max_tokens": 4096,
                "messages": [
                    {
                        "role": "system",
                        "content": "You extract rental inventory as JSON arrays only.",
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout_seconds=180,
        )
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("Groq extraction response missing choices")
        message = choices[0].get("message") or {}
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Groq extraction response missing text content")
        return text

    def _parse_json_array(self, raw: str) -> list[dict[str, Any]]:
        raw = raw.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\[[\s\S]*\]", raw)
            if not match:
                logger.error("extraction_json_parse_failed raw_prefix=%s", raw[:200])
                raise InventoryFormatError("LLM extraction response was not a JSON array")
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise InventoryFormatError(
                    "LLM extraction response contained invalid JSON"
                ) from exc
        if not isinstance(data, list):
            raise InventoryFormatError("LLM extraction response must be a JSON array")
        return [row for row in data if isinstance(row, dict)]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    parsed = _optional_float(value)
    return int(parsed) if parsed is not None and parsed >= 1 else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _optional_str(item))]


def _normalize_category(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or None
