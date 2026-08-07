"""Tool contract constants for the inventory chat agent (no AWS imports)."""

from __future__ import annotations

import json
from typing import Any

SEARCH_TOOL_NAME = "search_inventory"

# Numeric fields accept number OR string because Groq validates model tool
# calls strictly and Llama often emits "20" instead of 20.
_NUMBER_OR_STRING: dict[str, Any] = {"type": ["number", "string"]}
_INTEGER_OR_STRING: dict[str, Any] = {"type": ["integer", "string", "number"]}

SEARCH_TOOL_SPEC: dict[str, Any] = {
    "toolSpec": {
        "name": SEARCH_TOOL_NAME,
        "description": (
            "Semantic search over the rental inventory catalog. "
            "Use before recommending specific items. Apply filters when the user "
            "states budget, quantity, category, vendor, or color constraints. "
            "Prefer omitting a filter over guessing."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search text (theme, item type, style).",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional top-level category filter, e.g. seating, tables.",
                    },
                    "vendor": {
                        "type": "string",
                        "description": "Optional vendor name filter.",
                    },
                    "color": {
                        "type": "string",
                        "description": "Optional color filter matching indexed color tags.",
                    },
                    "max_unit_price": {
                        **_NUMBER_OR_STRING,
                        "description": "Maximum unit price (inclusive). Number or numeric string.",
                    },
                    "min_quantity": {
                        **_NUMBER_OR_STRING,
                        "description": (
                            "Minimum catalog quantity (inclusive). Number or numeric string. "
                            "Omit unless the user explicitly needs that many units in stock."
                        ),
                    },
                    "size": {
                        **_INTEGER_OR_STRING,
                        "description": "Max hits to return (default 8, max 20). Number or numeric string.",
                    },
                },
                "required": ["query"],
            }
        },
    }
}


def tool_spec_public() -> dict[str, Any]:
    return json.loads(json.dumps(SEARCH_TOOL_SPEC))


def openai_tools() -> list[dict[str, Any]]:
    """Groq / OpenAI-compatible tool list derived from the Bedrock-shaped contract."""
    spec = SEARCH_TOOL_SPEC["toolSpec"]
    return [
        {
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec["description"],
                "parameters": spec["inputSchema"]["json"],
            },
        }
    ]
