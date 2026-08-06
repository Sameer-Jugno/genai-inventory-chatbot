"""
Create the inventory OpenSearch index after the collection exists.

Usage (after Phase 2 OpenSearch is applied):
  export OPENSEARCH_ENDPOINT="https://..."
  export OPENSEARCH_INDEX="inventory-items"
  export AWS_REGION="us-east-1"   # optional; defaults to us-east-1
  python scripts/create_opensearch_index.py

Uses SigV4 (service aoss) with the default AWS credential chain.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

MAPPING_PATH = Path(__file__).with_name("opensearch_index_mapping.json")


def main() -> int:
    endpoint = os.environ.get("OPENSEARCH_ENDPOINT")
    index = os.environ.get("OPENSEARCH_INDEX", "inventory-items")
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"

    if not endpoint:
        print("Set OPENSEARCH_ENDPOINT first.", file=sys.stderr)
        return 1

    mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    host = endpoint.replace("https://", "").replace("http://", "").rstrip("/")

    credentials = boto3.Session().get_credentials()
    if credentials is None:
        print("No AWS credentials available.", file=sys.stderr)
        return 1

    frozen = credentials.get_frozen_credentials()
    auth = AWS4Auth(
        frozen.access_key,
        frozen.secret_key,
        region,
        "aoss",
        session_token=frozen.token,
    )

    client = OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=60,
    )

    if client.indices.exists(index=index):
        print(f"Index '{index}' already exists on {endpoint}")
        return 0

    client.indices.create(index=index, body=mapping)
    print(f"Created index '{index}' on {endpoint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
