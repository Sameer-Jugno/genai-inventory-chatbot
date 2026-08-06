"""Resolve API keys from process env or AWS Secrets Manager.

Local: put ``GROQ_API_KEY`` (and optional ``GROQ_API_KEY_2`` …) plus ``HF_TOKEN``
in a gitignored ``.env``.
AWS: set ``PROVIDER_SECRETS_ARN`` to a Secrets Manager secret whose JSON holds
the same fields.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)


def load_local_dotenv(*, start: Path | None = None) -> None:
    """Load ``.env`` from the repo root if present. Never overrides existing env."""
    root = start or Path(__file__).resolve().parents[2]
    env_path = root / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@lru_cache(maxsize=1)
def _secrets_from_arn(secret_arn: str) -> dict[str, str]:
    import boto3

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    raw = response.get("SecretString") or ""
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError(f"secret {secret_arn} must be a JSON object")
    return {str(k): str(v) for k, v in payload.items() if v is not None}


def secrets_payload(secret_arn: str) -> dict[str, str]:
    """Return the full Secrets Manager JSON payload (cached)."""
    return dict(_secrets_from_arn(secret_arn))


def require_secret(name: str) -> str:
    """Return a required API key from env or PROVIDER_SECRETS_ARN."""
    direct = os.environ.get(name, "").strip()
    if direct:
        return direct

    secret_arn = os.environ.get("PROVIDER_SECRETS_ARN", "").strip()
    if secret_arn:
        value = (_secrets_from_arn(secret_arn).get(name) or "").strip()
        if value:
            return value

    raise RuntimeError(
        f"required secret {name} is not set "
        f"(env {name} or PROVIDER_SECRETS_ARN JSON field)"
    )
