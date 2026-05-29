import unittest

from pycodex.core import PLUGIN_TEXT_MENTION_SIGIL, TOOL_MENTION_SIGIL


class MentionSyntaxTests(unittest.TestCase):
    def test_sigil_constants_match_upstream_plugin_utils(self) -> None:
        self.assertEqual(TOOL_MENTION_SIGIL, "$")
        self.assertEqual(PLUGIN_TEXT_MENTION_SIGIL, "@")

    def test_sigil_constants_are_single_characters(self) -> None:
        self.assertEqual(len(TOOL_MENTION_SIGIL), 1)
        self.assertEqual(len(PLUGIN_TEXT_MENTION_SIGIL), 1)


if __name__ == "__main__":
    unittest.main()
