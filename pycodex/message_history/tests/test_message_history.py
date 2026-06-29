"""Rust-derived tests for ``codex-message-history``.

Rust source:
- ``codex-rs/message-history/src/lib.rs``
- ``codex-rs/message-history/src/tests.rs``
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from pycodex.config.types import History, HistoryPersistence
from pycodex.message_history import HistoryConfig, append_entry, history_metadata, lookup


def test_lookup_reads_history_entries_and_metadata_counts_lines(tmp_path) -> None:
    # Rust test: lookup_reads_history_entries.
    path = tmp_path / "history.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(entry, separators=(",", ":"))
            for entry in (
                {"session_id": "session-a", "ts": 1, "text": "older"},
                {"session_id": "session-b", "ts": 2, "text": "newer"},
            )
        )
        + "\n",
        encoding="utf-8",
    )
    config = HistoryConfig.new(tmp_path, History())

    log_id, count = asyncio.run(history_metadata(config))

    assert log_id != 0
    assert count == 2
    assert lookup(log_id, 1, config).text == "newer"
    assert lookup(log_id + 1, 1, config) is None
    assert lookup(log_id, 99, config) is None


def test_append_entry_obeys_persistence_and_writes_rust_jsonl_shape(tmp_path) -> None:
    # Rust contract: append_entry writes one JSON object per line with
    # session_id, ts, and text; HistoryPersistence::None skips writes.
    config = HistoryConfig.new(tmp_path, History())
    asyncio.run(append_entry("hello", "conversation-1", config))

    record = json.loads((tmp_path / "history.jsonl").read_text(encoding="utf-8"))
    assert record["session_id"] == "conversation-1"
    assert isinstance(record["ts"], int)
    assert record["text"] == "hello"

    disabled = HistoryConfig.new(tmp_path / "disabled", SimpleNamespace(persistence=HistoryPersistence.NONE))
    asyncio.run(append_entry("hidden", "conversation-1", disabled))
    assert not (tmp_path / "disabled" / "history.jsonl").exists()


def test_append_entry_trims_history_when_beyond_max_bytes(tmp_path) -> None:
    # Rust test: append_entry_trims_history_when_beyond_max_bytes keeps the
    # newest tail rather than allowing unbounded history growth.
    config = HistoryConfig.new(tmp_path, History(max_bytes=130))

    asyncio.run(append_entry("x" * 70, "conversation-1", config))
    asyncio.run(append_entry("y" * 70, "conversation-1", config))

    lines = (tmp_path / "history.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines
    assert json.loads(lines[-1])["text"] == "y" * 70
    assert (tmp_path / "history.jsonl").stat().st_size <= 130
