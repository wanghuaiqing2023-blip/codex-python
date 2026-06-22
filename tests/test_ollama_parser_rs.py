"""Prepared parity tests for Rust ``codex-ollama/src/parser.rs``.

Pytest is deferred until the full ``codex-ollama`` crate is functionally
complete, per the crate-level porting workflow.
"""

from __future__ import annotations

from pycodex.ollama.parser import pull_events_from_value
from pycodex.ollama.pull import ChunkProgress, Status, Success


def test_pull_events_decoder_status_and_success_matches_rust() -> None:
    # Rust source: parser.rs test_pull_events_decoder_status_and_success.
    assert pull_events_from_value({"status": "verifying"}) == [Status("verifying")]

    events = pull_events_from_value({"status": "success"})
    assert events == [Status("success"), Success()]


def test_pull_events_decoder_progress_matches_rust() -> None:
    # Rust source: parser.rs test_pull_events_decoder_progress.
    assert pull_events_from_value({"digest": "sha256:abc", "total": 100}) == [
        ChunkProgress(digest="sha256:abc", total=100, completed=None)
    ]
    assert pull_events_from_value({"digest": "sha256:def", "completed": 42}) == [
        ChunkProgress(digest="sha256:def", total=None, completed=42)
    ]


def test_pull_events_decoder_combines_status_success_before_progress() -> None:
    # Rust source: status/success are pushed before optional ChunkProgress.
    assert pull_events_from_value(
        {"status": "success", "digest": "sha256:abc", "total": 10, "completed": 10}
    ) == [
        Status("success"),
        Success(),
        ChunkProgress(digest="sha256:abc", total=10, completed=10),
    ]


def test_pull_events_decoder_ignores_non_u64_progress_and_defaults_digest() -> None:
    # Rust source: JsonValue::as_u64 rejects negative, float, string, and bool values.
    assert pull_events_from_value({"total": -1, "completed": True}) == []
    assert pull_events_from_value({"total": 2.5, "completed": "3"}) == []
    assert pull_events_from_value({"completed": 3}) == [
        ChunkProgress(digest="", total=None, completed=3)
    ]
