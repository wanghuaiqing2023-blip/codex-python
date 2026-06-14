"""Parity tests for codex-rs/tui/src/history_cell/patches.rs."""

from pycodex.tui.history_cell.patches import (
    GENERATED_IMAGE_TITLE,
    PATCH_FAILURE_TITLE,
    VIEWED_IMAGE_TITLE,
    line_text,
    new_image_generation_call,
    new_patch_apply_failure,
    new_patch_event,
    new_view_image_tool_call,
)


def texts(lines):
    return [line_text(line) for line in lines]


def test_patch_history_cell_renders_deterministic_file_summary() -> None:
    cell = new_patch_event(
        {
            "/repo/b.py": {"kind": "modified"},
            "/repo/a.py": {"kind": "added"},
            "/repo/old.py": {"kind": "renamed", "new_path": "/repo/new.py"},
        },
        "/repo",
    )

    assert texts(cell.display_lines(80)) == [
        "A a.py",
        "M b.py",
        "R old.py -> new.py",
    ]
    assert texts(cell.raw_lines()) == [
        "A a.py",
        "M b.py",
        "R old.py -> new.py",
    ]


def test_patch_apply_failure_title_and_optional_stderr() -> None:
    empty = new_patch_apply_failure("   ")
    failed = new_patch_apply_failure("bad patch\nsecond line")

    assert texts(empty.display_lines(80)) == [PATCH_FAILURE_TITLE]
    rendered = "\n".join(texts(failed.display_lines(80)))
    assert PATCH_FAILURE_TITLE in rendered
    assert "bad patch" in rendered


def test_view_image_tool_call_uses_display_path_relative_to_cwd() -> None:
    cell = new_view_image_tool_call("/repo/images/cat.png", "/repo")

    assert texts(cell.display_lines(80)) == [
        VIEWED_IMAGE_TITLE,
        "  | images/cat.png",
    ]


def test_image_generation_call_renders_revised_prompt_and_saved_path_url() -> None:
    cell = new_image_generation_call(
        "call-image-generation",
        "A tiny blue square",
        "/tmp/generated-image.png",
    )

    rendered = texts(cell.display_lines(80))

    assert rendered[0] == GENERATED_IMAGE_TITLE
    assert rendered[1] == "  | A tiny blue square"
    assert rendered[2] == "  | Saved to: file:///tmp/generated-image.png"


def test_image_generation_call_falls_back_to_call_id_without_prompt_or_path() -> None:
    cell = new_image_generation_call("call-image-generation", None, None)

    assert texts(cell.display_lines(80)) == [
        GENERATED_IMAGE_TITLE,
        "  | call-image-generation",
    ]
