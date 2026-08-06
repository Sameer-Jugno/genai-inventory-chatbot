"""Minimal JSON HTTPS client (stdlib only — safe for Lambda packages)."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_USER_AGENT = "inventory-planner/1.0"


def post_json(
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout_seconds: float = 120,
    max_attempts: int = 4,
    retry_statuses: set[int] | None = None,
) -> Any:
    payload = json.dumps(body).encode("utf-8")
    request_headers = {
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
        **headers,
    }
    retryable = retry_statuses if retry_statuses is not None else {
        408,
        425,
        429,
        500,
        502,
        503,
        504,
    }
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        req = urllib.request.Request(
            url,
            data=payload,
            headers=request_headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")[:800]
            last_error = RuntimeError(f"HTTP {exc.code} from {url}: {err_body}")
            # Retry rate limits / transient upstream errors.
            if exc.code in retryable and attempt < max_attempts:
                sleep_for = min(2 ** attempt, 16)
                logger.warning(
                    "http_json_retry url=%s status=%s attempt=%s sleep=%s",
                    url,
                    exc.code,
                    attempt,
                    sleep_for,
                )
                time.sleep(sleep_for)
                continue
            raise last_error from exc
        except Exception as exc:  # noqa: BLE001 — surface as RuntimeError
            last_error = exc
            if attempt < max_attempts:
                time.sleep(min(2 ** attempt, 16))
                continue
            raise RuntimeError(f"request failed for {url}: {exc}") from exc
    raise RuntimeError(f"request failed for {url}: {last_error}")
