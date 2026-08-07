"""Inventory retrieval for chat — real Titan + OpenSearch path (ADR-010)."""

from __future__ import annotations

from typing import Any

from services.chat.catalog_view import SearchRequest
from services.ingestion.embedding import EmbeddingClient
from services.ingestion.opensearch_client import OpenSearchInventoryClient


class InventoryRetriever:
    """Embeds the query and runs filtered kNN search against the inventory index."""

    def __init__(
        self,
        *,
        embedder: EmbeddingClient,
        search: OpenSearchInventoryClient,
        default_size: int = 8,
        max_size: int = 20,
    ) -> None:
        self._embedder = embedder
        self._search = search
        self._default_size = default_size
        self._max_size = max_size

    def search(self, request: SearchRequest) -> list[dict[str, Any]]:
        query = (request.query or "").strip()
        if not query:
            raise ValueError("search query must be non-empty")

        size = request.size if request.size > 0 else self._default_size
        size = min(size, self._max_size)

        embedding = self._embedder.embed_text(query)
        return self._search.vector_search(
            embedding,
            size=size,
            category=request.category,
            max_unit_price=request.max_unit_price,
            min_quantity=request.min_quantity,
            vendor=request.vendor,
            color=request.color,
        )
