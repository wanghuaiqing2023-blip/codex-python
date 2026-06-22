import pytest

from pycodex.rollout_trace import (
    CompactionCheckpointTracePayload,
    ExecutionStatus,
    RawPayloadKind,
    RawTraceEventContext,
    RawTraceEventPayload,
    ThreadTraceContext,
    TraceWriter,
    replay_bundle,
)
from test_rollout_trace_thread_rs import metadata, single_bundle_dir


def test_disabled_compaction_context_records_nothing(tmp_path):
    # Rust test: thread_tests.rs disabled_thread_context_accepts_trace_calls_without_writing
    trace = ThreadTraceContext.disabled()

    attempt = trace.compaction_trace_context(
        "turn-1", "compaction-1", "gpt-test", "test-provider"
    ).start_attempt({"kind": "compaction"})
    attempt.record_completed([])
    attempt.record_failed("compaction failed")
    trace.compaction_trace_context(
        "turn-1", "compaction-1", "gpt-test", "test-provider"
    ).record_installed(CompactionCheckpointTracePayload())

    assert not attempt.is_enabled()
    assert list(tmp_path.iterdir()) == []


def test_enabled_compaction_attempt_records_and_replays_request_lifecycle(tmp_path):
    # Rust source: compaction.rs start_attempt/record_completed and
    # reducer/compaction.rs start_compaction_request/complete_compaction_request.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    compaction = trace.compaction_trace_context(
        "turn-1", "compaction-1", "gpt-test", "test-provider"
    )

    attempt = compaction.start_attempt({"kind": "compaction", "input": []})
    attempt.record_completed([])

    replayed = replay_bundle(single_bundle_dir(tmp_path))
    request = replayed.compaction_requests[attempt.compaction_request_id]
    assert request.compaction_id == "compaction-1"
    assert request.thread_id == "thread-root"
    assert request.codex_turn_id == "turn-1"
    assert request.execution.status == ExecutionStatus.COMPLETED
    assert request.model == "gpt-test"
    assert request.provider_name == "test-provider"
    assert request.raw_request_payload_id == "raw_payload:2"
    assert request.raw_response_payload_id == "raw_payload:3"


def test_compaction_failed_request_replays_failed_without_response_payload(tmp_path):
    # Rust source: compaction.rs record_failed and reducer/compaction.rs
    # complete_compaction_request with failed status and no response payload.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.compaction_trace_context(
        "turn-1", "compaction-1", "gpt-test", "test-provider"
    ).start_attempt({"kind": "compaction"})

    attempt.record_failed("compact endpoint failed")

    replayed = replay_bundle(single_bundle_dir(tmp_path))
    request = replayed.compaction_requests[attempt.compaction_request_id]
    assert request.execution.status == ExecutionStatus.FAILED
    assert request.raw_response_payload_id is None


def test_compaction_installed_records_checkpoint_and_request_ids(tmp_path):
    # Rust source: compaction.rs record_installed and reducer/compaction.rs
    # reduce_compaction_installed_event request-id association.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    compaction = trace.compaction_trace_context(
        "turn-1", "compaction-1", "gpt-test", "test-provider"
    )
    attempt = compaction.start_attempt({"kind": "compaction"})
    attempt.record_completed([])

    compaction.record_installed(
        CompactionCheckpointTracePayload(
            input_history=[{"type": "message", "role": "user"}],
            replacement_history=[{"type": "message", "role": "assistant"}],
        )
    )

    replayed = replay_bundle(single_bundle_dir(tmp_path))
    installed = replayed.compactions["compaction-1"]
    assert installed.thread_id == "thread-root"
    assert installed.codex_turn_id == "turn-1"
    assert installed.request_ids == [attempt.compaction_request_id]
    assert installed.marker_item_id in replayed.conversation_items
    assert "raw_payload:4" in replayed.raw_payloads


def test_compaction_reducer_rejects_unknown_request_and_mismatched_compaction(tmp_path):
    # Rust source: reducer/compaction.rs completion unknown-request and
    # compaction-id mismatch guards.
    unknown = tmp_path / "unknown"
    writer = TraceWriter.create(unknown, "trace-1", "rollout-1", "thread-root")
    writer.append(
        RawTraceEventPayload.variant(
            "CompactionRequestFailed",
            compaction_id="compaction-1",
            compaction_request_id="compaction_request:missing",
            error="failed",
        )
    )
    with pytest.raises(ValueError, match="unknown request compaction_request:missing"):
        replay_bundle(unknown)

    mismatched = tmp_path / "mismatched"
    trace = ThreadTraceContext.start_root_in_root_for_test(mismatched, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.compaction_trace_context(
        "turn-1", "compaction-start", "gpt-test", "test-provider"
    ).start_attempt({"kind": "compaction"})
    trace.writer.append_with_context(
        RawTraceEventContext(thread_id="thread-root", codex_turn_id="turn-1"),
        RawTraceEventPayload.variant(
            "CompactionRequestFailed",
            compaction_id="compaction-other",
            compaction_request_id=attempt.compaction_request_id,
            error="failed",
        ),
    )
    with pytest.raises(ValueError, match="used compaction compaction-other"):
        replay_bundle(single_bundle_dir(mismatched))


def test_compaction_reducer_rejects_duplicate_request_start(tmp_path):
    # Rust source: reducer/compaction.rs start_compaction_request
    # Contract: a compaction_request_id may only be started once.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.compaction_trace_context(
        "turn-1", "compaction-1", "gpt-test", "test-provider"
    ).start_attempt({"kind": "compaction"})
    duplicate_request = trace.writer.write_json_payload(
        RawPayloadKind.COMPACTION_REQUEST,
        {"kind": "duplicate"},
    )

    trace.writer.append_with_context(
        RawTraceEventContext(thread_id="thread-root", codex_turn_id="turn-1"),
        RawTraceEventPayload.variant(
            "CompactionRequestStarted",
            compaction_id="compaction-1",
            compaction_request_id=attempt.compaction_request_id,
            thread_id="thread-root",
            codex_turn_id="turn-1",
            model="gpt-test",
            provider_name="test-provider",
            request_payload=duplicate_request,
        ),
    )

    with pytest.raises(ValueError, match="duplicate compaction request start"):
        replay_bundle(single_bundle_dir(tmp_path))


