import pytest

from pycodex.rollout_trace import (
    ExecutionStatus,
    RawTraceEventContext,
    RawTraceEventPayload,
    RolloutStatus,
    ThreadTraceContext,
    TraceWriter,
    replay_bundle,
)
from test_rollout_trace_thread_rs import metadata, single_bundle_dir


def test_replay_bundle_reduces_root_thread_lifecycle(tmp_path):
    # Rust tests:
    # - thread_tests.rs create_in_root_writes_replayable_lifecycle_events
    # - reducer/thread.rs start_thread/end_thread lifecycle contract
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    trace.record_codex_turn_started("turn-1")
    trace.writer.append_with_context(
        RawTraceEventContext(thread_id="thread-root", codex_turn_id="turn-1"),
        RawTraceEventPayload.variant(
            "CodexTurnEnded",
            codex_turn_id="turn-1",
            status=ExecutionStatus.COMPLETED,
        ),
    )
    trace.record_ended(RolloutStatus.COMPLETED)

    replayed = replay_bundle(single_bundle_dir(tmp_path))
    assert replayed.status == RolloutStatus.COMPLETED
    assert replayed.root_thread_id == "thread-root"
    assert replayed.threads["thread-root"].agent_path == "/root"
    assert replayed.threads["thread-root"].origin.type == "root"
    assert replayed.threads["thread-root"].execution.status == ExecutionStatus.COMPLETED
    assert replayed.threads["thread-root"].default_model == "gpt-test"
    assert replayed.codex_turns["turn-1"].thread_id == "thread-root"
    assert replayed.codex_turns["turn-1"].execution.status == ExecutionStatus.COMPLETED
    assert list(replayed.raw_payloads) == ["raw_payload:1"]


def test_replay_bundle_reduces_spawned_thread_without_ending_rollout(tmp_path):
    # Rust tests:
    # - thread_tests.rs spawned_thread_start_appends_to_root_bundle
    # - reducer/thread.rs prefers SessionSource thread_spawn metadata for child identity
    root_trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    child_trace = root_trace.start_child_thread_trace_or_disabled(
        metadata(
            "thread-child",
            agent_path="/root/denormalized",
            task_name="fallback_task",
            nickname="Kepler",
            agent_role="fallback_role",
            session_source={
                "subagent": {
                    "thread_spawn": {
                        "parent_thread_id": "thread-root",
                        "agent_path": "/root/repo_file_counter",
                        "task_name": "repo_file_counter",
                        "agent_role": "worker",
                    }
                }
            },
        )
    )
    child_trace.record_ended(RolloutStatus.COMPLETED)

    replayed = replay_bundle(single_bundle_dir(tmp_path))
    child = replayed.threads["thread-child"]
    assert replayed.status == RolloutStatus.RUNNING
    assert child.agent_path == "/root/repo_file_counter"
    assert child.nickname == "Kepler"
    assert child.origin.type == "spawned"
    assert child.origin.parent_thread_id == "thread-root"
    assert child.origin.spawn_edge_id == "edge:spawn:thread-root:thread-child"
    assert child.origin.task_name == "repo_file_counter"
    assert child.origin.agent_role == "worker"
    assert child.execution.status == ExecutionStatus.COMPLETED
    assert list(replayed.raw_payloads) == ["raw_payload:1", "raw_payload:2"]


def test_replay_bundle_rejects_duplicate_thread_start(tmp_path):
    # Rust source: reducer/thread.rs start_thread duplicate guard.
    writer = TraceWriter.create(tmp_path, "trace-1", "rollout-1", "thread-root")
    for _ in range(2):
        writer.append(
            RawTraceEventPayload.variant(
                "ThreadStarted",
                thread_id="thread-root",
                agent_path="/root",
                metadata_payload=None,
            )
        )

    with pytest.raises(ValueError, match="duplicate thread start for thread-root"):
        replay_bundle(tmp_path)


def test_replay_bundle_rejects_unknown_and_mismatched_codex_turn_end(tmp_path):
    # Rust source: reducer/thread.rs end_codex_turn unknown-turn and thread-mismatch guards.
    unknown = tmp_path / "unknown"
    writer = TraceWriter.create(unknown, "trace-1", "rollout-1", "thread-root")
    writer.append_with_context(
        RawTraceEventContext(thread_id="thread-root", codex_turn_id="turn-missing"),
        RawTraceEventPayload.variant(
            "CodexTurnEnded",
            codex_turn_id="turn-missing",
            status=ExecutionStatus.COMPLETED,
        ),
    )
    with pytest.raises(ValueError, match="unknown turn turn-missing"):
        replay_bundle(unknown)

    mismatched = tmp_path / "mismatched"
    writer = TraceWriter.create(mismatched, "trace-2", "rollout-2", "thread-root")
    writer.append(
        RawTraceEventPayload.variant(
            "ThreadStarted",
            thread_id="thread-root",
            agent_path="/root",
            metadata_payload=None,
        )
    )
    writer.append(
        RawTraceEventPayload.variant(
            "CodexTurnStarted",
            codex_turn_id="turn-1",
            thread_id="thread-root",
        )
    )
    writer.append_with_context(
        RawTraceEventContext(thread_id="thread-other", codex_turn_id="turn-1"),
        RawTraceEventPayload.variant(
            "CodexTurnEnded",
            codex_turn_id="turn-1",
            status=ExecutionStatus.COMPLETED,
        ),
    )
    with pytest.raises(ValueError, match="used thread thread-other"):
        replay_bundle(mismatched)
