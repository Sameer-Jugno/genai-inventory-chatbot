"""Deterministic inventory item identifiers."""

from __future__ import annotations

import hashlib
import re


def stable_item_id(
    vendor: str,
    source_ref: str,
    idx: int,
    name: str,
    *,
    source_item_id: str | None = None,
    product_url: str | None = None,
) -> str:
    """
    Build an idempotent item ID using the strongest identity in the source.

    Vendor SKU and canonical product URL survive row reordering and description
    edits. Row position is only a fallback for sources with no natural key.
    """
    if source_item_id:
        identity = f"sku:{_normalize(source_item_id)}"
    elif product_url:
        identity = f"url:{product_url.strip().rstrip('/').lower()}"
    else:
        # Name is more stable than source filename or row/page order and also
        # deduplicates duplicate exports. Distinct variants should supply a SKU
        # or product URL; otherwise treating them as one item is safest.
        identity = f"name:{_normalize(name)}"
    raw = f"{_normalize(vendor)}|{identity}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())
