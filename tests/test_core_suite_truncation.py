from __future__ import annotations

from datetime import timedelta

from pycodex.core.tools import format_exec_output_for_model
from pycodex.core.tools.context import McpToolOutput, ToolPayload
from pycodex.protocol import (
    DEFAULT_IMAGE_DETAIL,
    CallToolResult,
    ExecToolCallOutput,
    FunctionCallOutputContentItem,
    StreamOutput,
    TruncationPolicyConfig,
)


def _shell_output(text: str, policy: TruncationPolicyConfig) -> str:
    output = ExecToolCallOutput(
        exit_code=0,
        aggregated_output=StreamOutput.new(text),
        duration=timedelta(milliseconds=25),
        timed_out=False,
    )
    return format_exec_output_for_model(output, policy).replace("\r\n", "\n")


def _mcp_text_output(text: str, policy: TruncationPolicyConfig) -> str:
    output = McpToolOutput(
        result=CallToolResult(content=({"type": "text", "text": text},), is_error=False),
        tool_input={"message": text},
        wall_time_seconds=0.25,
        original_image_detail_supported=False,
        truncation_policy=policy,
    )
    item = output.to_response_item("call-mcp", ToolPayload.function("{}"))
    return item.output.to_text() or ""


def test_tool_call_output_configured_limit_chars_type() -> None:
    # Rust: core/tests/suite/truncation.rs::tool_call_output_configured_limit_chars_type.
    body = "".join(f"{index}\n" for index in range(1, 1000))
    output = _shell_output(body, TruncationPolicyConfig.tokens(100_000))

    assert output.endswith(body)
    assert "tokens truncated" not in output
    assert "chars truncated" not in output


def test_tool_call_output_exceeds_limit_truncated_chars_limit() -> None:
    # Rust: core/tests/suite/truncation.rs::tool_call_output_exceeds_limit_truncated_chars_limit.
    body = "".join(f"{index}\n" for index in range(1, 1000))
    output = _shell_output(body, TruncationPolicyConfig.bytes(256))

    assert output.startswith("Exit code: 0\nWall time:")
    assert "Total output lines: 999" in output
    assert "chars truncated" in output
    assert "tokens truncated" not in output


def test_tool_call_output_exceeds_limit_truncated_for_model() -> None:
    # Rust: core/tests/suite/truncation.rs::tool_call_output_exceeds_limit_truncated_for_model.
    body = "".join(f"{index}\n" for index in range(1, 2000))
    output = _shell_output(body, TruncationPolicyConfig.tokens(50))

    assert output.startswith("Exit code: 0\nWall time:")
    assert "Total output lines: 1999" in output
    assert "tokens truncated" in output
    assert "1\n2\n3\n" in output
    assert "1999\n" in output


def test_tool_call_output_truncated_only_once() -> None:
    # Rust: core/tests/suite/truncation.rs::tool_call_output_truncated_only_once.
    body = "".join(f"{index}\n" for index in range(1, 5000))
    output = _shell_output(body, TruncationPolicyConfig.tokens(100))

    assert output.count("tokens truncated") == 1


def test_mcp_tool_call_output_exceeds_limit_truncated_for_model() -> None:
    # Rust: core/tests/suite/truncation.rs::mcp_tool_call_output_exceeds_limit_truncated_for_model.
    output = _mcp_text_output("long-message-with-newlines-" * 1000, TruncationPolicyConfig.tokens(50))

    assert output.startswith("Wall time: 0.2500 seconds\nOutput:")
    assert "Total output lines:" not in output
    assert "tokens truncated" in output
    assert len(output) < 3000


def test_mcp_image_output_preserves_image_and_no_text_summary() -> None:
    # Rust: core/tests/suite/truncation.rs::mcp_image_output_preserves_image_and_no_text_summary.
    image_url = "data:image/png;base64,iVBORw0KGgo="
    output = McpToolOutput(
        result=CallToolResult(
            content=({"type": "image", "data": image_url},),
            is_error=False,
        ),
        tool_input={},
        wall_time_seconds=0.25,
        original_image_detail_supported=True,
        truncation_policy=TruncationPolicyConfig.tokens(10_000),
    )

    item = output.to_response_item("call-image", ToolPayload.function("{}"))
    content_items = item.output.content_items

    assert content_items is not None
    assert len(content_items) == 2
    assert content_items[0].type == "input_text"
    assert content_items[0].text == "Wall time: 0.2500 seconds\nOutput:"
    assert content_items[1].type == "input_image"
    assert content_items[1].image_url == image_url


def test_token_policy_marker_reports_tokens() -> None:
    # Rust: core/tests/suite/truncation.rs::token_policy_marker_reports_tokens.
    body = "".join(f"{index}\n" for index in range(1, 151))
    output = _shell_output(body, TruncationPolicyConfig.tokens(50))

    assert "Total output lines: 150" in output
    assert "tokens truncated" in output
    assert "chars truncated" not in output


def test_byte_policy_marker_reports_bytes() -> None:
    # Rust: core/tests/suite/truncation.rs::byte_policy_marker_reports_bytes.
    body = "".join(f"{index}\n" for index in range(1, 151))
    output = _shell_output(body, TruncationPolicyConfig.bytes(200))

    assert "Total output lines: 150" in output
    assert "chars truncated" in output
    assert "tokens truncated" not in output


def test_shell_command_output_not_truncated_with_custom_limit() -> None:
    # Rust: core/tests/suite/truncation.rs::shell_command_output_not_truncated_with_custom_limit.
    body = "".join(f"{index}\n" for index in range(1, 1001))
    output = _shell_output(body, TruncationPolicyConfig.tokens(50_000))

    assert output.endswith(body)
    assert "truncated" not in output


def test_mcp_tool_call_output_not_truncated_with_custom_limit() -> None:
    # Rust: core/tests/suite/truncation.rs::mcp_tool_call_output_not_truncated_with_custom_limit.
    payload = "a" * 80_000
    output = _mcp_text_output(payload, TruncationPolicyConfig.tokens(50_000))

    assert payload in output
    assert "truncated" not in output
