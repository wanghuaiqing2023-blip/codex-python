from __future__ import annotations

import unittest

from pycodex.protocol import (
    DEFAULT_IMAGE_DETAIL,
    FunctionCallOutputContentItem,
    TruncationPolicyConfig,
)
from pycodex.utils.output_truncation import (
    approx_token_count,
    approx_tokens_from_byte_count_i64,
    formatted_truncate_text,
    formatted_truncate_text_content_items_with_policy,
    truncate_function_output_items_with_policy,
    truncate_text,
)


class OutputTruncationTests(unittest.TestCase):
    def test_formatted_truncate_text_bytes_and_tokens_match_rust_policy(self) -> None:
        # Source: codex/codex-rs/utils/output-truncation/src/truncate_tests.rs
        # Rust tests: truncate_bytes_less_than_placeholder_returns_placeholder,
        # truncate_tokens_less_than_placeholder_returns_placeholder.
        self.assertEqual(
            formatted_truncate_text("example output", TruncationPolicyConfig.bytes(1)),
            "Total output lines: 1\n\n\u202613 chars truncated\u2026t",
        )
        self.assertEqual(
            formatted_truncate_text("example output", TruncationPolicyConfig.tokens(1)),
            "Total output lines: 1\n\nex\u20263 tokens truncated\u2026ut",
        )

    def test_formatted_truncate_text_returns_original_under_limit(self) -> None:
        # Source: codex/codex-rs/utils/output-truncation/src/truncate_tests.rs
        # Rust tests: truncate_tokens_under_limit_returns_original,
        # truncate_bytes_under_limit_returns_original.
        content = "example output"

        self.assertEqual(formatted_truncate_text(content, TruncationPolicyConfig.tokens(10)), content)
        self.assertEqual(formatted_truncate_text(content, TruncationPolicyConfig.bytes(20)), content)

    def test_formatted_truncate_text_reports_original_line_count_when_truncated(self) -> None:
        # Source: codex/codex-rs/utils/output-truncation/src/truncate_tests.rs
        # Rust tests: truncate_bytes_reports_original_line_count_when_truncated,
        # truncate_tokens_reports_original_line_count_when_truncated.
        content = "this is an example of a long output that should be truncated\nalso some other line"

        self.assertTrue(
            formatted_truncate_text(content, TruncationPolicyConfig.bytes(30)).startswith(
                "Total output lines: 2\n\n"
            )
        )
        self.assertTrue(
            formatted_truncate_text(content, TruncationPolicyConfig.tokens(10)).startswith(
                "Total output lines: 2\n\n"
            )
        )

    def test_truncate_middle_bytes_handles_utf8_content(self) -> None:
        # Source: codex/codex-rs/utils/output-truncation/src/truncate_tests.rs
        # Rust test: truncate_middle_bytes_handles_utf8_content
        content = "\U0001f600" * 10 + "\nsecond line with text\n"

        self.assertEqual(
            truncate_text(content, TruncationPolicyConfig.bytes(20)),
            "\U0001f600\U0001f600\u202621 chars truncated\u2026with text\n",
        )

    def test_truncates_across_multiple_texts_and_reports_omitted(self) -> None:
        # Source: codex/codex-rs/utils/output-truncation/src/truncate_tests.rs
        # Rust test: truncates_across_multiple_under_limit_texts_and_reports_omitted
        chunk = (
            "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda "
            "mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega.\n"
        )
        limit = approx_token_count(chunk) * 3
        image = FunctionCallOutputContentItem.input_image("img:mid", DEFAULT_IMAGE_DETAIL)
        items = (
            FunctionCallOutputContentItem.input_text(chunk),
            FunctionCallOutputContentItem.input_text(chunk),
            image,
            FunctionCallOutputContentItem.input_text(chunk * 10),
            FunctionCallOutputContentItem.input_text(chunk),
            FunctionCallOutputContentItem.input_text(chunk),
        )

        output = truncate_function_output_items_with_policy(items, TruncationPolicyConfig.tokens(limit))

        self.assertEqual(output[0], items[0])
        self.assertEqual(output[1], items[1])
        self.assertEqual(output[2], image)
        self.assertIn("tokens truncated", output[3].text or "")
        self.assertEqual(output[4], FunctionCallOutputContentItem.input_text("[omitted 2 text items ...]"))

    def test_formatted_content_items_merge_text_and_append_media(self) -> None:
        # Source: codex/codex-rs/utils/output-truncation/src/truncate_tests.rs
        # Rust test: formatted_truncate_text_content_items_with_policy_merges_text_and_appends_images
        image_one = FunctionCallOutputContentItem.input_image("img:one", DEFAULT_IMAGE_DETAIL)
        image_two = FunctionCallOutputContentItem.input_image("img:two", DEFAULT_IMAGE_DETAIL)
        items = (
            FunctionCallOutputContentItem.input_text("abcd"),
            image_one,
            FunctionCallOutputContentItem.input_text("efgh"),
            FunctionCallOutputContentItem.input_text("ijkl"),
            image_two,
        )

        output, original_token_count = formatted_truncate_text_content_items_with_policy(
            items,
            TruncationPolicyConfig.bytes(8),
        )

        self.assertEqual(
            output,
            (
                FunctionCallOutputContentItem.input_text("Total output lines: 3\n\nabcd\u20266 chars truncated\u2026ijkl"),
                image_one,
                image_two,
            ),
        )
        self.assertEqual(original_token_count, 4)

    def test_formatted_content_items_returns_original_under_limit_and_no_text_items(self) -> None:
        # Source: codex/codex-rs/utils/output-truncation/src/lib.rs
        # Contract: no text or under-budget combined text returns original items and no token count.
        image = FunctionCallOutputContentItem.input_image("img:one", DEFAULT_IMAGE_DETAIL)
        text_items = (
            FunctionCallOutputContentItem.input_text("alpha"),
            FunctionCallOutputContentItem.input_text(""),
            FunctionCallOutputContentItem.input_text("beta"),
        )

        self.assertEqual(
            formatted_truncate_text_content_items_with_policy((image,), TruncationPolicyConfig.bytes(0)),
            ((image,), None),
        )
        self.assertEqual(
            formatted_truncate_text_content_items_with_policy(text_items, TruncationPolicyConfig.bytes(32)),
            (text_items, None),
        )

    def test_content_item_truncation_preserves_encrypted_content(self) -> None:
        # Source: codex/codex-rs/utils/output-truncation/src/truncate_tests.rs
        # Rust tests: formatted_truncate_text_content_items_with_policy_preserves_encrypted_content,
        # truncate_function_output_items_with_policy_preserves_encrypted_content.
        encrypted = FunctionCallOutputContentItem.encrypted("enc_opaque")
        items = (FunctionCallOutputContentItem.input_text("abcdefgh"), encrypted)

        formatted, original_token_count = formatted_truncate_text_content_items_with_policy(
            items,
            TruncationPolicyConfig.bytes(2),
        )
        truncated = truncate_function_output_items_with_policy(items, TruncationPolicyConfig.bytes(2))

        self.assertEqual(
            formatted,
            (
                FunctionCallOutputContentItem.input_text("Total output lines: 1\n\na\u20266 chars truncated\u2026h"),
                encrypted,
            ),
        )
        self.assertEqual(original_token_count, 2)
        self.assertEqual(
            truncated,
            (
                FunctionCallOutputContentItem.input_text("a\u20266 chars truncated\u2026h"),
                encrypted,
            ),
        )

    def test_formatted_content_items_merges_all_text_for_token_budget(self) -> None:
        # Source: codex/codex-rs/utils/output-truncation/src/truncate_tests.rs
        # Rust test: formatted_truncate_text_content_items_with_policy_merges_all_text_for_token_budget
        items = (
            FunctionCallOutputContentItem.input_text("abcdefgh"),
            FunctionCallOutputContentItem.input_text("ijklmnop"),
        )

        output, original_token_count = formatted_truncate_text_content_items_with_policy(
            items,
            TruncationPolicyConfig.tokens(2),
        )

        self.assertEqual(
            output,
            (FunctionCallOutputContentItem.input_text("Total output lines: 2\n\nabcd\u20263 tokens truncated\u2026mnop"),),
        )
        self.assertEqual(original_token_count, 5)

    def test_approx_tokens_from_byte_count_i64_clamps_non_positive_values(self) -> None:
        # Source: codex/codex-rs/utils/output-truncation/src/truncate_tests.rs
        # Rust test: byte_count_conversion_clamps_non_positive_values
        self.assertEqual(approx_tokens_from_byte_count_i64(-1), 0)
        self.assertEqual(approx_tokens_from_byte_count_i64(0), 0)
        self.assertEqual(approx_tokens_from_byte_count_i64(5), 2)


if __name__ == "__main__":
    unittest.main()
