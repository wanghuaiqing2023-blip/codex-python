import asyncio
import os
import re

import pytest

from pycodex.state.log_db import (
    LOG_BATCH_SIZE,
    LOG_FLUSH_INTERVAL_SECONDS,
    LOG_QUEUE_CAPACITY,
    LogDbLayer,
    LogSinkQueueConfig,
    MessageVisitor,
    SpanFieldVisitor,
    SpanLogContext,
    append_fields,
    current_process_log_uuid,
    event_thread_id,
    format_feedback_log_body,
    format_fields,
    log_entry_from_event,
)


class RecordingSink:
    def __init__(self) -> None:
        self.batches = []

    async def insert_logs(self, entries):
        self.batches.append(tuple(entries))


def test_log_sink_queue_config_defaults_and_normalization() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/log_db.rs::LogSinkQueueConfig
    # Behavior contract: defaults match Rust constants and normalization clamps
    # queue/batch sizes while replacing a zero flush interval with the default.
    assert LogSinkQueueConfig() == LogSinkQueueConfig(
        queue_capacity=LOG_QUEUE_CAPACITY,
        batch_size=LOG_BATCH_SIZE,
        flush_interval=LOG_FLUSH_INTERVAL_SECONDS,
    )

    normalized = LogSinkQueueConfig(
        queue_capacity=0,
        batch_size=0,
        flush_interval=0,
    ).normalized()

    assert normalized == LogSinkQueueConfig(
        queue_capacity=1,
        batch_size=1,
        flush_interval=LOG_FLUSH_INTERVAL_SECONDS,
    )


def test_process_log_uuid_is_pid_prefixed_and_stable() -> None:
    # Rust: current_process_log_uuid uses pid:{pid}:{uuid} and OnceLock.
    first = current_process_log_uuid()
    second = current_process_log_uuid()

    assert first == second
    assert re.fullmatch(rf"pid:{os.getpid()}:[0-9a-f-]{{36}}", first)


def test_visitors_capture_first_message_and_thread_id() -> None:
    # Rust visitors keep the first message/thread_id value they see.
    message = MessageVisitor()
    message.record_fields(
        [
            ("message", "first"),
            ("thread_id", 7),
            ("message", "second"),
            ("thread_id", "ignored"),
        ]
    )
    span = SpanFieldVisitor()
    span.record_fields([("thread_id", True), ("thread_id", "ignored")])

    assert message.message == "first"
    assert message.thread_id == "7"
    assert span.thread_id == "true"


def test_field_and_feedback_formatting_match_rust_shape() -> None:
    # Rust format_feedback_log_body walks spans from root and appends fields.
    root = SpanLogContext.from_fields("root", {"thread_id": "thread-1", "turn": 1})
    child = SpanLogContext("child", formatted_fields=append_fields("", {"phase": "run"}))

    assert format_fields({"message": "hello", "foo": 2, "ok": True}) == "hello foo=2 ok=true"
    assert append_fields("turn=1", {"phase": "run"}) == "turn=1 phase='run'"
    assert event_thread_id([root, child]) == "thread-1"
    assert (
        format_feedback_log_body({"message": "hello", "foo": 2}, [root, child])
        == "root{thread_id='thread-1' turn=1}:child{phase='run'}: hello foo=2"
    )


def test_log_entry_from_event_uses_message_thread_fallback_and_metadata() -> None:
    # Rust on_event builds LogEntry from event metadata, fields, spans, and process uuid.
    entry = log_entry_from_event(
        level="INFO",
        target="codex_state::log_db",
        fields={"message": "thread-scoped", "foo": 2},
        span_contexts=[SpanLogContext("feedback-thread", "turn=1", "thread-1")],
        module_path="codex_state::log_db",
        file="log_db.rs",
        line=7,
        process_uuid="process-1",
        ts=1,
        ts_nanos=2,
    )

    assert entry.ts == 1
    assert entry.ts_nanos == 2
    assert entry.level == "INFO"
    assert entry.target == "codex_state::log_db"
    assert entry.message == "thread-scoped"
    assert entry.feedback_log_body == "feedback-thread{turn=1}: thread-scoped foo=2"
    assert entry.thread_id == "thread-1"
    assert entry.process_uuid == "process-1"
    assert entry.module_path == "codex_state::log_db"
    assert entry.file == "log_db.rs"
    assert entry.line == 7


def test_bounded_queue_drops_new_entries_when_full_and_flushes() -> None:
    # Rust LogDbLayer uses try_send so a full queue drops later entries.
    sink = RecordingSink()
    layer = LogDbLayer.start_with_config(
        sink,
        LogSinkQueueConfig(queue_capacity=1, batch_size=8, flush_interval=60),
    )

    assert layer.emit_event(level="INFO", target="test", fields={"message": "first"}) is True
    assert layer.emit_event(level="INFO", target="test", fields={"message": "dropped"}) is False

    asyncio.run(layer.flush())

    assert len(sink.batches) == 1
    assert [entry.message for entry in sink.batches[0]] == ["first"]
    assert layer._queue == layer._queue.__class__()


def test_validation_rejects_invalid_config_and_fields() -> None:
    with pytest.raises(ValueError, match="flush_interval must be non-negative"):
        LogSinkQueueConfig(flush_interval=-1).normalized()
    with pytest.raises(TypeError, match="field name must be a string"):
        format_fields([(1, "value")])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="name must be a non-empty string"):
        SpanLogContext("")
