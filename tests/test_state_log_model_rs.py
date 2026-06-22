import pytest

from pycodex.state import LogEntry, LogQuery, LogRow


def test_log_entry_preserves_rust_fields_and_mapping_shape() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/log.rs::LogEntry
    # Behavior contract: LogEntry owns serializable log entry fields.
    entry = LogEntry(
        ts=1,
        ts_nanos=2,
        level="INFO",
        target="codex",
        message="hello",
        feedback_log_body="body",
        thread_id="thread-1",
        process_uuid="process-1",
        module_path="module",
        file="file.py",
        line=42,
    )

    assert entry.to_mapping() == {
        "ts": 1,
        "ts_nanos": 2,
        "level": "INFO",
        "target": "codex",
        "message": "hello",
        "feedback_log_body": "body",
        "thread_id": "thread-1",
        "process_uuid": "process-1",
        "module_path": "module",
        "file": "file.py",
        "line": 42,
    }


def test_log_entry_rejects_invalid_i64_and_string_fields() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/log.rs::LogEntry
    # Behavior contract: Python enforces Rust i64 and string field boundaries.
    with pytest.raises(TypeError, match="ts must be an integer"):
        LogEntry(ts=True, ts_nanos=0, level="INFO", target="codex")
    with pytest.raises(ValueError, match="line must fit in a signed 64-bit integer"):
        LogEntry(ts=0, ts_nanos=0, level="INFO", target="codex", line=2**63)
    with pytest.raises(TypeError, match="level must be a string"):
        LogEntry(ts=0, ts_nanos=0, level=None, target="codex")  # type: ignore[arg-type]


def test_log_row_from_mapping_converts_row_shape() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/log.rs::LogRow
    # Behavior contract: LogRow mirrors the row-shaped fields derived by sqlx.
    row = LogRow.from_mapping(
        {
            "id": 7,
            "ts": 10,
            "ts_nanos": 20,
            "level": "WARN",
            "target": "codex_state",
            "message": None,
            "thread_id": "thread-1",
            "process_uuid": None,
            "file": "state.rs",
            "line": 9,
        }
    )

    assert row == LogRow(
        id=7,
        ts=10,
        ts_nanos=20,
        level="WARN",
        target="codex_state",
        message=None,
        thread_id="thread-1",
        process_uuid=None,
        file="state.rs",
        line=9,
    )


def test_log_row_from_mapping_rejects_invalid_row_fields() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/log.rs::LogRow
    # Behavior contract: invalid row fields fail rather than silently coercing.
    with pytest.raises(TypeError, match="id must be an integer"):
        LogRow.from_mapping({"id": "1", "ts": 0, "ts_nanos": 0, "level": "INFO", "target": "x"})
    with pytest.raises(TypeError, match="message must be a string"):
        LogRow.from_mapping({"id": 1, "ts": 0, "ts_nanos": 0, "level": "INFO", "target": "x", "message": 1})


def test_log_query_default_matches_rust_default() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/log.rs::LogQuery
    # Behavior contract: derived Default gives empty vectors, None filters, and false booleans.
    assert LogQuery() == LogQuery(
        levels_upper=(),
        from_ts=None,
        to_ts=None,
        module_like=(),
        file_like=(),
        thread_ids=(),
        search=None,
        include_threadless=False,
        after_id=None,
        limit=None,
        descending=False,
    )


def test_log_query_normalizes_sequences_and_validates_bounds() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/log.rs::LogQuery
    # Behavior contract: Vec<String> fields become string sequences and limit is Option<usize>.
    query = LogQuery(
        levels_upper=["INFO", "WARN"],
        from_ts=1,
        to_ts=2,
        module_like=["state"],
        file_like=["runtime"],
        thread_ids=["thread-1"],
        search="hello",
        include_threadless=True,
        after_id=3,
        limit=50,
        descending=True,
    )

    assert query.levels_upper == ("INFO", "WARN")
    assert query.module_like == ("state",)
    assert query.file_like == ("runtime",)
    assert query.thread_ids == ("thread-1",)
    assert query.limit == 50

    with pytest.raises(ValueError, match="limit must be non-negative"):
        LogQuery(limit=-1)
    with pytest.raises(TypeError, match="levels_upper must be a sequence of strings"):
        LogQuery(levels_upper="INFO")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="include_threadless must be a bool"):
        LogQuery(include_threadless=1)  # type: ignore[arg-type]
