from __future__ import annotations

import unittest
from unittest.mock import patch

from shared.providers.groq import (
    GroqKeyPool,
    _cooldown_seconds,
    _normalize_keys,
    load_groq_api_keys,
)


class GroqKeyLoadingTests(unittest.TestCase):
    def test_normalize_comma_and_json(self) -> None:
        self.assertEqual(_normalize_keys("a, b ,c"), ["a", "b", "c"])
        self.assertEqual(_normalize_keys('["x","y"]'), ["x", "y"])

    def test_loads_numbered_env_keys(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "GROQ_API_KEY": "primary-key-aaaa",
                "GROQ_API_KEY_2": "backup-key-bbbb",
                "GROQ_API_KEY_3": "",
            },
            clear=False,
        ):
            # Avoid Secrets Manager lookups during unit tests.
            with patch.dict("os.environ", {"PROVIDER_SECRETS_ARN": ""}, clear=False):
                keys = load_groq_api_keys()
        self.assertEqual(keys[:2], ["primary-key-aaaa", "backup-key-bbbb"])


class GroqRotationTests(unittest.TestCase):
    def test_cooldown_parses_provider_message(self) -> None:
        seconds = _cooldown_seconds(
            'Please try again in 12m30.5s. Need more tokens? Upgrade...'
        )
        self.assertAlmostEqual(seconds, 12 * 60 + 30.5, places=1)

    def test_rotates_to_second_key_on_429(self) -> None:
        pool = GroqKeyPool.from_env(explicit=["key-one-1111", "key-two-2222"])
        calls: list[str] = []

        def fake_post(url, *, headers, body, timeout_seconds, retry_statuses, max_attempts):
            del url, body, timeout_seconds, retry_statuses, max_attempts
            auth = headers["Authorization"]
            calls.append(auth)
            if "key-one-1111" in auth:
                raise RuntimeError(
                    "HTTP 429 from https://api.groq.com/openai/v1/chat/completions: "
                    '{"error":{"message":"Rate limit reached. Please try again in 5m0s."}}'
                )
            return {"choices": [{"message": {"content": "ok"}}]}

        with patch("shared.providers.groq.post_json", side_effect=fake_post):
            payload = pool.post_chat(body={"model": "x", "messages": []})

        self.assertEqual(payload["choices"][0]["message"]["content"], "ok")
        self.assertEqual(len(calls), 2)
        self.assertIn("key-one-1111", calls[0])
        self.assertIn("key-two-2222", calls[1])
        self.assertEqual(pool.available_count(), 1)

    def test_raises_when_all_keys_rate_limited(self) -> None:
        pool = GroqKeyPool.from_env(explicit=["key-one-1111", "key-two-2222"])

        def always_429(*_args, **_kwargs):
            raise RuntimeError(
                "HTTP 429 from https://api.groq.com: "
                "Please try again in 2m0s."
            )

        with patch("shared.providers.groq.post_json", side_effect=always_429):
            with self.assertRaises(RuntimeError) as ctx:
                pool.post_chat(body={"model": "x", "messages": []})
        self.assertIn("every configured key", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
