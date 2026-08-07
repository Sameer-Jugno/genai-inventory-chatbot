"""Pure catalog view helpers shared by the agent (no AWS imports)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class SearchRequest:
    query: str
    category: str | None = None
    vendor: str | None = None
    color: str | None = None
    max_unit_price: float | None = None
    min_quantity: float | None = None
    size: int = 8


def format_hits_for_tool(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact, model-facing cards — omit embeddings and raw blobs."""
    cards: list[dict[str, Any]] = []
    for hit in hits:
        cards.append(
            {
                "item_id": hit.get("item_id"),
                "name": hit.get("name"),
                "vendor": display_vendor_name(
                    hit.get("vendor"),
                    product_url=hit.get("product_url"),
                ),
                "category": hit.get("category"),
                "subcategory": hit.get("subcategory"),
                "description": _trim(hit.get("description"), 280),
                "unit_price": hit.get("unit_price"),
                "currency": hit.get("currency") or "USD",
                "quantity": hit.get("quantity"),
                "dimensions_text": hit.get("dimensions_text"),
                "colors": hit.get("colors") or [],
                "tags": hit.get("tags") or [],
                "features": hit.get("features") or [],
                "product_url": hit.get("product_url"),
                "image_refs": hit.get("image_refs") or [],
                "source_item_id": hit.get("source_item_id"),
                "score": hit.get("score"),
            }
        )
    return cards


def display_vendor_name(vendor: object, *, product_url: object = None) -> str | None:
    """Turn storage slugs into user-facing names, using known source domains."""
    if isinstance(product_url, str) and product_url.strip():
        host = (urlparse(product_url).hostname or "").lower()
        if host == "acmebrooklyn.com" or host.endswith(".acmebrooklyn.com"):
            return "ACME Brooklyn"

    text = str(vendor or "").strip()
    if not text:
        return None
    if text.lower() == "demo-vendor":
        return "CandyWagon Demo Inventory"
    return text.replace("_", " ").replace("-", " ").title()


_MODEL_FACING_FIELDS = (
    "name",
    "vendor",
    "category",
    "subcategory",
    "description",
    "unit_price",
    "currency",
    "quantity",
    "dimensions_text",
    "colors",
    "tags",
)


def cards_for_model(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Facts the model needs to reason and cite; media and IDs stay in the UI."""
    trimmed: list[dict[str, Any]] = []
    for card in cards:
        kept = {
            field: card.get(field)
            for field in _MODEL_FACING_FIELDS
            if card.get(field) not in (None, [], ())
        }
        kept["has_photo"] = bool(card.get("image_urls") or card.get("image_refs"))
        trimmed.append(kept)
    return trimmed


def group_hits_by_vendor(hits: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for hit in hits:
        vendor = str(hit.get("vendor") or "unknown")
        grouped.setdefault(vendor, []).append(hit)
    return grouped


def estimate_budget(
    hits: list[dict[str, Any]],
    *,
    quantities: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Sum unit prices for hits that have prices. Does not invent missing prices."""
    quantities = quantities or {}
    priced = 0
    missing_price = 0
    total = 0.0
    currency = "USD"
    lines: list[dict[str, Any]] = []

    for hit in hits:
        item_id = str(hit.get("item_id") or "")
        price = hit.get("unit_price")
        qty = quantities.get(item_id, 1.0)
        if price is None:
            missing_price += 1
            continue
        priced += 1
        currency = str(hit.get("currency") or currency)
        line_total = float(price) * float(qty)
        total += line_total
        lines.append(
            {
                "item_id": item_id,
                "name": hit.get("name"),
                "unit_price": price,
                "quantity": qty,
                "line_total": line_total,
                "currency": currency,
            }
        )

    return {
        "currency": currency,
        "priced_item_count": priced,
        "missing_price_count": missing_price,
        "estimated_total": round(total, 2) if priced else None,
        "lines": lines,
        "note": (
            "Estimate uses indexed unit_price only; live quotes and fees are not included."
            if priced
            else "No priced items in this result set."
        ),
    }


def _trim(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
