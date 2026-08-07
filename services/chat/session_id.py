"""Durable chat session identity for Cognito users.

Sessions are real DynamoDB threads owned by a Cognito ``sub``:
- ``user:<sub>`` — legacy single-thread id (still resumed if it has history)
- ``user:<sub>:<uuid>`` — additional threads created via New chat

Refresh / re-login resumes the user's most recently updated session.
"""

from __future__ import annotations

import uuid
from typing import Any


def user_sub_from(user: Any | None) -> str | None:
    if user is None:
        return None
    metadata = getattr(user, "metadata", None) or {}
    if isinstance(metadata, dict):
        sub = metadata.get("sub")
        if isinstance(sub, str) and sub.strip():
            return sub.strip()
    return None


def legacy_session_id(user_sub: str) -> str:
    return f"user:{user_sub}"


def new_session_id(user_sub: str | None = None) -> str:
    """Create a new durable thread id (or anonymous UUID if unauthenticated)."""
    if user_sub:
        return f"user:{user_sub}:{uuid.uuid4()}"
    return str(uuid.uuid4())


def durable_session_id(user: Any | None) -> str:
    """Backward-compatible helper: legacy id when logged in, else random UUID."""
    sub = user_sub_from(user)
    if sub:
        return legacy_session_id(sub)
    return str(uuid.uuid4())
