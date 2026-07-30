"""Responses API fixtures derived from ``core/tests/common/responses.rs``."""

from __future__ import annotations

import base64
import json
from collections.abc import Iterable, Mapping
from typing import Any


def sse(events: Iterable[Mapping[str, Any]]) -> str:
    chunks: list[str] = []
    for event in events:
        kind = event["type"]
        chunk = f"event: {kind}\n"
        if len(event) != 1:
            chunk += "data: " + json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n"
        chunks.append(chunk + "\n")
    return "".join(chunks)


def ev_completed(response_id: str) -> dict[str, Any]:
    return {
        "type": "response.completed",
        "response": {
            "id": response_id,
            "usage": {
                "input_tokens": 0,
                "input_tokens_details": None,
                "output_tokens": 0,
                "output_tokens_details": None,
                "total_tokens": 0,
            },
        },
    }


def ev_response_created(response_id: str) -> dict[str, Any]:
    return {"type": "response.created", "response": {"id": response_id}}


def sse_completed(response_id: str) -> str:
    return sse([ev_response_created(response_id), ev_completed(response_id)])


def ev_completed_with_tokens(response_id: str, total_tokens: int) -> dict[str, Any]:
    event = ev_completed(response_id)
    event["response"]["usage"].update(input_tokens=total_tokens, total_tokens=total_tokens)
    return event


def ev_assistant_message(item_id: str, text: str) -> dict[str, Any]:
    return {
        "type": "response.output_item.done",
        "item": {
            "type": "message",
            "role": "assistant",
            "id": item_id,
            "content": [{"type": "output_text", "text": text}],
        },
    }


def user_message_item(text: str) -> dict[str, Any]:
    return {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}


def ev_message_item_added(item_id: str, text: str) -> dict[str, Any]:
    event = ev_assistant_message(item_id, text)
    event["type"] = "response.output_item.added"
    return event


def ev_output_text_delta(delta: str) -> dict[str, Any]:
    return {"type": "response.output_text.delta", "delta": delta}


def ev_reasoning_item(item_id: str, summary: Iterable[str], raw_content: Iterable[str]) -> dict[str, Any]:
    raw = list(raw_content)
    item: dict[str, Any] = {
        "type": "reasoning",
        "id": item_id,
        "summary": [{"type": "summary_text", "text": text} for text in summary],
        "encrypted_content": base64.b64encode(("b" * 550 + "".join(raw)).encode()).decode(),
    }
    if raw:
        item["content"] = [{"type": "reasoning_text", "text": text} for text in raw]
    return {"type": "response.output_item.done", "item": item}


def ev_reasoning_item_added(item_id: str, summary: Iterable[str]) -> dict[str, Any]:
    event = ev_reasoning_item(item_id, summary, ())
    event["type"] = "response.output_item.added"
    event["item"].pop("encrypted_content", None)
    return event


def ev_reasoning_summary_text_delta(delta: str) -> dict[str, Any]:
    return {"type": "response.reasoning_summary_text.delta", "delta": delta, "summary_index": 0}


def ev_reasoning_text_delta(delta: str) -> dict[str, Any]:
    return {"type": "response.reasoning_text.delta", "delta": delta, "content_index": 0}


def ev_function_call(call_id: str, name: str, arguments: str) -> dict[str, Any]:
    return {
        "type": "response.output_item.done",
        "item": {"type": "function_call", "call_id": call_id, "name": name, "arguments": arguments},
    }


def ev_function_call_with_namespace(
    call_id: str, namespace: str, name: str, arguments: str
) -> dict[str, Any]:
    event = ev_function_call(call_id, name, arguments)
    event["item"]["namespace"] = namespace
    return event


def ev_custom_tool_call(call_id: str, name: str, input_text: str) -> dict[str, Any]:
    return {
        "type": "response.output_item.done",
        "item": {"type": "custom_tool_call", "call_id": call_id, "name": name, "input": input_text},
    }


def ev_shell_command_call(call_id: str, command: str) -> dict[str, Any]:
    return ev_function_call(
        call_id,
        "shell_command",
        json.dumps({"command": command}, separators=(",", ":")),
    )


def ev_apply_patch_custom_tool_call(call_id: str, patch: str) -> dict[str, Any]:
    return ev_custom_tool_call(call_id, "apply_patch", patch)


def sse_failed(response_id: str, code: str, message: str) -> str:
    return sse(
        [
            {
                "type": "response.failed",
                "response": {"id": response_id, "error": {"code": code, "message": message}},
            }
        ]
    )


__all__ = [
    "ev_apply_patch_custom_tool_call",
    "ev_assistant_message",
    "ev_completed",
    "ev_completed_with_tokens",
    "ev_custom_tool_call",
    "ev_function_call",
    "ev_function_call_with_namespace",
    "ev_message_item_added",
    "ev_output_text_delta",
    "ev_reasoning_item",
    "ev_reasoning_item_added",
    "ev_reasoning_summary_text_delta",
    "ev_reasoning_text_delta",
    "ev_response_created",
    "ev_shell_command_call",
    "sse",
    "sse_completed",
    "sse_failed",
    "user_message_item",
]
