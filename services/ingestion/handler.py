"""S3-triggered inventory ingestion Lambda (Module 2.3)."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import unquote_plus

import boto3

from services.ingestion.embedding import EmbeddingClient
from services.ingestion.errors import InventoryFormatError
from services.ingestion.extraction import ExtractionClient
from services.ingestion.images import ImageStore
from services.ingestion.opensearch_client import OpenSearchInventoryClient
from services.ingestion.parsers.csv_parser import CsvRow, parse_csv
from services.ingestion.parsers.fixed_width_parser import parse_fixed_width_inventory
from services.ingestion.parsers.html_parser import chunk_text, html_to_text
from services.ingestion.parsers.pdf_catalog_parser import parse_product_page_pdf
from services.ingestion.parsers.pdf_parser import (
    chunk_pdf_pages,
    extract_pdf_pages,
    is_visual_catalog,
)
from services.ingestion.parsers.xlsx_parser import parse_xlsx_inventory
from shared.providers.secrets import load_local_dotenv
from shared.schema import InventoryItem, SourceType

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

UPLOADS_PREFIX = os.environ.get("UPLOADS_PREFIX", "uploads/")
IMAGES_PREFIX = os.environ.get("IMAGES_PREFIX", "images/")
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(128 * 1024 * 1024)))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Entry point for S3 ObjectCreated events.

    Flow:
      1. Resolve bucket/key from the event
      2. Skip anything not under uploads/
      3. Parse CSV / XLSX / fixed-width text / PDF / HTML → InventoryItem list
      4. Fetch optional CSV image URLs into images/
      5. Embed with HF bge-large, upsert into OpenSearch
    """
    load_local_dotenv()
    bucket_name = os.environ["DATA_BUCKET_NAME"]
    region = os.environ.get("AWS_REGION_NAME") or os.environ.get("AWS_REGION", "us-east-1")

    embedder = EmbeddingClient(
        model_id=os.environ.get("HF_EMBED_MODEL_ID", "BAAI/bge-large-en-v1.5"),
        region=region,
    )
    extractor = ExtractionClient(
        model_id=os.environ.get("GROQ_MODEL_ID", "llama-3.3-70b-versatile"),
        region=region,
    )
    search = OpenSearchInventoryClient(
        endpoint=os.environ["OPENSEARCH_ENDPOINT"],
        index=os.environ.get("OPENSEARCH_INDEX", "inventory-items"),
        region=region,
    )
    images = ImageStore(bucket=bucket_name, images_prefix=IMAGES_PREFIX)
    s3 = boto3.client("s3")

    processed = 0
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        logger.info("ingest_start bucket=%s key=%s", bucket, key)

        if not key.startswith(UPLOADS_PREFIX):
            logger.warning("skip_non_uploads_key key=%s", key)
            continue

        # S3 "folders" are zero-byte keys ending in "/"; creating them in the
        # console also fires ObjectCreated and must not be treated as catalogs.
        if key.endswith("/"):
            logger.info("skip_prefix_marker key=%s", key)
            continue

        processed += _ingest_object(
            s3=s3,
            embedder=embedder,
            extractor=extractor,
            search=search,
            images=images,
            bucket=bucket,
            key=key,
        )

    return {"ok": True, "processed_items": processed}


