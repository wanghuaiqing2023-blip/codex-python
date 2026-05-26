import unittest

from pycodex.core import (
    PLUGIN_TEXT_MENTION_SIGIL,
    TOOL_MENTION_SIGIL,
    web_search_action_detail,
    web_search_detail,
)
from pycodex.protocol import WebSearchAction


class WebSearchTests(unittest.TestCase):
    def test_search_action_prefers_non_empty_query(self) -> None:
        self.assertEqual(
            web_search_action_detail(
                WebSearchAction.search(query="weather", queries=("ignored", "other"))
            ),
            "weather",
        )

    def test_search_action_uses_first_multi_query_with_ellipsis(self) -> None:
        self.assertEqual(
            web_search_action_detail(
                WebSearchAction.search(query="", queries=("first", "second"))
            ),
            "first ...",
        )

    def test_search_action_uses_first_query_without_ellipsis_for_single_or_empty_first(self) -> None:
        self.assertEqual(
            web_search_action_detail(WebSearchAction.search(queries=("only",))),
            "only",
        )
        self.assertEqual(
            web_search_action_detail(WebSearchAction.search(queries=("", "second"))),
            "",
        )
        self.assertEqual(web_search_action_detail(WebSearchAction.search()), "")

    def test_open_page_action_detail(self) -> None:
        self.assertEqual(
            web_search_action_detail(WebSearchAction.open_page("https://example.com")),
            "https://example.com",
        )
        self.assertEqual(web_search_action_detail(WebSearchAction.open_page()), "")

    def test_find_in_page_action_detail(self) -> None:
        self.assertEqual(
            web_search_action_detail(
                WebSearchAction.find_in_page("https://example.com", "needle")
            ),
            "'needle' in https://example.com",
        )
        self.assertEqual(
            web_search_action_detail(WebSearchAction.find_in_page(pattern="needle")),
            "'needle'",
        )
        self.assertEqual(
            web_search_action_detail(WebSearchAction.find_in_page(url="https://example.com")),
            "https://example.com",
        )
        self.assertEqual(web_search_action_detail(WebSearchAction.find_in_page()), "")

    def test_other_action_detail_and_query_fallback(self) -> None:
        self.assertEqual(web_search_action_detail(WebSearchAction.other()), "")
        self.assertEqual(web_search_detail(WebSearchAction.other(), "fallback"), "fallback")
        self.assertEqual(web_search_detail(None, "fallback"), "fallback")
        self.assertEqual(
            web_search_detail(WebSearchAction.search(query="actual"), "fallback"),
            "actual",
        )

    def test_mention_syntax_constants(self) -> None:
        self.assertEqual(TOOL_MENTION_SIGIL, "$")
        self.assertEqual(PLUGIN_TEXT_MENTION_SIGIL, "@")


if __name__ == "__main__":
    unittest.main()
