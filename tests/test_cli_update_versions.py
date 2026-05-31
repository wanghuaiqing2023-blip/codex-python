import unittest

from pycodex.cli import extract_version_from_latest_tag, is_newer, is_source_build_version, parse_version


class UpdateVersionTests(unittest.TestCase):
    def test_extracts_version_from_latest_tag(self) -> None:
        self.assertEqual(extract_version_from_latest_tag("rust-v1.5.0"), "1.5.0")

    def test_latest_tag_without_prefix_is_invalid(self) -> None:
        with self.assertRaisesRegex(ValueError, "Failed to parse latest tag name 'v1.5.0'"):
            extract_version_from_latest_tag("v1.5.0")

    def test_prerelease_version_is_not_considered_newer(self) -> None:
        self.assertIsNone(is_newer("0.11.0-beta.1", "0.11.0"))
        self.assertIsNone(is_newer("1.0.0-rc.1", "1.0.0"))

    def test_plain_semver_comparisons_work(self) -> None:
        self.assertIs(is_newer("0.11.1", "0.11.0"), True)
        self.assertIs(is_newer("0.11.0", "0.11.1"), False)
        self.assertIs(is_newer("1.0.0", "0.9.9"), True)
        self.assertIs(is_newer("0.9.9", "1.0.0"), False)

    def test_source_build_version_is_not_checked(self) -> None:
        self.assertTrue(is_source_build_version("0.0.0"))
        self.assertFalse(is_source_build_version("0.1.0"))

    def test_whitespace_is_ignored(self) -> None:
        self.assertEqual(parse_version(" 1.2.3 \n"), (1, 2, 3))
        self.assertIs(is_newer(" 1.2.3 ", "1.2.2"), True)

    def test_parse_version_matches_rust_u64_components(self) -> None:
        self.assertEqual(parse_version("1.2.3.4"), (1, 2, 3))
        self.assertIsNone(parse_version("-1.2.3"))
        self.assertIsNone(parse_version("+1.2.3"))
        self.assertIsNone(parse_version("1. 2.3"))
        self.assertIsNone(parse_version("18446744073709551616.0.0"))


if __name__ == "__main__":
    unittest.main()
