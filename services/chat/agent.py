"""Groq tool-use agent for inventory chat (OpenAI-compatible API)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import replace
from typing import Any

from services.chat.catalog_view import (
    SearchRequest,
    cards_for_model,
    estimate_budget,
    format_hits_for_tool,
    group_hits_by_vendor,
)
from services.chat.gallery import AgentReply, GalleryItem, cards_to_gallery
from services.chat.images import ImageUrlService
from services.chat.persona import SYSTEM_PROMPT, is_out_of_scope_request, out_of_scope_reply
from services.chat.retrieval import InventoryRetriever
from services.chat.tools import SEARCH_TOOL_NAME, openai_tools
from shared.providers.groq import GroqKeyPool

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_FILTER_COLORS = (
    "black",
    "blue",
    "brown",
    "clear",
    "gold",
    "green",
    "navy",
    "orange",
    "pink",
    "purple",
    "red",
    "silver",
    "white",
    "yellow",
)


class InventoryChatAgent:
    def __init__(
        self,
        *,
        model_id: str | None = None,
        api_key: str | None = None,
        region: str | None = None,  # unused; kept for call-site compatibility
        retriever: InventoryRetriever,
        images: ImageUrlService | None = None,
        max_tool_rounds: int = 6,
    ) -> None:
        del region
        self._model_id = (model_id or _DEFAULT_MODEL).strip()
        self._groq = GroqKeyPool.from_env(explicit=api_key)
        self._retriever = retriever
        self._images = images
        self._max_tool_rounds = max_tool_rounds
        self._tools = openai_tools()

    def reply(
        self,
        *,
        user_message: str,
        history: list[dict[str, str]] | None = None,
    ) -> AgentReply:
        text = (user_message or "").strip()
        if not text:
            raise ValueError("user_message must be non-empty")

        if is_out_of_scope_request(text) and not _mentions_rentals(text):
            return AgentReply(text=out_of_scope_reply())

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        for turn in history or []:
            role = turn.get("role")
            content = (turn.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": text})

        try:
            return self._tool_loop(messages, user_message=text)
        except Exception as exc:
            # Demo safety net: if Groq tool validation / transient API fails,
            # still answer from a direct catalog search.
            if _is_recoverable_llm_error(exc):
                logger.warning("agent_llm_fallback reason=%s", exc)
                return self._fallback_catalog_reply(text)
            raise

    def _tool_loop(
        self,
        messages: list[dict[str, Any]],
        *,
        user_message: str,
    ) -> AgentReply:
        tool_validation_retries = 0
        gallery: tuple[GalleryItem, ...] = ()
        for _ in range(self._max_tool_rounds):
            try:
                response = self._groq.post_chat(
                    body={
                        "model": self._model_id,
                        "messages": messages,
                        "tools": self._tools,
                        "tool_choice": "auto",
                        "temperature": 0.2,
                        "max_tokens": 2048,
                    },
                    timeout_seconds=180,
                )
            except Exception as exc:
                if (
                    _is_tool_validation_error(exc)
                    and tool_validation_retries < 2
                ):
                    tool_validation_retries += 1
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your previous tool call was rejected because a numeric "
                                "argument used the wrong JSON type. Call search_inventory "
                                "again with query as a string and optional max_unit_price, "
                                "min_quantity, and size as JSON numbers (not quoted strings). "
                                "If unsure about a filter, omit it."
                            ),
                        }
                    )
                    continue
                raise

            choices = response.get("choices") or []
            if not choices:
                raise RuntimeError("Groq chat response missing choices")
            message = choices[0].get("message") or {}
            messages.append(message)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                text = (message.get("content") or "").strip() or (
                    "I could not produce a response."
                )
                return AgentReply(text=text, gallery=gallery)

            for tool_call in tool_calls:
                tool_message, round_gallery = self._run_tool(
                    tool_call,
                    user_message=user_message,
                )
                messages.append(tool_message)
                if round_gallery:
                    gallery = round_gallery

        return AgentReply(
            text=(
                "I searched several times without settling on a shortlist. "
                "Please narrow the request (category, budget, or vendor) and try again."
            ),
            gallery=gallery,
        )

    def _fallback_catalog_reply(self, user_message: str) -> AgentReply:
        """Direct OpenSearch path when the LLM tool loop cannot complete."""
        request = _apply_explicit_user_filters(
            SearchRequest(query=user_message, size=8),
            user_message,
        )
        hits = self._retriever.search(request)
        cards = format_hits_for_tool(hits)
        if self._images:
            for card in cards:
                refs = card.get("image_refs") or []
                if refs:
                    card["image_urls"] = self._images.presign_many(list(refs), limit=2)

        gallery = cards_to_gallery(cards)
        if not cards:
            return AgentReply(
                text=(
                    "I could not find catalog matches for that request. "
                    "Try a shorter item-focused ask, for example: rattan lounge chairs."
                )
            )

        lines = [
            _fallback_intro(request, count=len(gallery)),
            "",
            "Catalog quantity is not a confirmed hold; live availability is unknown.",
        ]
        return AgentReply(text="\n".join(lines), gallery=gallery)

    def _run_tool(
        self,
        tool_call: dict[str, Any],
        *,
        user_message: str,
    ) -> tuple[dict[str, Any], tuple[GalleryItem, ...]]:
        tool_call_id = tool_call.get("id") or "tool_call"
        function = tool_call.get("function") or {}
        name = function.get("name")
        raw_arguments = function.get("arguments") or "{}"

        if name != SEARCH_TOOL_NAME:
            return (
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps({"error": f"unknown tool: {name}"}),
                },
                (),
            )

        try:
            raw_input = _parse_tool_arguments(raw_arguments)
            request = _apply_explicit_user_filters(
                _parse_search_input(raw_input),
                user_message,
            )
            if not request.query:
                raise ValueError("query is required")
            hits = self._retriever.search(request)
            cards = format_hits_for_tool(hits)
            if self._images:
                for card in cards:
                    refs = card.get("image_refs") or []
                    if refs:
                        card["image_urls"] = self._images.presign_many(list(refs), limit=2)

            gallery = cards_to_gallery(cards)
            payload = {
                "hit_count": len(cards),
                "items": cards_for_model(cards),
                "applied_filters": {
                    key: value
                    for key, value in {
                        "max_unit_price": request.max_unit_price,
                        "min_quantity": request.min_quantity,
                        "category": request.category,
                        "vendor": request.vendor,
                        "color": request.color,
                    }.items()
                    if value is not None
                },
                "by_vendor": {
                    vendor: [c.get("name") for c in group]
                    for vendor, group in group_hits_by_vendor(cards).items()
                },
                "budget_estimate": estimate_budget(cards),
                "availability_note": (
                    "Catalog quantity is not a confirmed hold; live availability is unknown."
                ),
            }
            return (
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(payload),
                },
                gallery,
            )
        except Exception as exc:
            logger.exception("search_inventory_failed")
            return (
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps({"error": f"search_inventory failed: {exc}"}),
                },
                (),
            )


def _parse_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if not isinstance(raw_arguments, str):
        raise ValueError("tool arguments must be a JSON object or string")
    text = raw_arguments.strip() or "{}"
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("tool arguments must be a JSON object")
    return parsed


def _parse_search_input(raw: dict[str, Any]) -> SearchRequest:
    return SearchRequest(
        query=str(raw.get("query") or "").strip(),
        category=_optional_str(raw.get("category")),
        vendor=_optional_str(raw.get("vendor")),
        color=_optional_str(raw.get("color")),
        max_unit_price=_optional_float(raw.get("max_unit_price")),
        min_quantity=_optional_float(raw.get("min_quantity")),
        size=_optional_int(raw.get("size"), default=8, minimum=1, maximum=20),
    )


def _fallback_intro(request: SearchRequest, *, count: int) -> str:
    """User-facing summary of the catalog search; never mentions model internals."""
    constraints: list[str] = []
    if request.color:
        constraints.append(f"in {request.color}")
    if request.max_unit_price is not None:
        constraints.append(f"under ${request.max_unit_price:g} per unit")
    if request.min_quantity is not None:
        constraints.append(f"with at least {request.min_quantity:g} in stock")

    noun = "match" if count == 1 else "matches"
    sentence = f"Here {'is' if count == 1 else 'are'} {count} catalog {noun}"
    if constraints:
        sentence += " " + ", ".join(constraints)
    return sentence + ":"


def _apply_explicit_user_filters(
    request: SearchRequest,
    user_message: str,
) -> SearchRequest:
    """Enforce clear numeric constraints even when the model omits tool args."""
    max_price = _extract_max_unit_price(user_message)
    min_quantity = _extract_min_quantity(user_message)
    color = _extract_color(user_message)
    clean_query = _clean_retrieval_query(request.query)
    return replace(
        request,
        query=clean_query or request.query,
        max_unit_price=(
            max_price if max_price is not None else request.max_unit_price
        ),
        min_quantity=(
            min_quantity if min_quantity is not None else request.min_quantity
        ),
        color=color if color is not None else request.color,
    )


def _clean_retrieval_query(text: str) -> str:
    """Keep semantic intent in the embedding; numeric constraints become filters."""
    patterns = (
        r"\b(?:under|below|less\s+than|up\s+to)\s*\$?\s*\d+(?:\.\d+)?",
        r"\b(?:max(?:imum)?(?:\s+price)?|budget)(?:\s+of)?\s*[:=]?\s*"
        r"\$?\s*\d+(?:\.\d+)?",
        r"\$\s*\d+(?:\.\d+)?\s*(?:or\s+less|maximum|max)\b",
        r"\b(?:for|at\s+least|minimum(?:\s+of)?)\s+\d+(?:\.\d+)?\s*"
        r"(?:guests?|people|chairs?|seats?|units?)\b",
    )
    cleaned = text or ""
    for pattern in patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split()).strip(" ?.,")


def _extract_max_unit_price(text: str) -> float | None:
    patterns = (
        r"\b(?:under|below|less\s+than|up\s+to)\s*\$?\s*(\d+(?:\.\d+)?)",
        r"\b(?:max(?:imum)?(?:\s+price)?|budget)(?:\s+of)?\s*[:=]?\s*\$?\s*(\d+(?:\.\d+)?)",
        r"\$\s*(\d+(?:\.\d+)?)\s*(?:or\s+less|maximum|max)\b",
    )
    return _first_number_match(text, patterns)


def _extract_min_quantity(text: str) -> float | None:
    patterns = (
        r"\b(?:for|at\s+least|minimum(?:\s+of)?)\s+(\d+(?:\.\d+)?)\s*"
        r"(?:guests?|people|chairs?|seats?|units?)\b",
        r"\bneed\s+(\d+(?:\.\d+)?)\s+(?:\w+\s+){0,3}"
        r"(?:chairs?|seats?|units?)\b",
    )
    return _first_number_match(text, patterns)


def _extract_color(text: str) -> str | None:
    lowered = (text or "").lower()
    for color in _FILTER_COLORS:
        if re.search(rf"\b{re.escape(color)}\b", lowered):
            return color
    return None


def _first_number_match(text: str, patterns: tuple[str, ...]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    try:
        return float(text)
    except ValueError:
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        return float(match.group(0)) if match else None


def _optional_int(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if value is None or value == "":
        return default
    number = _optional_float(value)
    if number is None:
        return default
    return max(minimum, min(maximum, int(number)))


def _is_tool_validation_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "tool_use_failed" in text or (
        "http 400" in text and "tool" in text
    )


def _is_recoverable_llm_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        _is_tool_validation_error(exc)
        or "http 429" in text
        or "rate-limited on every configured key" in text
        or "http 500" in text
        or "http 502" in text
        or "http 503" in text
        or "http 504" in text
        or "tool-call limit" in text
    )


def _mentions_rentals(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in (
            "rent",
            "rental",
            "chair",
            "table",
            "lounge",
            "linen",
            "tent",
            "furniture",
            "inventory",
        )
    )
