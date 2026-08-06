"""Groq API key pool with automatic rotation on rate limits.

Keys are loaded from (in order):
1. Explicit constructor / function args
2. ``GROQ_API_KEYS`` — comma-separated or JSON array
3. ``GROQ_API_KEY``, ``GROQ_API_KEY_2``, ``GROQ_API_KEY_3``, …

When a key returns HTTP 429, it is cooled down until the provider's suggested
retry time and the next available key is used. Permanent failover behaviour —
not a demo-day workaround.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from shared.providers.http_json import post_json
from shared.providers.secrets import require_secret, secrets_payload

logger = logging.getLogger(__name__)

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_COOLDOWN_SECONDS = 60.0
_MAX_NUMBERED_KEYS = 8


@dataclass
class _KeyState:
    value: str
    label: str
    cool_until: float = 0.0


@dataclass
class GroqKeyPool:
    """Thread-safe rotating pool of Groq API keys."""

    keys: list[_KeyState] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _cursor: int = 0

    @classmethod
    def from_env(cls, *, explicit: str | list[str] | None = None) -> GroqKeyPool:
        values = _normalize_keys(explicit) or load_groq_api_keys()
        if not values:
            raise RuntimeError(
                "no Groq API keys configured "
                "(set GROQ_API_KEY and optional GROQ_API_KEY_2, …)"
            )
        return cls(
            keys=[
                _KeyState(value=key, label=_label_for(index, key))
                for index, key in enumerate(values)
            ]
        )

    def available_count(self, *, now: float | None = None) -> int:
        stamp = time.time() if now is None else now
        with self._lock:
            return sum(1 for key in self.keys if key.cool_until <= stamp)

    def post_chat(
        self,
        *,
        body: dict[str, Any],
        timeout_seconds: float = 180,
    ) -> Any:
        """POST /chat/completions, rotating keys on HTTP 429."""
        errors: list[str] = []
        attempted: set[str] = set()

        while True:
            state = self._acquire(skip=attempted)
            if state is None:
                detail = "; ".join(errors) or "all keys exhausted"
                raise RuntimeError(
                    f"Groq rate-limited on every configured key: {detail}"
                )

            attempted.add(state.label)
            try:
                return post_json(
                    _GROQ_CHAT_URL,
                    headers={"Authorization": f"Bearer {state.value}"},
                    body=body,
                    timeout_seconds=timeout_seconds,
                    # Do not burn retries on the same depleted key — rotate instead.
                    retry_statuses={408, 425, 500, 502, 503, 504},
                    max_attempts=3,
                )
            except Exception as exc:
                if not _is_rate_limit(exc):
                    raise
                cool_for = _cooldown_seconds(str(exc))
                self._cooldown(state, cool_for)
                errors.append(f"{state.label} cooldown={cool_for:.0f}s")
                logger.warning(
                    "groq_key_rate_limited key=%s cooldown_seconds=%.0f trying_next=%s",
                    state.label,
                    cool_for,
                    self.available_count() > 0,
                )

    def _acquire(self, *, skip: set[str]) -> _KeyState | None:
        now = time.time()
        with self._lock:
            total = len(self.keys)
            if total == 0:
                return None
            for _ in range(total):
                state = self.keys[self._cursor % total]
                self._cursor = (self._cursor + 1) % total
                if state.label in skip:
                    continue
                if state.cool_until <= now:
                    return state
            return None

    def _cooldown(self, state: _KeyState, seconds: float) -> None:
        with self._lock:
            state.cool_until = max(state.cool_until, time.time() + max(seconds, 1.0))


def load_groq_api_keys() -> list[str]:
    """Collect configured Groq keys from env and Secrets Manager."""
    collected: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        text = (value or "").strip()
        if text and text not in seen:
            seen.add(text)
            collected.append(text)

    for value in _normalize_keys(os.environ.get("GROQ_API_KEYS")):
        add(value)

    for name in _numbered_names():
        add(os.environ.get(name))

    secret_arn = os.environ.get("PROVIDER_SECRETS_ARN", "").strip()
    if secret_arn:
        try:
            payload = secrets_payload(secret_arn)
        except Exception:
            logger.exception("groq_keys_secret_load_failed")
            payload = {}
        for value in _normalize_keys(payload.get("GROQ_API_KEYS")):
            add(value)
        for name in _numbered_names():
            raw = payload.get(name)
            add(raw if isinstance(raw, str) else None)

    if not collected:
        add(require_secret("GROQ_API_KEY"))

    return collected


def _numbered_names() -> list[str]:
    names = ["GROQ_API_KEY"]
    names.extend(f"GROQ_API_KEY_{index}" for index in range(2, _MAX_NUMBERED_KEYS + 1))
    return names


def _normalize_keys(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [part.strip() for part in text.split(",") if part.strip()]


def _label_for(index: int, key: str) -> str:
    suffix = key[-4:] if len(key) >= 4 else key
    return f"key{index + 1}…{suffix}"


def _is_rate_limit(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "http 429" in text or "rate_limit" in text or "rate limit" in text


def _cooldown_seconds(message: str) -> float:
    match = re.search(
        r"try again in\s+(\d+)m([\d.]+)s",
        message,
        flags=re.IGNORECASE,
    )
    if match:
        return float(match.group(1)) * 60.0 + float(match.group(2))
    match = re.search(r"try again in\s+([\d.]+)s", message, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))
    match = re.search(r"retry-after['\":\s]+(\d+)", message, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))
    return _DEFAULT_COOLDOWN_SECONDS
