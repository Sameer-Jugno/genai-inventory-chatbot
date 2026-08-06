"""Inventory catalog schema shared by ingestion and retrieval."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


SCHEMA_VERSION = 2
EMBEDDING_DIMENSIONS = 1024  # BAAI/bge-large-en-v1.5 (same width as Titan V2)


class SourceType(str, Enum):
    UPLOAD = "upload"
    SCRAPE = "scrape"


class TagSource(str, Enum):
    FILE = "file"
    LLM = "llm"
    DERIVED = "derived"
    MIXED = "mixed"


class Dimensions(BaseModel):
    """Normalized dimensions; numeric values use ``unit`` (normally inches)."""

    length: float | None = None
    width: float | None = None
    depth: float | None = None
    height: float | None = None
    diameter: float | None = None
    unit: str | None = None  # e.g. "in", "cm", "ft"


class InventoryItem(BaseModel):
    """One OpenSearch document = one inventory item (ADR-006)."""

    item_id: str = Field(..., description="Stable hash of vendor + best source identity")
    vendor: str
    source_type: SourceType
    source_ref: str = Field(..., description="s3://…/uploads/… or source URL")
    source_item_id: str | None = Field(
        default=None,
        description="Vendor SKU/catalog ID when supplied, e.g. CH869",
    )
    source_page: int | None = Field(
        default=None,
        ge=1,
        description="First source PDF page containing this item",
    )
    name: str = Field(..., min_length=1, description="Human-readable catalog item name")
    description: str
    category: str | None = Field(
        default=None,
        description="Normalized top-level inventory category",
    )
    subcategory: str | None = None
    product_url: str | None = None
    model_3d_url: str | None = Field(
        default=None,
        description="Optional vendor 3D-model URL/reference when supplied",
    )
    dimensions_text: str | None = Field(
        default=None,
        description="Human-readable dimensions string returned to the user",
    )
    dimensions: Dimensions | None = None
    quantity: float | None = None
    unit_price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, description="ISO 4217 code, usually USD")
    features: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    service_areas: list[str] = Field(
        default_factory=list,
        description="Vendor service areas only when explicitly supplied",
    )
    tags: list[str] = Field(default_factory=list)
    tag_source: TagSource = TagSource.FILE
    image_refs: list[str] = Field(
        default_factory=list,
        description="S3 object keys under images/ — never expired URLs",
    )
    ingested_at: int = Field(..., description="Unix epoch seconds")
    schema_version: int = SCHEMA_VERSION
    raw_excerpt: str | None = None

    def embedding_text(self) -> str:
        """Canonical semantic text embedded at ingest and mirrored at query time."""
        parts = [
            self.name,
            self.description,
            f"category: {self.category}" if self.category else "",
            f"subcategory: {self.subcategory}" if self.subcategory else "",
            f"dimensions: {self.dimensions_text}" if self.dimensions_text else "",
            f"features: {', '.join(self.features)}" if self.features else "",
            f"colors: {', '.join(self.colors)}" if self.colors else "",
            f"tags: {', '.join(self.tags)}" if self.tags else "",
        ]
        return " | ".join(part for part in parts if part)

    def to_opensearch_source(self, embedding: list[float]) -> dict[str, Any]:
        if len(embedding) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"embedding must have {EMBEDDING_DIMENSIONS} dims, got {len(embedding)}"
            )
        payload = self.model_dump(mode="json")
        # Store the exact semantic text to support hybrid BM25 + vector retrieval
        # and make embedding provenance inspectable.
        payload["search_text"] = self.embedding_text()
        payload["source_quality"] = self.source_quality()
        payload["embedding"] = embedding
        return payload

    def source_quality(self) -> int:
        """Score source completeness so weaker duplicate exports cannot win."""
        return (
            int(self.source_item_id is not None) * 20
            + int(self.description != self.name) * 10
            + int(self.category is not None) * 5
            + int(self.quantity is not None) * 5
            + int(self.unit_price is not None) * 5
            + int(self.dimensions_text is not None) * 5
            + int(self.product_url is not None) * 5
            + int(bool(self.image_refs)) * 5
            + min(len(self.features), 5)
            + min(len(self.colors), 5)
            + min(len(self.tags), 10)
        )
