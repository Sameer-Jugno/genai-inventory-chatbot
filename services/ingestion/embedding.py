"""Hugging Face embeddings client (BAAI/bge-large-en-v1.5 by default)."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from shared.providers.http_json import post_json
from shared.providers.secrets import require_secret
from shared.schema import EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "BAAI/bge-large-en-v1.5"
_HF_FEATURE_URL = (
    "https://router.huggingface.co/hf-inference/models/"
    "{model}/pipeline/feature-extraction"
)


class EmbeddingClient:
    def __init__(
        self,
        *,
        model_id: str | None = None,
        api_key: str | None = None,
        region: str | None = None,  # unused; kept for call-site compatibility
    ) -> None:
        del region
        self._model_id = (model_id or _DEFAULT_MODEL).strip()
        self._api_key = api_key or require_secret("HF_TOKEN")
        self._url = _HF_FEATURE_URL.format(model=self._model_id)

    def embed_text(self, text: str) -> list[float]:
        cleaned = (text or "").strip()
        if not cleaned:
            raise ValueError("embed_text requires non-empty text")

        payload = post_json(
            self._url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            body={"inputs": cleaned, "options": {"wait_for_model": True}},
            timeout_seconds=120,
        )
        vector = _as_embedding(payload)
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise RuntimeError(
                f"unexpected embedding payload from {self._model_id}: "
                f"len={len(vector)} expected={EMBEDDING_DIMENSIONS}"
            )
        return vector

    def embed_many(
        self,
        texts: list[str],
        *,
        max_workers: int = 4,
    ) -> list[list[float]]:
        """Embed catalog rows concurrently while preserving source order."""
        if not texts:
            return []
        workers = max(1, min(max_workers, len(texts)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(self.embed_text, texts))


def _as_embedding(payload: Any) -> list[float]:
    """Normalize HF feature-extraction shapes to a single float vector."""
    if isinstance(payload, list) and payload and isinstance(payload[0], (int, float)):
        return [float(x) for x in payload]

    if isinstance(payload, list) and payload and isinstance(payload[0], list):
        # Token-level matrix → mean pool.
        if payload and isinstance(payload[0][0], (int, float)):
            dims = len(payload[0])
            sums = [0.0] * dims
            for token in payload:
                for i, value in enumerate(token):
                    sums[i] += float(value)
            n = float(len(payload))
            return [value / n for value in sums]

    raise RuntimeError(f"unexpected HF embedding payload type={type(payload)}")
