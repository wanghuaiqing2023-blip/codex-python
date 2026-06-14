"""Parity tests for ``codex-tui/src/ide_context/prompt.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pycodex.tui.ide_context.prompt import (
    ByteRange,
    MAX_ACTIVE_SELECTION_CHARS,
    PROMPT_REQUEST_BEGIN,
    TextElement,
    UserInputLocalImage,
    UserInputText,
    apply_ide_context_to_user_input,
    extract_prompt_request_with_offset,
    has_prompt_context,
    render_prompt_context,
)


@dataclass(frozen=True)
class FileDescriptor:
    label: str
    path: str


@dataclass(frozen=True)
class Position:
    line: int
    character: int


@dataclass(frozen=True)
class Range:
    start: Position
    end: Position


@dataclass(frozen=True)
class ActiveFile:
    descriptor: FileDescriptor
    selection: Range
    active_selection_content: str
    selections: list[Range]


@dataclass(frozen=True)
class IdeContext:
    active_file: ActiveFile | None
    open_tabs: list[FileDescriptor]


def descriptor(label: str, path: str) -> FileDescriptor:
    return FileDescriptor(label, path)


def test_render_prompt_context_matches_app_format():
    context = IdeContext(
        active_file=ActiveFile(
            descriptor("lib.rs", "src/lib.rs"),
            Range(Position(4, 0), Position(6, 1)),
            "fn selected() {}",
            [],
        ),
        open_tabs=[descriptor("lib.rs", "src/lib.rs"), descriptor("main.rs", "src/main.rs")],
    )

    assert render_prompt_context(context) == (
        "# Context from my IDE setup:\n\n## Active file: src/lib.rs\n\n"
        "## Active selection of the file:\nfn selected() {}\n## Open tabs:\n"
        "- lib.rs: src/lib.rs\n- main.rs: src/main.rs\n"
    )


def test_render_prompt_context_omits_empty_context():
    assert render_prompt_context(IdeContext(active_file=None, open_tabs=[])) is None
    assert not has_prompt_context(IdeContext(active_file=None, open_tabs=[]))


def test_apply_ide_context_uses_desktop_prompt_request_delimiter():
    context = IdeContext(
        active_file=ActiveFile(
            descriptor("lib.rs", "src/lib.rs"),
            Range(Position(0, 0), Position(0, 0)),
            "",
            [],
        ),
        open_tabs=[],
    )
    items = [
        UserInputLocalImage(Path("/tmp/screenshot.png")),
        UserInputText("Ask $figma", (TextElement(ByteRange(4, 10), "$figma"),)),
    ]

    assert apply_ide_context_to_user_input(context, items)

    expected_prefix = "# Context from my IDE setup:\n\n## Active file: src/lib.rs\n\n## My request for Codex:\n"
    prefix_len = len(expected_prefix.encode("utf-8"))
    assert items == [
        UserInputLocalImage(Path("/tmp/screenshot.png")),
        UserInputText(
            f"{expected_prefix}Ask $figma",
            (TextElement(ByteRange(prefix_len + 4, prefix_len + 10), "$figma"),),
        ),
    ]


def test_apply_ide_context_inserts_text_item_when_request_has_no_text():
    context = {"active_file": {"descriptor": {"path": "src/lib.rs"}, "selection": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}, "active_selection_content": "", "selections": []}, "open_tabs": []}
    items = [UserInputLocalImage(Path("image.png"))]

    assert apply_ide_context_to_user_input(context, items)
    assert isinstance(items[0], UserInputText)
    assert items[0].text.endswith(f"{PROMPT_REQUEST_BEGIN}\n")


def test_extract_prompt_request_returns_text_after_last_delimiter():
    message = "# Context\n## My request for Codex:\nFirst\n## My request for Codex:\n  Second\n"
    assert extract_prompt_request_with_offset(message) == ("Second", message.find("Second"))
    assert extract_prompt_request_with_offset("plain") == ("plain", 0)


def test_render_prompt_context_includes_selection_ranges_without_content():
    first_range = Range(Position(1, 2), Position(1, 5))
    second_range = Range(Position(3, 0), Position(4, 1))
    context = IdeContext(
        active_file=ActiveFile(
            descriptor("lib.rs", "src/lib.rs"),
            first_range,
            "",
            [first_range, second_range],
        ),
        open_tabs=[],
    )

    assert render_prompt_context(context) == (
        "# Context from my IDE setup:\n\n## Active file: src/lib.rs\n\n## Active selection ranges:\n"
        "- src/lib.rs: line 2, column 3 to line 2, column 6\n"
        "- src/lib.rs: line 4, column 1 to line 5, column 2\n"
    )


def test_render_prompt_context_truncates_large_selection():
    context = IdeContext(
        active_file=ActiveFile(
            descriptor("large.txt", "large.txt"),
            Range(Position(0, 0), Position(0, 1)),
            f"{'a' * MAX_ACTIVE_SELECTION_CHARS}tail",
            [],
        ),
        open_tabs=[],
    )

    rendered = render_prompt_context(context)
    assert rendered is not None
    assert f"[Selection truncated to {MAX_ACTIVE_SELECTION_CHARS} characters.]" in rendered
    assert "tail" not in rendered


def test_render_prompt_context_omits_excess_open_tabs():
    context = IdeContext(
        active_file=None,
        open_tabs=[descriptor(f"file-{index}.rs", f"src/file-{index}.rs") for index in range(102)],
    )

    rendered = render_prompt_context(context)
    assert rendered is not None
    assert "- file-99.rs: src/file-99.rs\n" in rendered
    assert "- file-100.rs: src/file-100.rs\n" not in rendered
    assert "[2 open tabs omitted.]\n" in rendered
