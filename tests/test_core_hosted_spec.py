import unittest

from pycodex.core import (
    WEB_SEARCH_TEXT_AND_IMAGE_CONTENT_TYPES,
    FreeformToolFormat,
    ToolSpec,
    WebSearchToolOptions,
    create_image_generation_tool,
    create_web_search_tool,
)
from pycodex.protocol import (
    WebSearchConfig,
    WebSearchContextSize,
    WebSearchFilters,
    WebSearchMode,
    WebSearchToolType,
    WebSearchUserLocation,
    WebSearchUserLocationType,
)


class HostedSpecTests(unittest.TestCase):
    def test_freeform_tool_serializes_as_custom_tool(self) -> None:
        tool = ToolSpec.freeform(
            name="exec",
            description="Run a command",
            format=FreeformToolFormat.grammar(
                syntax="lark",
                definition='start: "exec"',
            ),
        )

        self.assertEqual(
            tool.to_mapping(),
            {
                "type": "custom",
                "name": "exec",
                "description": "Run a command",
                "format": {
                    "type": "grammar",
                    "syntax": "lark",
                    "definition": 'start: "exec"',
                },
            },
        )

    def test_image_generation_tool_matches_expected_spec(self) -> None:
        self.assertEqual(
            create_image_generation_tool("png"),
            ToolSpec.image_generation("png"),
        )
        self.assertEqual(
            create_image_generation_tool("png").to_mapping(),
            {"type": "image_generation", "output_format": "png"},
        )

    def test_web_search_tool_preserves_configured_options(self) -> None:
        tool = create_web_search_tool(
            WebSearchToolOptions(
                web_search_mode=WebSearchMode.LIVE,
                web_search_config=WebSearchConfig(
                    filters=WebSearchFilters(("example.com",)),
                    user_location=WebSearchUserLocation(
                        type=WebSearchUserLocationType.APPROXIMATE,
                        country="US",
                        timezone="America/Los_Angeles",
                    ),
                    search_context_size=WebSearchContextSize.LOW,
                ),
                web_search_tool_type=WebSearchToolType.TEXT_AND_IMAGE,
            )
        )

        self.assertEqual(
            tool,
            ToolSpec.web_search(
                external_web_access=True,
                filters=WebSearchFilters(("example.com",)),
                user_location=WebSearchUserLocation(
                    type=WebSearchUserLocationType.APPROXIMATE,
                    country="US",
                    timezone="America/Los_Angeles",
                ),
                search_context_size=WebSearchContextSize.LOW,
                search_content_types=WEB_SEARCH_TEXT_AND_IMAGE_CONTENT_TYPES,
            ),
        )
        self.assertEqual(
            tool.to_mapping(),
            {
                "type": "web_search",
                "external_web_access": True,
                "filters": {"allowed_domains": ["example.com"]},
                "user_location": {
                    "type": "approximate",
                    "country": "US",
                    "region": None,
                    "city": None,
                    "timezone": "America/Los_Angeles",
                },
                "search_context_size": "low",
                "search_content_types": ["text", "image"],
            },
        )

    def test_web_search_tool_uses_cached_mode_without_external_web_access(self) -> None:
        tool = create_web_search_tool(
            WebSearchToolOptions(
                web_search_mode=WebSearchMode.CACHED,
                web_search_config=None,
                web_search_tool_type=WebSearchToolType.TEXT,
            )
        )

        self.assertEqual(
            tool,
            ToolSpec.web_search(external_web_access=False),
        )
        self.assertEqual(
            tool.to_mapping(),
            {"type": "web_search", "external_web_access": False},
        )

    def test_web_search_tool_is_absent_when_disabled_or_missing(self) -> None:
        self.assertIsNone(
            create_web_search_tool(
                WebSearchToolOptions(
                    web_search_mode=WebSearchMode.DISABLED,
                    web_search_config=None,
                    web_search_tool_type=WebSearchToolType.TEXT,
                )
            )
        )
        self.assertIsNone(
            create_web_search_tool(
                WebSearchToolOptions(
                    web_search_mode=None,
                    web_search_config=None,
                    web_search_tool_type=WebSearchToolType.TEXT,
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
