"""Smoke test CSV parser without AWS."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from services.ingestion.parsers.csv_parser import parse_csv


def main() -> None:
    sample = Path(__file__).with_name("samples") / "sample_inventory.csv"
    content = sample.read_text(encoding="utf-8")
    rows = parse_csv(
        content=content,
        vendor="demo-vendor",
        source_ref="s3://example/uploads/demo-vendor/sample_inventory.csv",
    )
    assert len(rows) == 3, rows
    assert rows[0].item.description.startswith("Round banquet")
    assert "table" in rows[0].item.tags
    assert rows[0].item.raw_excerpt is None
    text = rows[0].item.embedding_text()
    assert "Round banquet" in text
    print(f"ok: parsed {len(rows)} rows")
    for row in rows:
        print(
            f" - {row.item.item_id[:8]}… {row.item.description} "
            f"tags={row.item.tags} image_url={row.source_image_url}"
        )


if __name__ == "__main__":
    main()
