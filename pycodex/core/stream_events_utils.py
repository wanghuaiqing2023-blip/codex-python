"""Small stream-event helpers ported from Codex core."""

from __future__ import annotations

from pycodex.protocol import ResponseItem


def raw_assistant_output_text_from_item(item: ResponseItem) -> str | None:
    if item.type != "message" or item.role != "assistant":
        return None
    return "".join(
        content.text or ""
        for content in item.content
        if content.type == "output_text"
    )


__all__ = ["raw_assistant_output_text_from_item"]
