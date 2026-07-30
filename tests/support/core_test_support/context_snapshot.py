"""Stable request-context rendering derived from ``context_snapshot.rs``."""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


class ContextSnapshotRenderMode(str, Enum):
    REDACTED_TEXT = "redacted_text"
    FULL_TEXT = "full_text"
    KIND_ONLY = "kind_only"
    KIND_WITH_TEXT_PREFIX = "kind_with_text_prefix"


@dataclass(frozen=True)
class ContextSnapshotOptions:
    render_mode: ContextSnapshotRenderMode = ContextSnapshotRenderMode.REDACTED_TEXT
    max_chars: int = 80
    strip_capability_instructions: bool = False
    strip_agents_md_user_context: bool = False

    def with_render_mode(self, render_mode: ContextSnapshotRenderMode) -> "ContextSnapshotOptions":
        return replace(self, render_mode=render_mode)


def _snapshot_text(text: str, options: ContextSnapshotOptions) -> str:
    if options.render_mode is ContextSnapshotRenderMode.FULL_TEXT:
        return text
    if options.render_mode is ContextSnapshotRenderMode.KIND_WITH_TEXT_PREFIX:
        return text[: options.max_chars]
    return f"<REDACTED:{len(text)} chars>"


def format_request_input_snapshot(
    request: Mapping[str, Any] | Any,
    options: ContextSnapshotOptions | None = None,
) -> str:
    options = options or ContextSnapshotOptions()
    if isinstance(request, Mapping):
        items = request.get("input", ())
    else:
        accessor = getattr(request, "input", None)
        items = accessor() if callable(accessor) else getattr(request, "input", ())
    return format_response_items_snapshot(items, options)


def format_response_items_snapshot(
    items: Iterable[Mapping[str, Any]],
    options: ContextSnapshotOptions | None = None,
) -> str:
    options = options or ContextSnapshotOptions()
    rendered: list[str] = []
    for index, original in enumerate(copy.deepcopy(list(items))):
        item_type = original.get("type")
        if item_type is None:
            rendered.append(f"{index:02}:<MISSING_TYPE>")
            continue
        if options.render_mode is ContextSnapshotRenderMode.KIND_ONLY:
            role = original.get("role", "unknown")
            rendered.append(
                f"{index:02}:message/{role}" if item_type == "message" else f"{index:02}:{item_type}"
            )
            continue
        if item_type == "message":
            role = str(original.get("role", "unknown"))
            parts: list[str] = []
            for entry in original.get("content") or ():
                text = entry.get("text") if isinstance(entry, Mapping) else None
                if isinstance(text, str):
                    if (
                        options.strip_capability_instructions
                        and role == "developer"
                        and text.startswith(("<skills_instructions>", "<apps_instructions>"))
                    ):
                        continue
                    if (
                        options.strip_agents_md_user_context
                        and role == "user"
                        and text.startswith("# AGENTS.md instructions for ")
                    ):
                        continue
                    parts.append(_snapshot_text(text, options))
                elif isinstance(entry, Mapping):
                    kind = entry.get("type", "UNKNOWN_CONTENT_ITEM")
                    extras = sorted(set(entry) - {"type", "text"})
                    parts.append(f"<{kind}{':' + ','.join(extras) if extras else ''}>")
                else:
                    parts.append("<UNKNOWN_CONTENT_ITEM>")
            if not parts:
                rendered.append(f"{index:02}:message/{role}:<NO_TEXT>")
            elif len(parts) == 1:
                rendered.append(f"{index:02}:message/{role}:{parts[0]}")
            else:
                body = "\n".join(f"    [{part_index:02}] {part}" for part_index, part in enumerate(parts, 1))
                rendered.append(f"{index:02}:message/{role}[{len(parts)}]:\n{body}")
        elif item_type == "function_call":
            rendered.append(f"{index:02}:function_call/{original.get('name', 'unknown')}")
        elif item_type == "function_call_output":
            output = original.get("output")
            value = _snapshot_text(output, options) if isinstance(output, str) else "<NON_STRING_OUTPUT>"
            rendered.append(f"{index:02}:function_call_output:{value}")
        elif item_type == "reasoning":
            summary = original.get("summary") or ()
            first = summary[0].get("text") if summary and isinstance(summary[0], Mapping) else None
            summary_text = _snapshot_text(first, options) if isinstance(first, str) else "<NO_SUMMARY>"
            encrypted = bool(original.get("encrypted_content"))
            rendered.append(f"{index:02}:reasoning:summary={summary_text}:encrypted={str(encrypted).lower()}")
        else:
            rendered.append(f"{index:02}:{item_type}")
    return "\n".join(rendered)


def format_labeled_items_snapshot(
    scenario: str,
    sections: Sequence[tuple[str, Sequence[Mapping[str, Any]]]],
    options: ContextSnapshotOptions | None = None,
) -> str:
    body = "\n\n".join(
        f"## {title}\n{format_response_items_snapshot(items, options)}" for title, items in sections
    )
    return f"Scenario: {scenario}\n\n{body}"


def format_labeled_requests_snapshot(
    scenario: str,
    sections: Sequence[tuple[str, Mapping[str, Any]]],
    options: ContextSnapshotOptions | None = None,
) -> str:
    body = "\n\n".join(
        f"## {title}\n{format_request_input_snapshot(request, options)}" for title, request in sections
    )
    return f"Scenario: {scenario}\n\n{body}"


__all__ = [
    "ContextSnapshotOptions",
    "ContextSnapshotRenderMode",
    "format_labeled_items_snapshot",
    "format_labeled_requests_snapshot",
    "format_request_input_snapshot",
    "format_response_items_snapshot",
]
