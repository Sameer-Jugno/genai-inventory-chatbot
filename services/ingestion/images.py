"""Store inventory images under the images/ prefix."""

from __future__ import annotations

import logging
import mimetypes
import ipaddress
import socket
from urllib.parse import urlparse

import boto3
import urllib.request

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


class ImageStore:
    def __init__(self, *, bucket: str, images_prefix: str) -> None:
        self._bucket = bucket
        self._prefix = images_prefix if images_prefix.endswith("/") else f"{images_prefix}/"
        self._s3 = boto3.client("s3")

    def put_bytes(
        self,
        *,
        vendor: str,
        item_id: str,
        filename: str,
        body: bytes,
        content_type: str,
    ) -> str:
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ValueError(f"unsupported image content type: {content_type}")
        if len(body) > MAX_IMAGE_BYTES:
            raise ValueError(f"image exceeds {MAX_IMAGE_BYTES} bytes")

        key = f"{self._prefix}{vendor}/{item_id}/{filename}"
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
        logger.info("image_stored key=%s bytes=%s", key, len(body))
        return key

    def fetch_url_and_store(
        self,
        *,
        vendor: str,
        item_id: str,
        url: str,
    ) -> str | None:
        """Best-effort download of a remote image into the images/ prefix."""
        parsed = urlparse(url)
        if not _is_public_http_url(url):
            logger.warning("skip_unsafe_image_url url=%s", url)
            return None

        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "inventory-planner-ingestion/1.0"},
            )
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
                if not _is_public_http_url(response.geturl()):
                    logger.warning("skip_unsafe_image_redirect url=%s", response.geturl())
                    return None
                body = response.read(MAX_IMAGE_BYTES + 1)
                content_type = response.headers.get_content_type()
        except Exception:
            logger.exception("image_download_failed url=%s", url)
            return None

        if len(body) > MAX_IMAGE_BYTES:
            logger.warning("image_too_large url=%s", url)
            return None

        filename = parsed.path.rsplit("/", 1)[-1] or "image.bin"
        if "." not in filename:
            ext = mimetypes.guess_extension(content_type or "") or ".bin"
            filename = f"image{ext}"

        try:
            return self.put_bytes(
                vendor=vendor,
                item_id=item_id,
                filename=filename,
                body=body,
                content_type=content_type or "application/octet-stream",
            )
        except ValueError as exc:
            logger.warning("image_store_rejected url=%s reason=%s", url, exc)
            return None


def _is_public_http_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(parsed.hostname, parsed.port or 443)
        }
    except socket.gaierror:
        return False
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            return False
    return bool(addresses)
