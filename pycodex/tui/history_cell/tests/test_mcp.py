"""Parity tests for codex-rs/tui/src/history_cell/mcp.rs."""

import base64

from pycodex.tui.history_cell.mcp import (
    CallToolResult,
    McpAuthStatus,
    McpInventoryLoadingCell,
    McpInvocation,
    McpServerStatusDetail,
    McpToolCallCell,
    decode_mcp_image,
    empty_mcp_output,
    format_mcp_invocation,
    line_text,
    mcp_auth_status_label,
    new_active_mcp_tool_call,
    new_mcp_inventory_loading,
    new_mcp_tools_output_from_statuses,
    try_new_completed_mcp_tool_call_with_image_output,
)


PNG_1X1 = b"\x89PNG\r\n\x1a\n" + b"png-bytes"


def texts(lines):
    return [line_text(line) for line in lines]


def test_auth_status_labels_match_rust_copy() -> None:
    assert mcp_auth_status_label(McpAuthStatus.Unsupported) == "Unsupported"
    assert mcp_auth_status_label("NotLoggedIn") == "Not logged in"
    assert mcp_auth_status_label("BearerToken") == "Bearer token"
    assert mcp_auth_status_label("OAuth") == "OAuth"


def test_format_invocation_uses_compact_json_arguments() -> None:
    line = format_mcp_invocation(McpInvocation("server", "tool", {"b": 2}))

    assert line_text(line) == 'server.tool({"b":2})'


def test_mcp_tool_call_active_complete_error_and_animation() -> None:
    cell = new_active_mcp_tool_call(
        "call-1",
        {"server": "s", "tool": "t", "arguments": {"x": 1}},
        animations_enabled=True,
    )

    assert cell.call_id() == "call-1"
    assert cell.success() is None
    assert cell.transcript_animation_tick() == 0
    assert texts(cell.raw_lines()) == ['Calling s.t({"x":1})']

    cell.mark_failed()

    assert cell.success() is False
    assert cell.transcript_animation_tick() is None
    assert texts(cell.raw_lines()) == ['Called s.t({"x":1})', "Error: interrupted"]


def test_mcp_tool_call_success_renders_content_blocks() -> None:
    cell = McpToolCallCell.new("call-1", McpInvocation("s", "t", None), False)
    extra = cell.complete(
        1.2,
        CallToolResult(
            content=(
                {"type": "text", "text": "hello"},
                {"type": "image", "data": base64.b64encode(PNG_1X1).decode()},
                {"type": "audio"},
                {"type": "resource", "resource": {"uri": "file://a"}},
                {"type": "resource_link", "uri": "https://example.com"},
            ),
            is_error=False,
        ),
    )

    assert extra is not None
    assert cell.success() is True
    assert texts(cell.raw_lines()) == [
        "Called s.t()",
        "hello",
        "<image content>",
        "<audio content>",
        "embedded resource: file://a",
        "link: https://example.com",
    ]


def test_decode_mcp_image_accepts_plain_and_data_url_png() -> None:
    encoded = base64.b64encode(PNG_1X1).decode()

    assert decode_mcp_image({"type": "image", "data": encoded}) == PNG_1X1
    assert decode_mcp_image({"type": "image", "data": f"data:image/png;base64,{encoded}"}) == PNG_1X1
    assert decode_mcp_image({"type": "image", "data": "not-base64"}) is None
    assert try_new_completed_mcp_tool_call_with_image_output("error") is None


def test_empty_mcp_output_and_status_inventory_lines() -> None:
    assert "No MCP servers configured" in "\n".join(texts(empty_mcp_output().display_lines(80)))

    cell = new_mcp_tools_output_from_statuses(
        [
            {
                "name": "beta",
                "tools": {"z": {}},
                "auth_status": "OAuth",
                "resources": [{"name": "Docs", "uri": "file://docs"}],
                "resource_templates": [{"name": "Item", "uri_template": "item://{id}"}],
            },
            {"name": "alpha", "tools": {}, "auth_status": "Unsupported"},
        ],
        McpServerStatusDetail.Full,
    )

    rendered = texts(cell.display_lines(80))

    assert rendered[:5] == ["/mcp", "", "MCP Tools", "", "  - alpha"]
    assert "    - Tools: z" in rendered
    assert "    - Resources: Docs (file://docs)" in rendered
    assert "    - Resource templates: Item (item://{id})" in rendered


def test_inventory_loading_cell_animates_only_when_enabled() -> None:
    animated = new_mcp_inventory_loading(True)
    static = McpInventoryLoadingCell.new(False)

    assert texts(animated.display_lines(80)) == ["- Loading MCP inventory..."]
    assert texts(animated.raw_lines()) == ["Loading MCP inventory..."]
    assert animated.transcript_animation_tick() == 0
    assert static.transcript_animation_tick() is None