def _ingest_object(
    *,
    s3: Any,
    embedder: EmbeddingClient,
    extractor: ExtractionClient,
    search: OpenSearchInventoryClient,
    images: ImageStore,
    bucket: str,
    key: str,
) -> int:
    obj = s3.get_object(Bucket=bucket, Key=key)
    content_length = int(obj.get("ContentLength", 0))
    if content_length > MAX_UPLOAD_BYTES:
        raise InventoryFormatError(
            f"{key} is {content_length} bytes; maximum is {MAX_UPLOAD_BYTES}"
        )
    body: bytes = obj["Body"].read()
    source_ref = f"s3://{bucket}/{key}"
    vendor = _vendor_from_key(key)
    lower_key = key.lower()

    if lower_key.endswith(".csv"):
        items = _items_from_csv(
            content=body.decode("utf-8", errors="replace"),
            vendor=vendor,
            source_ref=source_ref,
            images=images,
        )
    elif lower_key.endswith(".xlsx"):
        items = _attach_images(
            parse_xlsx_inventory(
                data=body,
                vendor=vendor,
                source_ref=source_ref,
            ),
            images,
        )
    elif lower_key.endswith(".pdf"):
        pages = extract_pdf_pages(body)
        structured_rows = parse_product_page_pdf(
            pages=pages,
            vendor=vendor,
            source_ref=source_ref,
        )
        if structured_rows:
            items = [row.item for row in structured_rows]
        elif is_visual_catalog(pages):
            # Groq has no Bedrock-style PDF document vision. Use extractable
            # page text when present; otherwise ask for a structured upload.
            items = []
            for page_number, page_text in pages:
                text = (page_text or "").strip()
                if not text:
                    continue
                items.extend(
                    extractor.extract_items_from_text(
                        text=f"[PAGE {page_number}]\n{text}",
                        vendor=vendor,
                        source_ref=source_ref,
                        source_type=SourceType.UPLOAD,
                        default_source_page=page_number,
                    )
                )
            items = _deduplicate_items(items)
            if not items:
                raise InventoryFormatError(
                    f"{key} looks like a visual PDF catalog with no extractable "
                    "text; upload CSV/XLSX or a text-based PDF"
                )
        else:
            items = []
            for chunk in chunk_pdf_pages(pages):
                items.extend(
                    extractor.extract_items_from_text(
                        text=chunk.text,
                        vendor=vendor,
                        source_ref=source_ref,
                        source_type=SourceType.UPLOAD,
                        default_source_page=(
                            chunk.first_page
                            if chunk.first_page == chunk.last_page
                            else None
                        ),
                    )
                )
            items = _deduplicate_items(items)
    elif lower_key.endswith(".txt"):
        items = _items_from_fixed_width(
            content=body.decode("utf-8", errors="replace"),
            vendor=vendor,
            source_ref=source_ref,
            images=images,
        )
    elif lower_key.endswith(".html") or lower_key.endswith(".htm"):
        text = html_to_text(body.decode("utf-8", errors="replace"))
        items = []
        for chunk in chunk_text(text):
            items.extend(
                extractor.extract_items_from_text(
                    text=chunk,
                    vendor=vendor,
                    source_ref=source_ref,
                    source_type=SourceType.SCRAPE,
                )
            )
        items = _deduplicate_items(items)
    else:
        raise InventoryFormatError(
            f"unsupported inventory object {key}; expected CSV, XLSX, TXT, PDF, or HTML"
        )

    if not items:
        raise InventoryFormatError(f"no inventory items extracted from {key}")

    embeddings = embedder.embed_many([item.embedding_text() for item in items])
    indexed = search.upsert_items(items, embeddings)
    logger.info("ingest_complete key=%s items=%s indexed=%s", key, len(items), indexed)
    return indexed


def _items_from_csv(
    *,
    content: str,
    vendor: str,
    source_ref: str,
    images: ImageStore,
) -> list[InventoryItem]:
    rows: list[CsvRow] = parse_csv(content=content, vendor=vendor, source_ref=source_ref)
    return _attach_images(rows, images)


def _items_from_fixed_width(
    *,
    content: str,
    vendor: str,
    source_ref: str,
    images: ImageStore,
) -> list[InventoryItem]:
    rows = parse_fixed_width_inventory(
        content=content,
        vendor=vendor,
        source_ref=source_ref,
    )
    return _attach_images(rows, images)


def _attach_images(rows: list[CsvRow], images: ImageStore) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    for row in rows:
        refs = list(row.item.image_refs)
        for embedded in row.embedded_images:
            try:
                key = images.put_bytes(
                    vendor=row.item.vendor,
                    item_id=row.item.item_id,
                    filename=embedded.filename,
                    body=embedded.body,
                    content_type=embedded.content_type,
                )
            except ValueError as exc:
                logger.warning(
                    "embedded_image_rejected item_id=%s reason=%s",
                    row.item.item_id,
                    exc,
                )
            else:
                refs.append(key)
        if row.source_image_url and row.source_image_url.startswith("http"):
            key = images.fetch_url_and_store(
                vendor=row.item.vendor,
                item_id=row.item.item_id,
                url=row.source_image_url,
            )
            if key:
                refs.append(key)
        items.append(row.item.model_copy(update={"image_refs": refs}))
    return items


def _deduplicate_items(items: list[InventoryItem]) -> list[InventoryItem]:
    """Collapse repeated TOC/detail extraction, keeping the richer record."""
    selected: dict[str, InventoryItem] = {}
    for item in items:
        current = selected.get(item.item_id)
        if current is None or _richness(item) > _richness(current):
            selected[item.item_id] = item
    return list(selected.values())


def _richness(item: InventoryItem) -> int:
    return (
        len(item.description)
        + len(item.features) * 20
        + len(item.tags) * 10
        + int(item.dimensions_text is not None) * 20
        + int(item.unit_price is not None) * 20
        + int(item.quantity is not None) * 20
        + int(item.source_item_id is not None) * 20
    )


def _vendor_from_key(key: str) -> str:
    # uploads/{vendor}/filename → vendor; otherwise "unknown"
    parts = key.split("/")
    if len(parts) >= 3 and parts[0] == "uploads":
        return parts[1]
    return "unknown"
