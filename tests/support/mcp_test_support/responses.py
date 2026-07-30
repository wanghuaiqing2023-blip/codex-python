"""MCP model-response fixtures derived from ``responses.rs``."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from tests.support.core_test_support.responses import (
    ev_assistant_message,
    ev_completed,
    ev_function_call,
    ev_response_created,
    sse,
)


def create_shell_command_sse_response(
    command: list[str],
    workdir: str | Path | None,
    timeout_ms: int | None,
    call_id: str,
) -> str:
    arguments = json.dumps(
        {
            "command": shlex.join(command),
            "workdir": str(workdir) if workdir is not None else None,
            "timeout_ms": timeout_ms,
        },
        separators=(",", ":"),
    )
    response_id = f"resp-{call_id}"
    return sse(
        [
            ev_response_created(response_id),
            ev_function_call(call_id, "shell_command", arguments),
            ev_completed(response_id),
        ]
    )


def create_final_assistant_message_sse_response(message: str) -> str:
    response_id = "resp-final"
    return sse(
        [
            ev_response_created(response_id),
            ev_assistant_message("msg-final", message),
            ev_completed(response_id),
        ]
    )


def create_apply_patch_sse_response(patch_content: str, call_id: str) -> str:
    command = f"apply_patch <<'EOF'\n{patch_content}\nEOF"
    arguments = json.dumps({"command": command}, separators=(",", ":"))
    response_id = f"resp-{call_id}"
    return sse(
        [
            ev_response_created(response_id),
            ev_function_call(call_id, "shell_command", arguments),
            ev_completed(response_id),
        ]
    )


__all__ = [
    "create_apply_patch_sse_response",
    "create_final_assistant_message_sse_response",
    "create_shell_command_sse_response",
]
