"""OpenSearch Serverless client with SigV4 signing."""

from __future__ import annotations

import logging
from typing import Any

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection, helpers
from requests_aws4auth import AWS4Auth

from shared.schema import InventoryItem

logger = logging.getLogger(__name__)


class OpenSearchInventoryClient:
    def __init__(self, *, endpoint: str, index: str, region: str) -> None:
        host = endpoint.replace("https://", "").replace("http://", "").rstrip("/")
        credentials = boto3.Session().get_credentials()
        if credentials is None:
            raise RuntimeError("No AWS credentials available for OpenSearch SigV4")

        frozen = credentials.get_frozen_credentials()
        auth = AWS4Auth(
            frozen.access_key,
            frozen.secret_key,
            region,
            "aoss",
            session_token=frozen.token,
        )
        self._index = index
        self._client = OpenSearch(
            hosts=[{"host": host, "port": 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=60,
        )

    def upsert_items(self, items: list[InventoryItem], embeddings: list[list[float]]) -> int:
        """
        Idempotent write for OpenSearch Serverless VECTORSEARCH collections.

        AOSS vector collections reject externally supplied document IDs and do
        not implement _delete_by_query, so ``item_id`` cannot be the ``_id``.
        Identity is resolved by searching ``item_id`` and reusing the
        AOSS-generated ``_id``, which update/delete do accept.
        """
        if len(items) != len(embeddings):
            raise ValueError("items and embeddings length mismatch")

        documents: dict[str, dict[str, Any]] = {}
        for item, embedding in zip(items, embeddings, strict=True):
            document = item.to_opensearch_source(embedding)
            existing = documents.get(item.item_id)
            # Collapse duplicates inside one upload before touching the index.
            if existing is None or document["source_quality"] >= existing["source_quality"]:
                documents[item.item_id] = document

        indexed = self._lookup_existing(list(documents))

        actions: list[dict[str, Any]] = []
        for item_id, document in documents.items():
            matches = indexed.get(item_id, [])
            if not matches:
                actions.append({"_op_type": "index", "_index": self._index, "_source": document})
                continue

            winner_doc_id, winner_quality = matches[0]
            # Stale copies of the same item_id (older schema or partial writes).
            for extra_doc_id, _ in matches[1:]:
                actions.append(
                    {"_op_type": "delete", "_index": self._index, "_id": extra_doc_id}
                )

            if document["source_quality"] >= winner_quality:
                actions.append(
                    {"_op_type": "delete", "_index": self._index, "_id": winner_doc_id}
                )
                actions.append({"_op_type": "index", "_index": self._index, "_source": document})
            else:
                # Weaker export: refresh only volatile commercial fields.
                partial = {"ingested_at": document["ingested_at"]}
                if document.get("quantity") is not None:
                    partial["quantity"] = document["quantity"]
                if document.get("unit_price") is not None:
                    partial["unit_price"] = document["unit_price"]
                    partial["currency"] = document.get("currency")
                actions.append(
                    {
                        "_op_type": "update",
                        "_index": self._index,
                        "_id": winner_doc_id,
                        "doc": partial,
                    }
                )

        success, errors = helpers.bulk(self._client, actions, raise_on_error=False)
        if errors:
            logger.error("opensearch_bulk_errors count=%s sample=%s", len(errors), errors[:3])
            raise RuntimeError(f"OpenSearch bulk indexing failed for {len(errors)} docs")
        return len(documents)

    def _lookup_existing(
        self,
        item_ids: list[str],
        *,
        batch_size: int = 200,
    ) -> dict[str, list[tuple[str, int]]]:
        """Map item_id → [(document _id, source_quality)], richest first."""
        found: dict[str, list[tuple[str, int]]] = {}
        for start in range(0, len(item_ids), batch_size):
            batch = item_ids[start : start + batch_size]
            response = self._client.search(
                index=self._index,
                body={
                    "size": len(batch) * 2,
                    "_source": ["item_id", "source_quality"],
                    "query": {"terms": {"item_id": batch}},
                },
            )
            for hit in response.get("hits", {}).get("hits", []):
                source = hit.get("_source", {})
                item_id = source.get("item_id")
                if not item_id:
                    continue
                quality = int(source.get("source_quality") or 0)
                found.setdefault(item_id, []).append((hit["_id"], quality))

        for matches in found.values():
            matches.sort(key=lambda pair: pair[1], reverse=True)
        return found

    def vector_search(
        self,
        embedding: list[float],
        *,
        size: int = 10,
        category: str | None = None,
        max_unit_price: float | None = None,
        min_quantity: float | None = None,
        vendor: str | None = None,
        color: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve semantically similar items with optional exact/range filters."""
        filters: list[dict[str, Any]] = []
        if category:
            filters.append({"term": {"category": category}})
        if max_unit_price is not None:
            filters.append({"range": {"unit_price": {"lte": max_unit_price}}})
        if min_quantity is not None:
            filters.append({"range": {"quantity": {"gte": min_quantity}}})
        if vendor:
            filters.append({"term": {"vendor": vendor}})
        if color:
            filters.append({"term": {"colors": color}})

        query: dict[str, Any] = {
            "knn": {
                "embedding": {
                    "vector": embedding,
                    "k": size,
                }
            }
        }
        if filters:
            query = {"bool": {"must": [query], "filter": filters}}

        response = self._client.search(
            index=self._index,
            body={
                "size": size,
                "_source": {"excludes": ["embedding"]},
                "query": query,
            },
        )
        return [
            {
                "score": hit.get("_score"),
                **hit.get("_source", {}),
            }
            for hit in response.get("hits", {}).get("hits", [])
        ]
