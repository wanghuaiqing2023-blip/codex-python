from pycodex.core.tools.handlers import tool_search_spec as facade
from pycodex.core.tools.handlers.tool_search import (
    TOOL_SEARCH_DEFAULT_LIMIT,
    TOOL_SEARCH_TOOL_NAME,
    create_tool_search_tool,
)
from pycodex.tools.tool_discovery import ToolSearchSourceInfo


def test_facade_exports_rust_coordinate_tool_search_spec_surface():
    # Rust source: codex-rs/core/src/tools/handlers/tool_search_spec.rs.
    assert facade.TOOL_SEARCH_DEFAULT_LIMIT == TOOL_SEARCH_DEFAULT_LIMIT
    assert facade.TOOL_SEARCH_TOOL_NAME == TOOL_SEARCH_TOOL_NAME
    assert facade.create_tool_search_tool is create_tool_search_tool


def test_facade_preserves_rust_source_deduplication_and_default_limit_text():
    # Rust test: create_tool_search_tool_deduplicates_and_renders_enabled_sources.
    spec = facade.create_tool_search_tool(
        [
            ToolSearchSourceInfo("docs", "Docs source"),
            ToolSearchSourceInfo("docs"),
            ToolSearchSourceInfo("Drive"),
        ],
        default_limit=12,
    )

    assert spec["type"] == "tool_search"
    assert spec["execution"] == "client"
    assert "- Drive\n- docs: Docs source" in spec["description"]
    assert spec["parameters"]["properties"]["limit"]["description"] == (
        "Maximum number of tools to return (defaults to 12)."
    )