def test_compaction_install_rejects_duplicate_unknown_turn_and_thread_mismatch(tmp_path):
    # Rust source: reducer/compaction.rs reduce_compaction_installed_event
    # Contract: installed compaction ids are unique and install events must
    # reference an existing Codex turn owned by the event thread.
    duplicate = tmp_path / "duplicate"
    trace = ThreadTraceContext.start_root_in_root_for_test(duplicate, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    compaction = trace.compaction_trace_context(
        "turn-1", "compaction-1", "gpt-test", "test-provider"
    )
    checkpoint = CompactionCheckpointTracePayload(
        input_history=[{"type": "message", "role": "user"}],
        replacement_history=[{"type": "message", "role": "assistant"}],
    )
    compaction.record_installed(checkpoint)
    compaction.record_installed(checkpoint)
    with pytest.raises(ValueError, match="duplicate compaction install for compaction-1"):
        replay_bundle(single_bundle_dir(duplicate))

    unknown_turn = tmp_path / "unknown-turn"
    trace = ThreadTraceContext.start_root_in_root_for_test(unknown_turn, metadata("thread-root"))
    payload = trace.writer.write_json_payload(RawPayloadKind.COMPACTION_CHECKPOINT, checkpoint)
    trace.writer.append_with_context(
        RawTraceEventContext(thread_id="thread-root", codex_turn_id="turn-missing"),
        RawTraceEventPayload.variant(
            "CompactionInstalled",
            compaction_id="compaction-1",
            checkpoint_payload=payload,
        ),
    )
    with pytest.raises(ValueError, match="referenced unknown codex turn turn-missing"):
        replay_bundle(single_bundle_dir(unknown_turn))

    mismatched_thread = tmp_path / "mismatched-thread"
    root = ThreadTraceContext.start_root_in_root_for_test(mismatched_thread, metadata("thread-root"))
    root.record_codex_turn_started("turn-root")
    child = root.start_child_thread_trace_or_disabled(metadata("thread-child", agent_path="/root/child"))
    payload = root.writer.write_json_payload(RawPayloadKind.COMPACTION_CHECKPOINT, checkpoint)
    root.writer.append_with_context(
        RawTraceEventContext(thread_id="thread-child", codex_turn_id="turn-root"),
        RawTraceEventPayload.variant(
            "CompactionInstalled",
            compaction_id="compaction-1",
            checkpoint_payload=payload,
        ),
    )
    assert child.is_enabled()
    with pytest.raises(ValueError, match="used thread thread-child, but codex turn turn-root belongs to thread-root"):
        replay_bundle(single_bundle_dir(mismatched_thread))


def test_compaction_install_rejects_malformed_checkpoint_payload(tmp_path):
    # Rust source: reducer/conversation.rs reduce_compaction_checkpoint
    # Contract: compaction checkpoint payloads must contain array
    # input_history and replacement_history fields.
    missing_input = tmp_path / "missing-input"
    trace = ThreadTraceContext.start_root_in_root_for_test(missing_input, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    payload = trace.writer.write_json_payload(
        RawPayloadKind.COMPACTION_CHECKPOINT,
        {"replacement_history": []},
    )
    trace.writer.append_with_context(
        RawTraceEventContext(thread_id="thread-root", codex_turn_id="turn-1"),
        RawTraceEventPayload.variant(
            "CompactionInstalled",
            compaction_id="compaction-1",
            checkpoint_payload=payload,
        ),
    )
    with pytest.raises(ValueError, match="did not contain array input_history"):
        replay_bundle(single_bundle_dir(missing_input))

    missing_replacement = tmp_path / "missing-replacement"
    trace = ThreadTraceContext.start_root_in_root_for_test(missing_replacement, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    payload = trace.writer.write_json_payload(
        RawPayloadKind.COMPACTION_CHECKPOINT,
        {"input_history": []},
    )
    trace.writer.append_with_context(
        RawTraceEventContext(thread_id="thread-root", codex_turn_id="turn-1"),
        RawTraceEventPayload.variant(
            "CompactionInstalled",
            compaction_id="compaction-1",
            checkpoint_payload=payload,
        ),
    )
    with pytest.raises(ValueError, match="did not contain array replacement_history"):
        replay_bundle(single_bundle_dir(missing_replacement))
