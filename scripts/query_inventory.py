"""Live Phase 2 retrieval smoke test using HF embeddings + OpenSearch Serverless."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.ingestion.embedding import EmbeddingClient
from services.ingestion.opensearch_client import OpenSearchInventoryClient
from shared.providers.secrets import load_local_dotenv


def main() -> int:
    load_local_dotenv()
    parser = argparse.ArgumentParser(description="Semantic inventory search")
    parser.add_argument("query")
    parser.add_argument("--category")
    parser.add_argument("--vendor")
    parser.add_argument("--color")
    parser.add_argument("--max-price", type=float)
    parser.add_argument("--min-quantity", type=float)
    parser.add_argument("--size", type=int, default=10)
    args = parser.parse_args()

    endpoint = os.environ.get("OPENSEARCH_ENDPOINT")
    if not endpoint:
        print("Set OPENSEARCH_ENDPOINT first.", file=sys.stderr)
        return 1

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    index = os.environ.get("OPENSEARCH_INDEX", "inventory-items")
    model_id = os.environ.get("HF_EMBED_MODEL_ID", "BAAI/bge-large-en-v1.5")

    embedder = EmbeddingClient(model_id=model_id, region=region)
    search = OpenSearchInventoryClient(
        endpoint=endpoint,
        index=index,
        region=region,
    )
    results = search.vector_search(
        embedder.embed_text(args.query),
        size=args.size,
        category=args.category,
        max_unit_price=args.max_price,
        min_quantity=args.min_quantity,
        vendor=args.vendor,
        color=args.color,
    )
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
