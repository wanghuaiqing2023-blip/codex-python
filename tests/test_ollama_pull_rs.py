"""Prepared parity tests for Rust ``codex-ollama/src/pull.rs``.

Pytest is deferred until the full ``codex-ollama`` crate is functionally
complete, per the crate-level porting workflow.
"""

from __future__ import annotations

from io import StringIO

from pycodex.ollama.pull import (
    ChunkProgress,
    CliProgressReporter,
    Error,
    Status,
    Success,
    TuiProgressReporter,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_cli_progress_reporter_status_matches_rust_inline_rendering() -> None:
    # Rust source: CliProgressReporter::on_event Status branch.
    out = StringIO()
    reporter = CliProgressReporter(writer=out, clock=FakeClock())

    reporter.on_event(Status("verifying"))
    reporter.on_event(Status("ok"))
    reporter.on_event(Status("pulling manifest"))
    reporter.on_event(Status("PULLING MANIFEST"))

    assert out.getvalue() == "\rverifying\rok       "
    assert reporter.last_line_len == len("ok")


def test_cli_progress_reporter_chunk_progress_header_and_speed() -> None:
    # Rust source: ChunkProgress branch aggregates totals by digest.
    clock = FakeClock()
    out = StringIO()
    reporter = CliProgressReporter(writer=out, clock=clock)
    total = 1024 * 1024 * 1024

    reporter.on_event(ChunkProgress(digest="sha256:a", total=total, completed=0))
    clock.now = 2.0
    reporter.on_event(ChunkProgress(digest="sha256:a", completed=512 * 1024 * 1024))

    text = out.getvalue()
    assert text.startswith("\r\x1b[2KDownloading model: total 1.00 GB\n")
    assert "\r0.00/1.00 GB (0.0%) 0.0 MB/s" in text
    assert "\r0.50/1.00 GB (50.0%) 256.0 MB/s" in text


def test_cli_progress_reporter_ignores_zero_total_error_and_writes_success_newline() -> None:
    # Rust source: zero aggregate total returns Ok, Error is handled by caller, Success writes newline.
    out = StringIO()
    reporter = CliProgressReporter(writer=out, clock=FakeClock())

    reporter.on_event(ChunkProgress(digest="sha256:a", completed=10))
    reporter.on_event(Error("boom"))
    reporter.on_event(Success())

    assert out.getvalue() == "\n"


def test_tui_progress_reporter_delegates_to_cli_reporter() -> None:
    # Rust source: TuiProgressReporter(CliProgressReporter) forwards on_event.
    out = StringIO()
    reporter = TuiProgressReporter(CliProgressReporter(writer=out, clock=FakeClock()))

    reporter.on_event(Status("writing"))

    assert out.getvalue() == "\rwriting"
