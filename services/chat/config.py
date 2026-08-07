"""Runtime configuration for the chat service. Fail fast on missing required env."""

from __future__ import annotations

import os
from dataclasses import dataclass

from shared.providers.secrets import load_local_dotenv


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"required environment variable {name} is not set")
    return value


@dataclass(frozen=True)
class ChatConfig:
    aws_region: str
    opensearch_endpoint: str
    opensearch_index: str
    groq_model_id: str
    hf_embed_model_id: str
    dynamodb_table_name: str
    data_bucket_name: str
    images_prefix: str
    cognito_user_pool_id: str
    cognito_app_client_id: str
    session_ttl_days: int = 30
    max_tool_rounds: int = 4
    default_search_size: int = 8
    max_search_size: int = 20
    image_url_ttl_seconds: int = 3600

    @classmethod
    def from_env(cls) -> "ChatConfig":
        load_local_dotenv()
        region = (
            os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        images_prefix = os.environ.get("IMAGES_PREFIX", "images/").strip() or "images/"
        if not images_prefix.endswith("/"):
            images_prefix = f"{images_prefix}/"

        return cls(
            aws_region=region,
            opensearch_endpoint=_require("OPENSEARCH_ENDPOINT"),
            opensearch_index=os.environ.get("OPENSEARCH_INDEX", "inventory-items").strip(),
            groq_model_id=os.environ.get(
                "GROQ_MODEL_ID",
                "llama-3.3-70b-versatile",
            ).strip(),
            hf_embed_model_id=os.environ.get(
                "HF_EMBED_MODEL_ID",
                "BAAI/bge-large-en-v1.5",
            ).strip(),
            dynamodb_table_name=_require("DYNAMODB_TABLE_NAME"),
            data_bucket_name=_require("DATA_BUCKET_NAME"),
            images_prefix=images_prefix,
            cognito_user_pool_id=_require("COGNITO_USER_POOL_ID"),
            cognito_app_client_id=_require("COGNITO_APP_CLIENT_ID"),
            session_ttl_days=int(os.environ.get("SESSION_TTL_DAYS", "30")),
            max_tool_rounds=int(os.environ.get("MAX_TOOL_ROUNDS", "6")),
            default_search_size=int(os.environ.get("DEFAULT_SEARCH_SIZE", "8")),
            max_search_size=int(os.environ.get("MAX_SEARCH_SIZE", "20")),
            image_url_ttl_seconds=int(os.environ.get("IMAGE_URL_TTL_SECONDS", "3600")),
        )
