import importlib.util
import io
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "pycodex" / "tui" / "bin" / "md-events.py"
spec = importlib.util.spec_from_file_location("pycodex.tui.bin.md_events", MODULE_PATH)
md_events = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(md_events)


class FailingStdin:
    def read(self):
        raise OSError("boom")


def test_rust_module_metadata_is_complete():
    """The codex-tui module wrapper is complete; parser internals are dependency-crate detail."""

    assert md_events.RUST_MODULE.status == "complete"


def test_format_stdin_read_error_matches_rust_stderr_prefix():
    """Rust codex-tui bin::md-events read_to_string error branch."""

    assert md_events.format_stdin_read_error("boom") == "failed to read stdin: boom"


def test_main_returns_one_and_writes_stderr_on_read_failure():
    """Rust codex-tui bin::md-events exits 1 when stdin cannot be read."""

    stderr = io.StringIO()

    exit_code = md_events.main(stdin=FailingStdin(), stdout=io.StringIO(), stderr=stderr)

    assert exit_code == 1
    assert stderr.getvalue() == "failed to read stdin: boom\n"


def test_successful_markdown_event_stream_outputs_common_debug_events():
    """Rust codex-tui bin::md-events success path prints parser Debug events."""

    assert md_events.markdown_events_debug("# heading\n") == [
        "Start(Heading { level: H1, id: None, classes: [], attrs: [] })",
        'Text(Borrowed("heading"))',
        "End(Heading(H1))",
    ]

    stdout = io.StringIO()
    assert md_events.main(stdin=io.StringIO("plain **bold** and `code`\n"), stdout=stdout, stderr=io.StringIO()) == 0
    assert stdout.getvalue().splitlines() == [
        "Start(Paragraph)",
        'Text(Borrowed("plain "))',
        "Start(Strong)",
        'Text(Borrowed("bold"))',
        "End(Strong)",
        'Text(Borrowed(" and "))',
        'Code(Borrowed("code"))',
        "End(Paragraph)",
    ]


def test_markdown_event_stream_covers_lists_links_and_fenced_code():
    """Python complete module covers common pulldown-cmark Debug event shapes."""

    assert md_events.markdown_events_debug("- [x](https://example.com)\n") == [
        "Start(List(None))",
        "Start(Item)",
        'Start(Link { link_type: Inline, dest_url: Borrowed("https://example.com"), title: Borrowed(""), id: Borrowed("") })',
        'Text(Borrowed("x"))',
        "End(Link)",
        "End(Item)",
        "End(List(false))",
    ]
    assert md_events.markdown_events_debug("```rs\nfn main() {}\n```\n") == [
        'Start(CodeBlock(Fenced(Borrowed("rs"))))',
        'Text(Borrowed("fn main() {}\\n"))',
        "End(CodeBlock)",
    ]
