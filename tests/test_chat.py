from __future__ import annotations

import unittest

from services.chat.catalog_view import (
    SearchRequest,
    estimate_budget,
    format_hits_for_tool,
    group_hits_by_vendor,
)
from services.chat.gallery import cards_to_gallery, gallery_markdown
from services.chat.persona import is_out_of_scope_request, out_of_scope_reply
from services.chat.sessions import SessionMessage
from services.chat.tools import SEARCH_TOOL_NAME, SEARCH_TOOL_SPEC, tool_spec_public


class PersonaTests(unittest.TestCase):
    def test_flags_catering_as_out_of_scope(self) -> None:
        self.assertTrue(is_out_of_scope_request("Can you arrange catering for 200?"))
        self.assertIn("rental inventory", out_of_scope_reply().lower())

    def test_allows_rental_asks(self) -> None:
        self.assertFalse(
            is_out_of_scope_request("Need rattan lounge chairs for a rooftop cocktail party")
        )


class RetrievalHelpersTests(unittest.TestCase):
    def test_format_hits_omits_noise_and_trims_description(self) -> None:
        hits = [
            {
                "item_id": "abc",
                "name": "Rattan Lounge",
                "vendor": "acme",
                "description": "x" * 400,
                "embedding": [0.1] * 8,
                "unit_price": 120,
                "currency": "USD",
                "quantity": 6,
                "tags": ["lounge", "rattan"],
                "image_refs": ["images/acme/1.png"],
            }
        ]
        [card] = format_hits_for_tool(hits)
        self.assertEqual(card["name"], "Rattan Lounge")
        self.assertNotIn("embedding", card)
        self.assertLessEqual(len(card["description"] or ""), 281)
        self.assertEqual(card["image_refs"], ["images/acme/1.png"])

    def test_group_and_budget(self) -> None:
        hits = [
            {"item_id": "1", "name": "A", "vendor": "v1", "unit_price": 10, "currency": "USD"},
            {"item_id": "2", "name": "B", "vendor": "v1", "unit_price": None},
            {"item_id": "3", "name": "C", "vendor": "v2", "unit_price": 5, "currency": "USD"},
        ]
        grouped = group_hits_by_vendor(hits)
        self.assertEqual(sorted(grouped), ["v1", "v2"])
        budget = estimate_budget(hits, quantities={"1": 2, "3": 4})
        self.assertEqual(budget["priced_item_count"], 2)
        self.assertEqual(budget["missing_price_count"], 1)
        self.assertEqual(budget["estimated_total"], 2 * 10 + 4 * 5)

    def test_search_request_defaults(self) -> None:
        req = SearchRequest(query="vintage chairs")
        self.assertEqual(req.size, 8)
        self.assertIsNone(req.max_unit_price)

    def test_formats_vendor_for_display(self) -> None:
        cards = format_hits_for_tool(
            [
                {
                    "name": "Rattan Chair",
                    "vendor": "demo-vendor",
                    "product_url": "https://example.com/demo/rattan",
                },
                {
                    "name": "Bamboo Chair",
                    "vendor": "demo-vendor",
                    "product_url": "https://www.acmebrooklyn.com/prop/bamboo-chair/",
                },
            ]
        )
        self.assertEqual(cards[0]["vendor"], "CandyWagon Demo Inventory")
        self.assertEqual(cards[1]["vendor"], "ACME Brooklyn")


class AgentContractTests(unittest.TestCase):
    def test_tool_spec_is_stable(self) -> None:
        spec = tool_spec_public()
        self.assertEqual(spec["toolSpec"]["name"], SEARCH_TOOL_NAME)
        props = spec["toolSpec"]["inputSchema"]["json"]["properties"]
        self.assertIn("query", props)
        self.assertIn("max_unit_price", props)
        self.assertEqual(SEARCH_TOOL_SPEC["toolSpec"]["name"], SEARCH_TOOL_NAME)

    def test_openai_tools_mirror_contract(self) -> None:
        from services.chat.tools import openai_tools

        tools = openai_tools()
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["type"], "function")
        self.assertEqual(tools[0]["function"]["name"], SEARCH_TOOL_NAME)
        props = tools[0]["function"]["parameters"]["properties"]
        self.assertIn("query", props)
        # Groq is strict: numeric filters must accept number or string.
        self.assertEqual(props["min_quantity"]["type"], ["number", "string"])
        self.assertIn("string", props["size"]["type"])


