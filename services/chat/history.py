"""Model-facing conversation history.

Persisted assistant turns carry rendered catalog cards with presigned image
URLs. Those are display artefacts: replaying them would spend most of the
model's context (and the daily provider token budget) on links it cannot use,
so history is reduced to the narrative and bounded on both turns and size.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Protocol

MAX_TURNS = 10
MAX_CHARS_PER_TURN = 1_200
MAX_TOTAL_CHARS = 6_000


class _HasRoleAndContent(Protocol):
    role: str
    content: str


def model_history(
    messages: Iterable[_HasRoleAndContent],
    *,
    strip: Any,
    max_turns: int = MAX_TURNS,
    max_chars_per_turn: int = MAX_CHARS_PER_TURN,
    max_total_chars: int = MAX_TOTAL_CHARS,
) -> list[dict[str, str]]:
    """Newest-first budgeting, returned oldest-first for the chat API."""
    cleaned: list[dict[str, str]] = []
    for message in messages:
        role = getattr(message, "role", "")
        if role not in {"user", "assistant"}:
            continue
        content = getattr(message, "content", "") or ""
        if role == "assistant":
            content = strip(content)
        content = " ".join(content.split())
        if not content:
            continue
        if len(content) > max_chars_per_turn:
            content = content[: max_chars_per_turn - 1].rstrip() + "…"
        cleaned.append({"role": role, "content": content})

    return _budget(cleaned, max_turns=max_turns, max_total_chars=max_total_chars)


def _budget(
    turns: Sequence[dict[str, str]],
    *,
    max_turns: int,
    max_total_chars: int,
) -> list[dict[str, str]]:
    kept: list[dict[str, str]] = []
    total = 0
    for turn in reversed(turns):
        if len(kept) >= max_turns:
            break
        size = len(turn["content"])
        if kept and total + size > max_total_chars:
            break
        kept.append(turn)
        total += size
    kept.reverse()
    return kept
