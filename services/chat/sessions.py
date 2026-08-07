"""DynamoDB chat session history (ADR-002 / ADR-011)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

import boto3
from boto3.dynamodb.conditions import Key

Role = Literal["user", "assistant", "system", "tool"]

USER_SUB_INDEX = "user_sub-index"


@dataclass(frozen=True)
class SessionMessage:
    session_id: str
    timestamp: int
    role: Role
    content: str
    user_sub: str | None = None
    expires_at: int | None = None
    metadata: dict[str, Any] | None = None

    def to_item(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "role": self.role,
            "content": self.content,
        }
        if self.user_sub:
            item["user_sub"] = self.user_sub
        if self.expires_at is not None:
            item["expires_at"] = self.expires_at
        if self.metadata:
            item["metadata"] = self.metadata
        return item

    @classmethod
    def from_item(cls, item: dict[str, Any]) -> "SessionMessage":
        return cls(
            session_id=str(item["session_id"]),
            timestamp=int(item["timestamp"]),
            role=item["role"],  # type: ignore[arg-type]
            content=str(item.get("content") or ""),
            user_sub=item.get("user_sub"),
            expires_at=int(item["expires_at"]) if item.get("expires_at") is not None else None,
            metadata=item.get("metadata"),
        )


@dataclass(frozen=True)
class SessionSummary:
    """One conversation thread belonging to a Cognito user."""

    session_id: str
    user_sub: str
    last_timestamp: int
    message_count: int
    preview: str


class SessionStore:
    def __init__(self, *, table_name: str, region: str, ttl_days: int = 30) -> None:
        resource = boto3.resource("dynamodb", region_name=region)
        self._table = resource.Table(table_name)
        self._ttl_days = ttl_days

    def append(
        self,
        *,
        session_id: str,
        role: Role,
        content: str,
        user_sub: str | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp_ms: int | None = None,
    ) -> SessionMessage:
        now_ms = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
        expires_at = int(time.time()) + self._ttl_days * 24 * 60 * 60
        message = SessionMessage(
            session_id=session_id,
            timestamp=now_ms,
            role=role,
            content=content,
            user_sub=user_sub,
            expires_at=expires_at,
            metadata=metadata,
        )
        self._table.put_item(Item=message.to_item())
        return message

    def list_messages(self, session_id: str, *, limit: int = 100) -> list[SessionMessage]:
        response = self._table.query(
            KeyConditionExpression=Key("session_id").eq(session_id),
            ScanIndexForward=True,
            Limit=limit,
        )
        return [SessionMessage.from_item(item) for item in response.get("Items", [])]

    def list_sessions_for_user(
        self,
        user_sub: str,
        *,
        limit: int = 10,
        scan_limit: int = 200,
    ) -> list[SessionSummary]:
        """Newest sessions first, derived from the user_sub GSI."""
        sub = (user_sub or "").strip()
        if not sub:
            return []

        response = self._table.query(
            IndexName=USER_SUB_INDEX,
            KeyConditionExpression=Key("user_sub").eq(sub),
            ScanIndexForward=False,
            Limit=scan_limit,
        )
        grouped: dict[str, dict[str, Any]] = {}
        for item in response.get("Items", []):
            session_id = str(item["session_id"])
            timestamp = int(item["timestamp"])
            content = str(item.get("content") or "")
            role = str(item.get("role") or "")
            current = grouped.get(session_id)
            if current is None:
                preview = content if role == "user" else ""
                grouped[session_id] = {
                    "last_timestamp": timestamp,
                    "message_count": 1,
                    "preview": preview,
                }
                continue
            current["message_count"] += 1
            if timestamp > current["last_timestamp"]:
                current["last_timestamp"] = timestamp
            if role == "user" and not current["preview"]:
                current["preview"] = content

        summaries = [
            SessionSummary(
                session_id=session_id,
                user_sub=sub,
                last_timestamp=int(data["last_timestamp"]),
                message_count=int(data["message_count"]),
                preview=_preview_text(str(data["preview"])),
            )
            for session_id, data in grouped.items()
        ]
        summaries.sort(key=lambda row: row.last_timestamp, reverse=True)
        return summaries[:limit]


def _preview_text(content: str, *, limit: int = 80) -> str:
    text = " ".join((content or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
