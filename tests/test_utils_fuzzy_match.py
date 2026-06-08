from __future__ import annotations

import unittest

from pycodex.utils.fuzzy_match import I32_MAX, fuzzy_match


class FuzzyMatchTests(unittest.TestCase):
    def test_ascii_basic_indices(self) -> None:
        # Source: codex/codex-rs/utils/fuzzy-match/src/lib.rs
        # Rust crate: codex-utils-fuzzy-match
        # Rust test: tests::ascii_basic_indices
        # Contract: returns original character indices and lower-is-better score.
        result = fuzzy_match("hello", "hl")

        self.assertEqual(result, ([0, 2], -99))

    def test_unicode_dotted_i_istanbul_highlighting(self) -> None:
        # Source: codex/codex-rs/utils/fuzzy-match/src/lib.rs
        # Rust test: tests::unicode_dotted_i_istanbul_highlighting
        result = fuzzy_match("İstanbul", "is")

        self.assertEqual(result, ([0, 1], -99))

    def test_unicode_german_sharp_s_casefold(self) -> None:
        # Source: codex/codex-rs/utils/fuzzy-match/src/lib.rs
        # Rust test: tests::unicode_german_sharp_s_casefold
        # Contract: Rust lowercasing is not full Unicode casefolding, so ß does not become ss.
        self.assertIsNone(fuzzy_match("straße", "strasse"))

    def test_prefer_contiguous_match_over_spread(self) -> None:
        # Source: codex/codex-rs/utils/fuzzy-match/src/lib.rs
        # Rust test: tests::prefer_contiguous_match_over_spread
        result_a = fuzzy_match("abc", "abc")
        result_b = fuzzy_match("a-b-c", "abc")

        self.assertEqual(result_a, ([0, 1, 2], -100))
        self.assertEqual(result_b, ([0, 2, 4], -98))
        self.assertLess(result_a[1], result_b[1])  # type: ignore[index]

    def test_start_of_string_bonus_applies(self) -> None:
        # Source: codex/codex-rs/utils/fuzzy-match/src/lib.rs
        # Rust test: tests::start_of_string_bonus_applies
        result_a = fuzzy_match("file_name", "file")
        result_b = fuzzy_match("my_file_name", "file")

        self.assertEqual(result_a, ([0, 1, 2, 3], -100))
        self.assertEqual(result_b, ([3, 4, 5, 6], 0))
        self.assertLess(result_a[1], result_b[1])  # type: ignore[index]

    def test_empty_needle_matches_with_max_score_and_no_indices(self) -> None:
        # Source: codex/codex-rs/utils/fuzzy-match/src/lib.rs
        # Rust test: tests::empty_needle_matches_with_max_score_and_no_indices
        self.assertEqual(fuzzy_match("anything", ""), ([], I32_MAX))

    def test_case_insensitive_matching_basic(self) -> None:
        # Source: codex/codex-rs/utils/fuzzy-match/src/lib.rs
        # Rust test: tests::case_insensitive_matching_basic
        self.assertEqual(fuzzy_match("FooBar", "foO"), ([0, 1, 2], -100))

    def test_indices_are_deduped_for_multichar_lowercase_expansion(self) -> None:
        # Source: codex/codex-rs/utils/fuzzy-match/src/lib.rs
        # Rust test: tests::indices_are_deduped_for_multichar_lowercase_expansion
        needle = "\u0069\u0307"

        self.assertEqual(fuzzy_match("İ", needle), ([0], -100))

    def test_missing_subsequence_returns_none(self) -> None:
        # Source: codex/codex-rs/utils/fuzzy-match/src/lib.rs
        # Contract: every lowered needle char must be found in order.
        self.assertIsNone(fuzzy_match("abc", "acb"))

    def test_rejects_non_string_inputs(self) -> None:
        with self.assertRaisesRegex(TypeError, "haystack must be a string"):
            fuzzy_match(123, "a")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "needle must be a string"):
            fuzzy_match("abc", None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
