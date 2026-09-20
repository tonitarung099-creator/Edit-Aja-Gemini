import io
import json
import unittest

from tools.gemini_provider.gemini_provider import (
    MAX_API_KEYS,
    GeminiCredential,
    GeminiKeyPool,
    GeminiRestClient,
    NoUsableCredential,
    mask_api_key,
    parse_generate_models,
)


class FakeResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._data


class GeminiProviderTests(unittest.TestCase):
    def test_maximum_unique_api_keys_is_100(self):
        pool = GeminiKeyPool.from_api_keys(
            [f"key-{index:03d}" for index in range(MAX_API_KEYS)]
        )
        self.assertEqual(len(pool), MAX_API_KEYS)

        with self.assertRaises(ValueError):
            GeminiKeyPool.from_api_keys(
                [f"key-{index:03d}" for index in range(MAX_API_KEYS + 1)]
            )

    def test_duplicate_keys_are_deduplicated(self):
        pool = GeminiKeyPool.from_api_keys(["same-key", "same-key", "other-key"])
        self.assertEqual(len(pool), 2)

    def test_key_masking_never_returns_full_secret(self):
        key = "abcd-1234567890-wxyz"
        masked = mask_api_key(key)
        self.assertNotEqual(masked, key)
        self.assertTrue(masked.startswith("abcd"))
        self.assertTrue(masked.endswith("wxyz"))

    def test_429_cools_every_key_in_same_project_scope(self):
        pool = GeminiKeyPool(
            [
                GeminiCredential("key-a", project_id="project-one"),
                GeminiCredential("key-b", project_id="project-one"),
                GeminiCredential("key-c", project_id="project-two"),
            ],
            clock=lambda: 100.0,
        )

        pool.record_failure(
            "key-a",
            status_code=429,
            retry_after_seconds=30,
            now=100.0,
        )

        snapshot = pool.snapshot(now=100.0)
        self.assertEqual(snapshot[0]["status"], "cooldown")
        self.assertEqual(snapshot[1]["status"], "cooldown")
        self.assertEqual(snapshot[2]["status"], "ready")
        self.assertEqual(pool.acquire(now=100.0).api_key, "key-c")

    def test_unknown_projects_share_conservative_quota_scope(self):
        pool = GeminiKeyPool.from_api_keys(["key-a", "key-b"], clock=lambda: 50.0)
        pool.record_failure("key-a", status_code=429, now=50.0)

        with self.assertRaises(NoUsableCredential):
            pool.acquire(now=50.0)

    def test_auth_failure_invalidates_only_failed_key(self):
        pool = GeminiKeyPool.from_api_keys(["key-a", "key-b"], clock=lambda: 1.0)
        pool.record_failure("key-a", status_code=401, now=1.0)
        self.assertEqual(pool.acquire(now=1.0).api_key, "key-b")

    def test_request_shape_400_does_not_rotate_key(self):
        pool = GeminiKeyPool.from_api_keys(["key-a"], clock=lambda: 1.0)
        pool.record_failure("key-a", status_code=400, now=1.0)
        self.assertEqual(pool.acquire(now=1.0).api_key, "key-a")

    def test_parse_generate_models_accepts_rest_field(self):
        models = parse_generate_models(
            {
                "models": [
                    {
                        "name": "models/gemini-example",
                        "displayName": "Gemini Example",
                        "supportedGenerationMethods": ["generateContent"],
                        "thinking": True,
                    },
                    {
                        "name": "models/embed-example",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            }
        )
        self.assertEqual([item["id"] for item in models], ["gemini-example"])

    def test_parse_generate_models_accepts_sdk_style_field(self):
        models = parse_generate_models(
            {
                "models": [
                    {
                        "name": "models/gemini-forward-compatible",
                        "supportedActions": ["generateContent"],
                    }
                ]
            }
        )
        self.assertEqual(
            [item["id"] for item in models],
            ["gemini-forward-compatible"],
        )

    def test_rest_client_uses_header_and_paginates(self):
        calls = []
        payloads = [
            {
                "models": [
                    {
                        "name": "models/gemini-a",
                        "supportedGenerationMethods": ["generateContent"],
                    }
                ],
                "nextPageToken": "next-token",
            },
            {
                "models": [
                    {
                        "name": "models/gemini-b",
                        "supportedGenerationMethods": ["generateContent"],
                    }
                ]
            },
        ]

        def opener(request, timeout):
            calls.append((request, timeout))
            return FakeResponse(payloads[len(calls) - 1])

        client = GeminiRestClient(opener=opener)
        models = client.list_models("super-secret-key")

        self.assertEqual([item["id"] for item in models], ["gemini-a", "gemini-b"])
        self.assertEqual(len(calls), 2)

        first_request = calls[0][0]
        self.assertNotIn("super-secret-key", first_request.full_url)
        header_map = {key.lower(): value for key, value in first_request.header_items()}
        self.assertEqual(header_map["x-goog-api-key"], "super-secret-key")
        self.assertIn("pageSize=1000", first_request.full_url)

        second_request = calls[1][0]
        self.assertIn("pageToken=next-token", second_request.full_url)


if __name__ == "__main__":
    unittest.main()