class AgentParseTests(unittest.TestCase):
    def test_parses_numeric_strings(self) -> None:
        from services.chat.agent import _parse_search_input

        req = _parse_search_input(
            {
                "query": "rattan chairs",
                "min_quantity": "20",
                "max_unit_price": "50",
                "size": "10",
            }
        )
        self.assertEqual(req.query, "rattan chairs")
        self.assertEqual(req.min_quantity, 20.0)
        self.assertEqual(req.max_unit_price, 50.0)
        self.assertEqual(req.size, 10)

    def test_clamps_size_and_ignores_junk(self) -> None:
        from services.chat.agent import _parse_search_input

        req = _parse_search_input({"query": "chairs", "size": "999", "min_quantity": "about 30"})
        self.assertEqual(req.size, 20)
        self.assertEqual(req.min_quantity, 30.0)

    def test_enforces_explicit_price_when_model_omits_it(self) -> None:
        from services.chat.agent import _apply_explicit_user_filters

        req = _apply_explicit_user_filters(
            SearchRequest(query="What lounge chairs do you have under $100?"),
            "What lounge chairs do you have under $100?",
        )
        self.assertEqual(req.max_unit_price, 100.0)
        self.assertEqual(req.query, "What lounge chairs do you have")

    def test_enforces_guest_count_as_minimum_quantity(self) -> None:
        from services.chat.agent import _apply_explicit_user_filters

        req = _apply_explicit_user_filters(
            SearchRequest(query="gold chiavari chairs for 80 guests"),
            "Show me gold chiavari chairs for 80 guests",
        )
        self.assertEqual(req.min_quantity, 80.0)
        self.assertEqual(req.query, "gold chiavari chairs")

    def test_explicit_constraint_overrides_model_value(self) -> None:
        from services.chat.agent import _apply_explicit_user_filters

        req = _apply_explicit_user_filters(
            SearchRequest(query="chairs", max_unit_price=250),
            "Chairs below $75",
        )
        self.assertEqual(req.max_unit_price, 75.0)

    def test_combines_color_price_and_quantity_filters(self) -> None:
        from services.chat.agent import _apply_explicit_user_filters

        req = _apply_explicit_user_filters(
            SearchRequest(query="gold chairs under $20 for 80 guests"),
            "Show gold chairs under $20 for 80 guests",
        )
        self.assertEqual(req.color, "gold")
        self.assertEqual(req.max_unit_price, 20.0)
        self.assertEqual(req.min_quantity, 80.0)
        self.assertEqual(req.query, "gold chairs")


