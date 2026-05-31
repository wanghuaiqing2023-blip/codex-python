import unittest

from pycodex.protocol import TokenUsage


class TokenUsageDisplayTests(unittest.TestCase):
    def test_formats_zero_usage_like_rust_display(self) -> None:
        self.assertEqual(
            str(TokenUsage()),
            "Token usage: total=0 input=0 output=0",
        )

    def test_formats_blended_total_cached_input_and_reasoning(self) -> None:
        usage = TokenUsage(
            input_tokens=12_345,
            cached_input_tokens=2_000,
            output_tokens=4_321,
            reasoning_output_tokens=321,
            total_tokens=99_999,
        )

        self.assertEqual(
            str(usage),
            "Token usage: total=14,666 input=10,345 (+ 2,000 cached) output=4,321 (reasoning 321)",
        )

    def test_clamps_negative_blended_inputs_like_rust_display(self) -> None:
        usage = TokenUsage(
            input_tokens=10,
            cached_input_tokens=40,
            output_tokens=-5,
            reasoning_output_tokens=-1,
            total_tokens=10,
        )

        self.assertEqual(
            str(usage),
            "Token usage: total=0 input=0 (+ 40 cached) output=-5",
        )


if __name__ == "__main__":
    unittest.main()
