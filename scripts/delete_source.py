"""Remove indexed items that came from one upload (source_ref).

AOSS vector collections do not implement ``_delete_by_query``, so documents are
located by ``source_ref`` and deleted by their AOSS-generated ``_id``. Deletes
tolerate 404s: AOSS is eventually consistent, so a document can disappear
between the search that found it and the delete that targets it.

Usage:
    python3 scripts/delete_source.py --contains demo_chairs_with_images
    python3 scripts/delete_source.py --contains demo_chairs --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from opensearchpy.exceptions import NotFoundError

from services.ingestion.opensearch_client import OpenSearchInventoryClient
from shared.providers.secrets import load_local_dotenv

_PAGE_SIZE = 100
_MAX_PASSES = 20


def main() -> int:
    load_local_dotenv()
    parser = argparse.ArgumentParser(description="Delete indexed items by source_ref")
    parser.add_argument(
        "--contains",
        required=True,
        help="Substring of source_ref to match, e.g. the uploaded filename.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform deletion. Without this flag the script only reports matches.",
    )
    args = parser.parse_args()

    endpoint = os.environ.get("OPENSEARCH_ENDPOINT")
    if not endpoint:
        print("Set OPENSEARCH_ENDPOINT first.", file=sys.stderr)
        return 1

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    index = os.environ.get("OPENSEARCH_INDEX", "inventory-items")

    client = OpenSearchInventoryClient(endpoint=endpoint, index=index, region=region)
    raw = client._client  # noqa: SLF001 - maintenance script; no public delete API yet
    query = {"wildcard": {"source_ref": f"*{args.contains}*"}}

    found = _search_page(raw, index=index, query=query)
    if not args.apply:
        print(f"Would delete {len(found)} document(s) matching source_ref *{args.contains}*")
        for name in list(found.values())[:20]:
            print(f"  - {name}")
        print("\nRe-run with --apply to delete.")
        return 0

    deleted = 0
    missing = 0
    for _ in range(_MAX_PASSES):
        if not found:
            break
        for document_id, name in found.items():
            try:
                raw.delete(index=index, id=document_id)
                deleted += 1
                print(f"  deleted {name}")
            except NotFoundError:
                missing += 1
        found = _search_page(raw, index=index, query=query)

    print(f"\nDeleted {deleted} document(s); {missing} already gone.")
    remaining = _search_page(raw, index=index, query=query)
    print(f"Remaining matches: {len(remaining)}")
    return 0 if not remaining else 1


def _search_page(raw, *, index: str, query: dict) -> dict[str, str]:
    response = raw.search(
        index=index,
        body={"size": _PAGE_SIZE, "_source": ["name", "source_ref"], "query": query},
    )
    return {
        hit["_id"]: hit.get("_source", {}).get("name") or "?"
        for hit in response.get("hits", {}).get("hits", [])
    }


if __name__ == "__main__":
    raise SystemExit(main())
