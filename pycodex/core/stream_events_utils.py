"""Small stream-event helpers ported from Codex core."""

from __future__ import annotations

import base64
import binascii
from pathlib import Path

from pycodex.protocol import MessagePhase, ResponseInputItem, ResponseItem


GENERATED_IMAGE_ARTIFACTS_DIR = "generated_images"
CITATION_OPEN = "<oai-mem-citation>"
CITATION_CLOSE = "</oai-mem-citation>"
PROPOSED_PLAN_OPEN = "<proposed_plan>"
PROPOSED_PLAN_CLOSE = "</proposed_plan>"


def _sanitize_image_artifact_component(value: str) -> str:
    sanitized = "".join(
        ch if ch.isascii() and (ch.isalnum() or ch in {"-", "_"}) else "_"
        for ch in value
    )
    return sanitized or "generated_image"


def image_generation_artifact_path(
    codex_home: str | Path,
    session_id: str,
    call_id: str,
) -> Path:
    return (
        Path(codex_home)
        / GENERATED_IMAGE_ARTIFACTS_DIR
        / _sanitize_image_artifact_component(session_id)
        / f"{_sanitize_image_artifact_component(call_id)}.png"
    )


def save_image_generation_result(
    codex_home: str | Path,
    session_id: str,
    call_id: str,
    result: str,
) -> Path:
    try:
        data = base64.b64decode(result.strip().encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise ValueError(f"invalid image generation payload: {exc}") from exc

    path = image_generation_artifact_path(codex_home, session_id, call_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def raw_assistant_output_text_from_item(item: ResponseItem) -> str | None:
    if item.type != "message" or item.role != "assistant":
        return None
    return "".join(
        content.text or ""
        for content in item.content
        if content.type == "output_text"
    )


def _strip_citations(text: str) -> str:
    visible: list[str] = []
    position = 0
    while True:
        start = text.find(CITATION_OPEN, position)
        if start == -1:
            visible.append(text[position:])
            break
        visible.append(text[position:start])
        content_start = start + len(CITATION_OPEN)
        end = text.find(CITATION_CLOSE, content_start)
        if end == -1:
            break
        position = end + len(CITATION_CLOSE)
    return "".join(visible)


def _is_line_start(text: str, position: int) -> bool:
    return position == 0 or text[position - 1] == "\n"


def _strip_proposed_plan_blocks(text: str) -> str:
    visible: list[str] = []
    position = 0
    while True:
        start = text.find(PROPOSED_PLAN_OPEN, position)
        while start != -1 and not _is_line_start(text, start):
            start = text.find(PROPOSED_PLAN_OPEN, start + len(PROPOSED_PLAN_OPEN))
        if start == -1:
            visible.append(text[position:])
            break

        visible.append(text[position:start])
        content_start = start + len(PROPOSED_PLAN_OPEN)
        if content_start < len(text) and text[content_start] not in {"\n", "\r"}:
            visible.append(PROPOSED_PLAN_OPEN)
            position = content_start
            continue

        end = text.find(PROPOSED_PLAN_CLOSE, content_start)
        if end == -1:
            break
        position = end + len(PROPOSED_PLAN_CLOSE)
        if position < len(text) and text[position] == "\r":
            position += 1
        if position < len(text) and text[position] == "\n":
            position += 1
    return "".join(visible)


def strip_hidden_assistant_markup(text: str, plan_mode: bool) -> str:
    visible = _strip_citations(text)
    if plan_mode:
        visible = _strip_proposed_plan_blocks(visible)
    return visible


def last_assistant_message_from_item(
    item: ResponseItem,
    plan_mode: bool,
) -> str | None:
    combined = raw_assistant_output_text_from_item(item)
    if combined is None or combined == "":
        return None
    stripped = strip_hidden_assistant_markup(combined, plan_mode)
    if stripped.strip() == "":
        return None
    return stripped


def response_item_may_include_external_context(item: ResponseItem) -> bool:
    return item.type in {"tool_search_call", "tool_search_output", "web_search_call"}


def completed_item_defers_mailbox_delivery_to_next_turn(
    item: ResponseItem,
    plan_mode: bool,
) -> bool:
    if item.type == "message":
        if item.role != "assistant" or item.phase == MessagePhase.COMMENTARY:
            return False
        return last_assistant_message_from_item(item, plan_mode) is not None
    if item.type == "image_generation_call":
        return True
    return False


def response_input_to_response_item(input_item: ResponseInputItem) -> ResponseItem | None:
    if input_item.type in {
        "function_call_output",
        "custom_tool_call_output",
        "mcp_tool_call_output",
        "tool_search_output",
    }:
        return ResponseItem.from_response_input_item(input_item)
    return None


__all__ = [
    "GENERATED_IMAGE_ARTIFACTS_DIR",
    "completed_item_defers_mailbox_delivery_to_next_turn",
    "image_generation_artifact_path",
    "last_assistant_message_from_item",
    "raw_assistant_output_text_from_item",
    "response_input_to_response_item",
    "response_item_may_include_external_context",
    "save_image_generation_result",
    "strip_hidden_assistant_markup",
]
