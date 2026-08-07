"""Presigned URLs for processed catalog images under images/."""

from __future__ import annotations

import logging

import boto3

logger = logging.getLogger(__name__)


class ImageUrlService:
    def __init__(
        self,
        *,
        bucket_name: str,
        images_prefix: str,
        region: str,
        ttl_seconds: int = 3600,
    ) -> None:
        self._bucket = bucket_name
        self._prefix = images_prefix if images_prefix.endswith("/") else f"{images_prefix}/"
        self._ttl = ttl_seconds
        self._s3 = boto3.client("s3", region_name=region)

    def presign(self, image_ref: str) -> str:
        key = self._normalize_key(image_ref)
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=self._ttl,
        )

    def presign_many(self, image_refs: list[str], *, limit: int = 5) -> list[str]:
        urls: list[str] = []
        for ref in image_refs[:limit]:
            try:
                urls.append(self.presign(ref))
            except Exception:
                logger.exception("presign_failed ref=%s", ref)
        return urls

    def _normalize_key(self, image_ref: str) -> str:
        ref = (image_ref or "").strip().lstrip("/")
        if not ref:
            raise ValueError("image_ref must be non-empty")
        if ref.startswith("s3://"):
            # s3://bucket/key → key
            without = ref[5:]
            _, _, key = without.partition("/")
            if not key:
                raise ValueError(f"invalid s3 uri: {image_ref}")
            return key
        if ref.startswith(self._prefix):
            return ref
        return f"{self._prefix}{ref}"
