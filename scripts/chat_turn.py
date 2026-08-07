"""One-turn live chat smoke against OpenSearch + Groq (Phase 3)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.chat.agent import InventoryChatAgent
from services.chat.retrieval import InventoryRetriever
from services.ingestion.embedding import EmbeddingClient
from services.ingestion.opensearch_client import OpenSearchInventoryClient
from shared.providers.secrets import load_local_dotenv


def main() -> int:
    load_local_dotenv()
    parser = argparse.ArgumentParser(description="Run one Inventory Planner agent turn")
    parser.add_argument("message")
    args = parser.parse_args()

    endpoint = os.environ.get("OPENSEARCH_ENDPOINT")
    if not endpoint:
        print("Set OPENSEARCH_ENDPOINT first.", file=sys.stderr)
        return 1

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    index = os.environ.get("OPENSEARCH_INDEX", "inventory-items")
    groq_model = os.environ.get("GROQ_MODEL_ID", "llama-3.3-70b-versatile")
    embed_model = os.environ.get("HF_EMBED_MODEL_ID", "BAAI/bge-large-en-v1.5")

    embedder = EmbeddingClient(model_id=embed_model, region=region)
    search = OpenSearchInventoryClient(endpoint=endpoint, index=index, region=region)
    retriever = InventoryRetriever(embedder=embedder, search=search)
    agent = InventoryChatAgent(
        model_id=groq_model,
        region=region,
        retriever=retriever,
    )
    reply = agent.reply(user_message=args.message)
    print(reply.text)
    if reply.gallery:
        print(f"\n[gallery: {len(reply.gallery)} item(s)]")
        for item in reply.gallery:
            bits = [item.name]
            if item.image_url:
                bits.append(f"image={item.image_url[:80]}...")
            elif item.product_url:
                bits.append(f"product={item.product_url}")
            print(" - " + " | ".join(bits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
