import json
import unittest

from pycodex.core import (
    approx_bytes_for_tokens,
    approx_token_count,
    approx_tokens_from_byte_count,
    find_uuids,
    normalize_markdown_hash_location_suffix,
    take_bytes_at_char_boundary,
    to_ascii_json_string,
    truncate_middle_chars,
    truncate_middle_with_token_budget,
)
from pycodex.core.string_utils import (
    _split_string,
    sanitize_metric_tag_value,
    truncate_to_char_boundary,
)


class CoreStringUtilsTests(unittest.TestCase):
    def test_take_bytes_at_char_boundary_keeps_valid_utf8_prefix(self) -> None:
        self.assertEqual(take_bytes_at_char_boundary("abc", 8), "abc")
        self.assertEqual(take_bytes_at_char_boundary("\U0001f600abc\U0001f600", 5), "\U0001f600a")
        self.assertEqual(take_bytes_at_char_boundary("\U0001f600abc", 3), "")
        self.assertEqual(take_bytes_at_char_boundary("abc", 0), "")

        with self.assertRaisesRegex(TypeError, "value must be a string"):
            take_bytes_at_char_boundary(123, 8)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "max_bytes must be an integer"):
            take_bytes_at_char_boundary("abc", True)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "max_bytes must be non-negative"):
            take_bytes_at_char_boundary("abc", -1)

    def test_approx_token_helpers_use_upstream_four_byte_estimate(self) -> None:
        self.assertEqual(approx_token_count("abcdef"), 2)
        self.assertEqual(approx_token_count("\U0001f600abc"), 2)
        self.assertEqual(approx_bytes_for_tokens(8), 32)
        self.assertEqual(approx_tokens_from_byte_count(9), 3)

        with self.assertRaisesRegex(TypeError, "text must be a string"):
            approx_token_count(123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "tokens must be non-negative"):
            approx_bytes_for_tokens(-1)
        with self.assertRaisesRegex(ValueError, "bytes_count must be non-negative"):
            approx_tokens_from_byte_count(-1)

    def test_split_string_matches_upstream_utf8_boundary_behavior(self) -> None:
        self.assertEqual(_split_string("hello world", 5, 5), (1, "hello", "world"))
        self.assertEqual(_split_string("abc", 0, 0), (3, "", ""))
        self.assertEqual(_split_string("abcdef", 3, 0), (3, "abc", ""))
        self.assertEqual(_split_string("abcdef", 0, 3), (3, "", "def"))
        self.assertEqual(_split_string("abcdef", 4, 4), (0, "abcd", "ef"))
        self.assertEqual(_split_string("\U0001f600abc\U0001f600", 5, 5), (1, "\U0001f600a", "c\U0001f600"))
        self.assertEqual(_split_string("\U0001f600" * 5, 1, 1), (5, "", ""))
        self.assertEqual(_split_string("\U0001f600" * 5, 7, 7), (3, "\U0001f600", "\U0001f600"))
        self.assertEqual(_split_string("\U0001f600" * 5, 8, 8), (1, "\U0001f600\U0001f600", "\U0001f600\U0001f600"))

    def test_truncate_middle_chars_uses_byte_budget_and_char_marker(self) -> None:
        self.assertEqual(truncate_middle_chars("short", 100), "short")
        self.assertEqual(
            truncate_middle_chars("hello world", 10),
            "hello\u20261 chars truncated\u2026world",
        )
        self.assertEqual(
            truncate_middle_chars("\U0001f600" * 5, 8),
            "\U0001f600\u20263 chars truncated\u2026\U0001f600",
        )
        with self.assertRaisesRegex(TypeError, "value must be a string"):
            truncate_middle_chars(123, 10)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "max_bytes must be non-negative"):
            truncate_middle_chars("abcdef", -1)

    def test_truncate_middle_with_token_budget_reports_original_count(self) -> None:
        self.assertEqual(
            truncate_middle_with_token_budget("short output", 100),
            ("short output", None),
        )
        self.assertEqual(
            truncate_middle_with_token_budget("abcdef", 0),
            ("\u20262 tokens truncated\u2026", 2),
        )
        output, original_tokens = truncate_middle_with_token_budget(
            "\U0001f600" * 10 + "\nsecond line with text\n",
            8,
        )
        self.assertIn("tokens truncated", output)
        self.assertEqual(original_tokens, 16)
        with self.assertRaisesRegex(TypeError, "value must be a string"):
            truncate_middle_with_token_budget(123, 1)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "max_tokens must be non-negative"):
            truncate_middle_with_token_budget("abcdef", -1)

    def test_sanitize_metric_tag_value_matches_upstream_examples(self) -> None:
        self.assertEqual(sanitize_metric_tag_value("bad value!"), "bad_value")
        self.assertEqual(sanitize_metric_tag_value("///"), "unspecified")
        self.assertEqual(sanitize_metric_tag_value("___ok/path___"), "ok/path")
        self.assertEqual(sanitize_metric_tag_value("x" * 300), "x" * 256)
        with self.assertRaisesRegex(TypeError, "value must be a string"):
            sanitize_metric_tag_value(123)  # type: ignore[arg-type]

    def test_find_uuids_matches_upstream_regex_behavior(self) -> None:
        self.assertEqual(
            find_uuids(
                "x 00112233-4455-6677-8899-aabbccddeeff-k "
                "y 12345678-90ab-cdef-0123-456789abcdef"
            ),
            [
                "00112233-4455-6677-8899-aabbccddeeff",
                "12345678-90ab-cdef-0123-456789abcdef",
            ],
        )
        self.assertEqual(
            find_uuids("not-a-uuid-1234-5678-9abc-def0-123456789abc"),
            [],
        )
        self.assertEqual(
            find_uuids("\U0001f642 55e5d6f7-8a7f-4d2a-8d88-123456789012abc"),
            ["55e5d6f7-8a7f-4d2a-8d88-123456789012"],
        )
        with self.assertRaisesRegex(TypeError, "value must be a string"):
            find_uuids(123)  # type: ignore[arg-type]

    def test_normalize_markdown_hash_location_suffix_converts_locations(self) -> None:
        self.assertEqual(normalize_markdown_hash_location_suffix("#L74C3"), ":74:3")
        self.assertEqual(
            normalize_markdown_hash_location_suffix("#L74C3-L76C9"),
            ":74:3-76:9",
        )
        self.assertEqual(normalize_markdown_hash_location_suffix("#L74-L76"), ":74-76")
        self.assertIsNone(normalize_markdown_hash_location_suffix("L74C3"))
        self.assertIsNone(normalize_markdown_hash_location_suffix("#74C3"))
        with self.assertRaisesRegex(TypeError, "suffix must be a string"):
            normalize_markdown_hash_location_suffix(123)  # type: ignore[arg-type]

    def test_truncate_to_char_boundary_uses_character_count(self) -> None:
        self.assertEqual(truncate_to_char_boundary("\u00e1" * 4 + "tail", 4), "\u00e1" * 4)
        self.assertEqual(truncate_to_char_boundary("short", 50), "short")
        self.assertEqual(truncate_to_char_boundary("short", 0), "")
        with self.assertRaisesRegex(TypeError, "value must be a string"):
            truncate_to_char_boundary(123, 4)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "max_chars must be non-negative"):
            truncate_to_char_boundary("short", -1)

    def test_to_ascii_json_string_escapes_non_ascii_strings(self) -> None:
        value = {
            "workspaces": {
                "/tmp/\u6771\u4eac": {
                    "label": "Agentlar\u0131m",
                    "emoji": "\U0001f680",
                }
            }
        }

        serialized = to_ascii_json_string(value)

        self.assertEqual(
            serialized,
            (
                r'{"workspaces":{"/tmp/\u6771\u4eac":'
                r'{"label":"Agentlar\u0131m","emoji":"\ud83d\ude80"}}}'
            ),
        )
        self.assertTrue(serialized.isascii())
        self.assertNotIn("\u6771\u4eac", serialized)
        self.assertNotIn("Agentlar\u0131m", serialized)
        self.assertNotIn("\U0001f680", serialized)
        self.assertEqual(json.loads(serialized), value)


if __name__ == "__main__":
    unittest.main()
