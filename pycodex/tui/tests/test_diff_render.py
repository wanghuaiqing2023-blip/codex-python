"""Parity evidence for fixed-commit ``codex-tui::diff_render`` history output."""

# Rust source: codex/codex-rs/tui/src/diff_render.rs

from pycodex.tui.diff_model import FileChange
from pycodex.tui.diff_render import create_diff_summary, display_width


def _text(line) -> str:
    return "".join(span.content for span in line.spans)


def test_diff_summary_renders_rust_header_counts_line_numbers_and_syntax() -> None:
    lines = create_diff_summary(
        {"hello.c": FileChange.add('printf("hello");\nreturn 0;\n')},
        ".",
        80,
    )

    assert _text(lines[0]) == "• Added hello.c (+2 -0)"
    assert _text(lines[1]).startswith("    1 + printf")
    assert _text(lines[2]).startswith("    2 + return")
    assert any(getattr(span.style, "fg", None) is not None for span in lines[1].spans)


def test_diff_summary_handles_update_rename_delete_and_narrow_width() -> None:
    lines = create_diff_summary(
        {
            "old.py": FileChange.update("@@ -1 +1 @@\n-old\n+new\n", "new.py"),
            "gone.txt": FileChange.delete("one\ntwo\n"),
        },
        ".",
        20,
    )
    rendered = [_text(line) for line in lines]

    assert rendered[0] == "• Edited 2 files (+1 -3)"
    assert any("old.py → new.py" in line for line in rendered)
    assert any("gone.txt" in line for line in rendered)
    diff_rows = [line for line in rendered if " + " in line or " - " in line]
    assert all(display_width(line) <= 20 for line in diff_rows)
