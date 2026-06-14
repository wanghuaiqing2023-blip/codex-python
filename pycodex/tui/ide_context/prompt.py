"""Prompt rendering for IDE context injected into TUI user turns.

Upstream source: ``codex/codex-rs/tui/src/ide_context/prompt.rs``.

The Rust module formats IDE context before the user's request, adjusts text
placeholder byte ranges, and can recover the raw request after the last desktop
prompt delimiter.  Python keeps those exact semantics using lightweight
semantic dataclasses and duck-typed accessors.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, MutableSequence, Sequence

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="ide_context::prompt",
    source="codex/codex-rs/tui/src/ide_context/prompt.rs",
)

MAX_ACTIVE_SELECTION_CHARS = 40_000
MAX_OPEN_TABS = 100
MAX_OPEN_TABS_CHARS = 20_000
PROMPT_REQUEST_BEGIN = "## My request for Codex:"


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int


@dataclass(frozen=True)
class TextElement:
    byte_range: ByteRange
    placeholder_value: str | None = None

    def placeholder(self) -> str | None:
        return self.placeholder_value


@dataclass(frozen=True)
class UserInputText:
    text: str
    text_elements: tuple[TextElement, ...] = ()


@dataclass(frozen=True)
class UserInputLocalImage:
    path: Any
    detail: Any = None


def apply_ide_context_to_user_input(context: Any, items: MutableSequence[Any]) -> bool:
    context_text = render_prompt_context(context)
    if context_text is None:
        return False

    prefix = f"{context_text}\n{PROMPT_REQUEST_BEGIN}\n"
    text_index = next((idx for idx, item in enumerate(items) if _is_text_input(item)), None)
    if text_index is None:
        items.insert(0, UserInputText(prefix, ()))
        return True

    item = items[text_index]
    text = str(_field(item, "text", ""))
    text_elements = tuple(_coerce_text_element(element) for element in (_field(item, "text_elements", []) or []))
    items[text_index] = prefixed_text_input(prefix, text, text_elements)
    return True


def has_prompt_context(context: Any) -> bool:
    return render_prompt_context(context) is not None


def extract_prompt_request_with_offset(message: str) -> tuple[str, int]:
    marker_index = message.rfind(PROMPT_REQUEST_BEGIN)
    if marker_index == -1:
        return message, 0
    request_start = marker_index + len(PROMPT_REQUEST_BEGIN)
    request = message[request_start:]
    leading_trimmed_len = len(request) - len(request.lstrip())
    return request.strip(), request_start + leading_trimmed_len


def prefixed_text_input(prefix: str, text: str, text_elements: Sequence[TextElement | Any]) -> UserInputText:
    prefix_len = len(prefix.encode("utf-8"))
    adjusted = []
    for raw_element in text_elements:
        element = _coerce_text_element(raw_element)
        adjusted.append(
            TextElement(
                ByteRange(
                    start=element.byte_range.start + prefix_len,
                    end=element.byte_range.end + prefix_len,
                ),
                element.placeholder(),
            )
        )
    return UserInputText(f"{prefix}{text}", tuple(adjusted))


def render_prompt_context(context: Any) -> str | None:
    section = []
    active_file = _field(context, "active_file")
    open_tabs = list(_field(context, "open_tabs", []) or [])

    if active_file is not None:
        descriptor = _field(active_file, "descriptor")
        section.append(f"\n## Active file: {_field(descriptor, 'path')}\n")

        selections = list(_field(active_file, "selections", []) or [])
        selected_ranges = selections if selections else [_field(active_file, "selection")]
        selected_ranges = [range_ for range_ in selected_ranges if range_ is not None and not _range_empty(range_)]
        active_selection_content = str(_field(active_file, "active_selection_content", "") or "")
        if selected_ranges and (active_selection_content == "" or len(selected_ranges) > 1):
            section.append("\n## Active selection range:\n" if len(selected_ranges) == 1 else "\n## Active selection ranges:\n")
            path = _field(descriptor, "path")
            for range_ in selected_ranges:
                start = _field(range_, "start")
                end = _field(range_, "end")
                section.append(
                    f"- {path}: line {_field(start, 'line') + 1}, column {_field(start, 'character') + 1} "
                    f"to line {_field(end, 'line') + 1}, column {_field(end, 'character') + 1}\n"
                )

        if active_selection_content:
            section.append("\n## Active selection of the file:\n")
            if len(active_selection_content) > MAX_ACTIVE_SELECTION_CHARS:
                section.append(active_selection_content[:MAX_ACTIVE_SELECTION_CHARS])
                section.append(f"\n[Selection truncated to {MAX_ACTIVE_SELECTION_CHARS} characters.]\n")
            else:
                section.append(active_selection_content)

    if open_tabs:
        section.append("\n## Open tabs:\n")
        rendered_tabs = 0
        rendered_tab_chars = 0
        for tab in open_tabs:
            if rendered_tabs >= MAX_OPEN_TABS:
                break
            tab_line = f"- {_field(tab, 'label')}: {_field(tab, 'path')}\n"
            if rendered_tab_chars + len(tab_line) > MAX_OPEN_TABS_CHARS:
                break
            section.append(tab_line)
            rendered_tabs += 1
            rendered_tab_chars += len(tab_line)
        omitted_tabs = len(open_tabs) - rendered_tabs
        if omitted_tabs > 0:
            section.append(f"[{omitted_tabs} open tabs omitted.]\n")

    if not section:
        return None
    return "# Context from my IDE setup:\n" + "".join(section)


def _is_text_input(item: Any) -> bool:
    if isinstance(item, UserInputText):
        return True
    if isinstance(item, Mapping):
        return "text" in item and ("path" not in item or item.get("kind") == "text")
    return hasattr(item, "text")


def _coerce_text_element(element: Any) -> TextElement:
    if isinstance(element, TextElement):
        return element
    byte_range = _field(element, "byte_range")
    if byte_range is None:
        byte_range = _field(element, "range")
    placeholder = _field(element, "placeholder_value")
    if placeholder is None:
        raw_placeholder = getattr(element, "placeholder", None)
        placeholder = raw_placeholder() if callable(raw_placeholder) else _field(element, "placeholder")
    return TextElement(
        ByteRange(int(_field(byte_range, "start")), int(_field(byte_range, "end"))),
        None if placeholder is None else str(placeholder),
    )


def _range_empty(range_: Any) -> bool:
    start = _field(range_, "start")
    end = _field(range_, "end")
    return _field(start, "line") == _field(end, "line") and _field(start, "character") == _field(end, "character")


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = [
    "ByteRange",
    "MAX_ACTIVE_SELECTION_CHARS",
    "MAX_OPEN_TABS",
    "MAX_OPEN_TABS_CHARS",
    "PROMPT_REQUEST_BEGIN",
    "RUST_MODULE",
    "TextElement",
    "UserInputLocalImage",
    "UserInputText",
    "apply_ide_context_to_user_input",
    "extract_prompt_request_with_offset",
    "has_prompt_context",
    "prefixed_text_input",
    "render_prompt_context",
]
