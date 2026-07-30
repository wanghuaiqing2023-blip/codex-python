from __future__ import annotations

import json
from pathlib import Path
import shlex


def create_shell_command_sse_response(
    command: list[str],
    workdir: Path | None,
    timeout_ms: int | None,
    call_id: str,
) -> str:
    arguments = {
        "command": shlex.join(command),
        "workdir": None if workdir is None else str(workdir),
        "timeout_ms": timeout_ms,
    }
    return _tool_response(call_id, "shell_command", arguments)


def create_final_assistant_message_sse_response(message: str) -> str:
    return _sse(
        {"type": "response.created", "response": {"id": "resp-1"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "id": "msg-1",
                "role": "assistant",
                "content": [{"type": "output_text", "text": message}],
            },
        },
        {"type": "response.completed", "response": {"id": "resp-1"}},
    )


def create_apply_patch_sse_response(patch_content: str, call_id: str) -> str:
    return _tool_response(
        call_id,
        "apply_patch",
        {"patch": patch_content},
    )


def create_exec_command_sse_response(call_id: str) -> str:
    return _tool_response(
        call_id,
        "exec_command",
        {"cmd": "cmd.exe /d /c echo hi", "yield_time_ms": 500},
    )


def create_request_user_input_sse_response(call_id: str) -> str:
    return _tool_response(
        call_id,
        "request_user_input",
        {
            "questions": [
                {
                    "id": "confirm_path",
                    "header": "Confirm",
                    "question": "Proceed with the plan?",
                    "options": [
                        {
                            "label": "Yes (Recommended)",
                            "description": "Continue the current plan.",
                        },
                        {"label": "No", "description": "Stop and revisit the approach."},
                    ],
                }
            ]
        },
    )


def create_request_permissions_sse_response(call_id: str) -> str:
    return _tool_response(
        call_id,
        "request_permissions",
        {
            "reason": "Select a workspace root",
            "permissions": {"file_system": {"write": [".", "../shared"]}},
        },
    )


def _tool_response(call_id: str, name: str, arguments: dict[str, object]) -> str:
    return _sse(
        {"type": "response.created", "response": {"id": "resp-1"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": json.dumps(arguments, separators=(",", ":")),
            },
        },
        {"type": "response.completed", "response": {"id": "resp-1"}},
    )


def _sse(*events: dict[str, object]) -> str:
    return "".join(
        f"event: {event['type']}\n"
        f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
        for event in events
    )
