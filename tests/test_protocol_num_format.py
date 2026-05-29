import unittest

from pycodex.protocol import format_si_suffix, format_with_separators


class ProtocolNumFormatTests(unittest.TestCase):
    def test_format_si_suffix_matches_upstream_en_us_examples(self):
        cases = {
            0: "0",
            999: "999",
            1_000: "1.00K",
            1_200: "1.20K",
            10_000: "10.0K",
            100_000: "100K",
            999_500: "1.00M",
            1_000_000: "1.00M",
            1_234_000: "1.23M",
            12_345_678: "12.3M",
            999_950_000: "1.00G",
            1_000_000_000: "1.00G",
            1_234_000_000: "1.23G",
            1_234_000_000_000: "1,234G",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(format_si_suffix(value), expected)

    def test_negative_si_values_clamp_to_zero_like_upstream(self):
        self.assertEqual(format_si_suffix(-1), "0")

    def test_format_with_separators_accepts_i64_range(self):
        self.assertEqual(format_with_separators(-1_234_567), "-1,234,567")
        self.assertEqual(format_with_separators(9_223_372_036_854_775_807), "9,223,372,036,854,775,807")

    def test_num_format_rejects_non_i64_inputs(self):
        with self.assertRaisesRegex(TypeError, "value must be an integer"):
            format_with_separators(True)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "value must be an integer"):
            format_si_suffix(1.2)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "value must fit in i64"):
            format_with_separators(2**63)
        with self.assertRaisesRegex(ValueError, "value must fit in i64"):
            format_si_suffix(-(2**63) - 1)


if __name__ == "__main__":
    unittest.main()
