from pathlib import Path

import pytest

from pycodex.tui.history_cell.tests import (
    SMALL_PNG_BASE64,
    LineLike,
    SpanLike,
    assert_unstyled_lines,
    helper_names,
    image_block,
    render_lines,
    render_transcript,
    rendering_behavior_tests,
    resource_link_block,
    stdio_server_config,
    streamable_http_server_config,
    string_map_to_toml_value,
    test_cwd,
    text_block,
)


def test_test_cwd_and_png_fixture_match_rust_intent() -> None:
    assert test_cwd().is_absolute()
    assert SMALL_PNG_BASE64.startswith("iVBORw0KGgo")


def test_mcp_server_config_helpers_build_semantic_tables() -> None:
    assert string_map_to_toml_value({"A": "1"}) == {"A": "1"}
    stdio = stdio_server_config("python", ["-m", "server"], {"KEY": "VALUE"}, ["TOKEN"])
    assert stdio.transport == "stdio"
    assert stdio.command == "python"
    assert stdio.args == ("-m", "server")
    assert stdio.env == {"KEY": "VALUE"}
    assert stdio.env_vars == ("TOKEN",)

    http = streamable_http_server_config(
        "https://example.test/mcp",
        bearer_token_env_var="TOKEN",
        http_headers={"X-Test": "1"},
        env_http_headers={"X-Env": "ENV"},
    )
    assert http.transport == "streamable_http"
    assert http.url == "https://example.test/mcp"
    assert http.bearer_token_env_var == "TOKEN"
    assert http.http_headers == {"X-Test": "1"}
    assert http.env_http_headers == {"X-Env": "ENV"}


def test_render_lines_and_transcript_flatten_line_shapes() -> None:
    lines = [
        "plain",
        {"spans": [{"content": "he"}, {"content": "llo"}]},
        LineLike((SpanLike("wor"), SpanLike("ld"))),
    ]
    assert render_lines(lines) == ["plain", "hello", "world"]

    class Cell:
        def transcript_lines(self, width: int):
            assert width == 65535
            return lines

    assert render_transcript(Cell()) == ["plain", "hello", "world"]


def test_assert_unstyled_lines_accepts_default_and_rejects_styled_spans() -> None:
    assert_unstyled_lines([LineLike((SpanLike("ok"),))])
    with pytest.raises(AssertionError):
        assert_unstyled_lines([LineLike((SpanLike("bad", style="red"),))])


def test_content_block_helpers_match_rust_rmcp_fixture_intent() -> None:
    assert image_block("abc") == {"type": "image", "data": "abc", "mimeType": "image/png"}
    assert text_block("hello") == {"type": "text", "text": "hello"}
    assert resource_link_block("file://x", "x", "Title", "Desc") == {
        "type": "resource_link",
        "resource": {
            "uri": "file://x",
            "name": "x",
            "title": "Title",
            "description": "Desc",
            "mime_type": None,
            "size": None,
            "icons": None,
            "meta": None,
        },
    }


def test_helper_and_rendering_test_inventories_document_module_boundary() -> None:
    assert "render_lines" in helper_names()
    assert "stdio_server_config" in helper_names()
    assert "agent_markdown_cell_renders_source_at_different_widths" in rendering_behavior_tests()
