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


def test_format_stdin_read_error_matches_rust_stderr_prefix():
    """Rust codex-tui bin::md-events read_to_string error branch."""

    assert md_events.format_stdin_read_error("boom") == "failed to read stdin: boom"


def test_main_returns_one_and_writes_stderr_on_read_failure():
    """Rust codex-tui bin::md-events exits 1 when stdin cannot be read."""

    stderr = io.StringIO()

    exit_code = md_events.main(stdin=FailingStdin(), stdout=io.StringIO(), stderr=stderr)

    assert exit_code == 1
    assert stderr.getvalue() == "failed to read stdin: boom\n"


def test_successful_markdown_event_stream_is_explicitly_blocked_not_faked():
    """Rust success path depends on pulldown-cmark Parser Debug event parity."""

    with pytest.raises(NotImplementedError):
        md_events.markdown_events_debug("# heading\n")

    with pytest.raises(NotImplementedError):
        md_events.main(stdin=io.StringIO("# heading\n"), stdout=io.StringIO(), stderr=io.StringIO())