class ModelContextTests(unittest.TestCase):
    """Presigned URLs and internal IDs must never reach the provider."""

    def test_model_cards_drop_media_and_ids(self) -> None:
        from services.chat.catalog_view import cards_for_model

        [card] = cards_for_model(
            [
                {
                    "item_id": "abc123",
                    "name": "Gold Chiavari Chair",
                    "vendor": "CandyWagon Demo Inventory",
                    "unit_price": 12.5,
                    "quantity": 120,
                    "tags": ["chair", "gold"],
                    "score": 0.9,
                    "source_item_id": "CH-DEMO-02",
                    "image_refs": ["images/demo-vendor/x/y.png"],
                    "image_urls": ["https://s3.example/presigned?sig=" + "a" * 200],
                }
            ]
        )
        self.assertEqual(card["name"], "Gold Chiavari Chair")
        self.assertEqual(card["unit_price"], 12.5)
        self.assertTrue(card["has_photo"])
        for leaked in ("image_urls", "image_refs", "item_id", "score", "source_item_id"):
            self.assertNotIn(leaked, card)

    def test_history_strips_rendered_cards(self) -> None:
        from services.chat.gallery import GalleryItem, gallery_markdown, strip_gallery
        from services.chat.history import model_history

        narrative = "Here are 2 catalog matches under $100:"
        rendered = narrative + gallery_markdown(
            (
                GalleryItem(
                    name="Rattan Lounge Chair",
                    unit_price=85,
                    image_url="https://s3.example/presigned?sig=" + "b" * 200,
                ),
            )
        )
        history = model_history(
            [
                SessionMessage(
                    session_id="s1",
                    timestamp=1,
                    role="user",
                    content="lounge chairs under $100",
                ),
                SessionMessage(
                    session_id="s1",
                    timestamp=2,
                    role="assistant",
                    content=rendered,
                ),
            ],
            strip=strip_gallery,
        )
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1]["content"], narrative)
        self.assertNotIn("presigned", history[1]["content"])
        self.assertNotIn("Matching catalog items", history[1]["content"])

    def test_history_strips_cards_persisted_before_marker(self) -> None:
        from services.chat.gallery import strip_gallery

        legacy = (
            "Here are 2 catalog matches:\n\n---\n\n### Matching catalog items\n\n"
            "**1. Chair** — $85 · qty 24\n\n![Chair](https://s3.example/presigned?sig=c)"
        )
        self.assertEqual(strip_gallery(legacy), "Here are 2 catalog matches:")

    def test_history_is_bounded_by_turns_and_size(self) -> None:
        from services.chat.gallery import strip_gallery
        from services.chat.history import model_history

        messages = [
            SessionMessage(
                session_id="s1",
                timestamp=index,
                role="user" if index % 2 == 0 else "assistant",
                content=f"turn-{index} " + "x" * 4_000,
            )
            for index in range(40)
        ]
        history = model_history(messages, strip=strip_gallery)
        self.assertLessEqual(len(history), 10)
        self.assertTrue(all(len(turn["content"]) <= 1_200 for turn in history))
        self.assertIn("turn-39", history[-1]["content"])


class FallbackTextTests(unittest.TestCase):
    def test_intro_states_applied_constraints_without_model_wording(self) -> None:
        from services.chat.agent import _fallback_intro

        text = _fallback_intro(
            SearchRequest(
                query="gold chairs",
                color="gold",
                max_unit_price=20,
                min_quantity=80,
            ),
            count=1,
        )
        self.assertIn("1 catalog match", text)
        self.assertIn("in gold", text)
        self.assertIn("under $20", text)
        self.assertIn("at least 80", text)
        for leaked in ("model", "tool", "error", "fallback"):
            self.assertNotIn(leaked, text.lower())

    def test_intro_without_constraints_is_plain(self) -> None:
        from services.chat.agent import _fallback_intro

        text = _fallback_intro(SearchRequest(query="chairs"), count=3)
        self.assertEqual(text, "Here are 3 catalog matches:")


