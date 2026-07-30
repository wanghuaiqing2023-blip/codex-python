"""Python counterpart of the Rust ``mcp_test_support`` crate."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from tests.support.core_test_support import (
    format_with_current_shell,
    format_with_current_shell_display_non_login,
    format_with_current_shell_non_login,
)

from .mcp_process import McpProcess
from .mock_model_server import create_mock_responses_server
from .responses import (
    create_apply_patch_sse_response,
    create_final_assistant_message_sse_response,
    create_shell_command_sse_response,
)

T = TypeVar("T")


def to_response(
    response: Mapping[str, Any],
    decoder: Callable[[Any], T] | None = None,
) -> T | Any:
    if "error" in response:
        raise RuntimeError(str(response["error"]))
    if "result" not in response:
        raise ValueError("JSON-RPC response has no result")
    result = response["result"]
    return decoder(result) if decoder is not None else result


__all__ = [
    "McpProcess",
    "create_apply_patch_sse_response",
    "create_final_assistant_message_sse_response",
    "create_mock_responses_server",
    "create_shell_command_sse_response",
    "format_with_current_shell",
    "format_with_current_shell_display_non_login",
    "format_with_current_shell_non_login",
    "to_response",
]