class GalleryTests(unittest.TestCase):
    def test_cards_to_gallery_prefers_presigned_image(self) -> None:
        cards = [
            {
                "name": "Gold Chiavari",
                "vendor": "acme",
                "unit_price": 12.5,
                "quantity": 40,
                "product_url": "https://example.com/chair",
                "image_urls": ["https://cdn.example/chair.jpg"],
                "tags": ["chair", "gold"],
                "colors": ["gold"],
                "dimensions_text": '36"H x 16"W',
                "description": "Classic gold chiavari banquet chair. " + "x" * 400,
            },
            {"name": "No Media Chair", "vendor": "acme"},
        ]
        gallery = cards_to_gallery(cards)
        self.assertEqual(len(gallery), 2)
        self.assertEqual(gallery[0].name, "Gold Chiavari")
        self.assertEqual(gallery[0].image_url, "https://cdn.example/chair.jpg")
        self.assertEqual(gallery[0].product_url, "https://example.com/chair")
        self.assertLessEqual(len(gallery[0].description or ""), 160)
        md = gallery_markdown(gallery)
        self.assertIn("Open image", md)
        self.assertIn("Product page", md)
        self.assertIn("No Media Chair", md)

    def test_card_markdown_shows_structured_attributes(self) -> None:
        gallery = cards_to_gallery(
            [
                {
                    "name": "Rattan Lounge Chair",
                    "vendor": "demo-vendor",
                    "unit_price": 85.0,
                    "quantity": 24,
                    "dimensions_text": '30"H x 28"W',
                    "colors": ["natural"],
                    "tags": ["chair", "rattan"],
                    "image_urls": ["https://cdn.example/rattan.png"],
                }
            ]
        )
        md = gallery_markdown(gallery)
        self.assertIn("**1. Rattan Lounge Chair**", md)
        self.assertIn("$85 · qty 24", md)
        self.assertIn("**Vendor:** demo-vendor", md)
        self.assertIn("**Dimensions:**", md)
        self.assertIn("![Rattan Lounge Chair](https://cdn.example/rattan.png)", md)

    def test_missing_price_and_quantity_are_stated(self) -> None:
        gallery = cards_to_gallery([{"name": "Mystery Chair"}])
        md = gallery_markdown(gallery)
        self.assertIn("price not in catalog", md)
        self.assertIn("qty unknown", md)


class DurableSessionIdTests(unittest.TestCase):
    def test_uses_cognito_sub_when_present(self) -> None:
        from types import SimpleNamespace

        from services.chat.session_id import durable_session_id

        user = SimpleNamespace(metadata={"sub": "1468a478-0099-4abc-def0-1234567890ab"})
        self.assertEqual(
            durable_session_id(user),
            "user:1468a478-0099-4abc-def0-1234567890ab",
        )

    def test_same_user_always_gets_same_legacy_session(self) -> None:
        from types import SimpleNamespace

        from services.chat.session_id import durable_session_id

        user = SimpleNamespace(metadata={"sub": "abc-123"})
        self.assertEqual(durable_session_id(user), durable_session_id(user))

    def test_new_session_is_user_scoped_and_unique(self) -> None:
        from services.chat.session_id import new_session_id

        first = new_session_id("abc-123")
        second = new_session_id("abc-123")
        self.assertTrue(first.startswith("user:abc-123:"))
        self.assertTrue(second.startswith("user:abc-123:"))
        self.assertNotEqual(first, second)

    def test_anonymous_falls_back_to_uuid(self) -> None:
        from services.chat.session_id import durable_session_id, new_session_id

        first = durable_session_id(None)
        second = new_session_id(None)
        self.assertNotEqual(first, second)
        self.assertFalse(first.startswith("user:"))


class SessionSummaryTests(unittest.TestCase):
    def test_preview_text_trims(self) -> None:
        from services.chat.sessions import _preview_text

        self.assertEqual(_preview_text("  hello   world  "), "hello world")
        long = "x" * 100
        preview = _preview_text(long, limit=20)
        self.assertEqual(len(preview), 20)
        self.assertTrue(preview.endswith("…"))


class SessionRecordTests(unittest.TestCase):
    def test_round_trip_item_shape(self) -> None:
        message = SessionMessage(
            session_id="s1",
            timestamp=1_700_000_000_000,
            role="user",
            content="need lounge seating",
            user_sub="sub-1",
            expires_at=1_700_000_000 + 30 * 86400,
            metadata={"source": "chainlit"},
        )
        item = message.to_item()
        self.assertEqual(item["session_id"], "s1")
        self.assertEqual(item["timestamp"], 1_700_000_000_000)
        self.assertIn("expires_at", item)
        restored = SessionMessage.from_item(item)
        self.assertEqual(restored.content, "need lounge seating")
        self.assertEqual(restored.role, "user")


if __name__ == "__main__":
    unittest.main()
