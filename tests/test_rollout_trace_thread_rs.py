import json
from pathlib import Path

from pycodex.rollout_trace import (
    AgentResultTracePayload,
    RawPayloadKind,
    RolloutStatus,
    ThreadStartedTraceMetadata,
    ThreadTraceContext,
)


def metadata(
    thread_id: str,
    *,
    agent_path: str = "/root",
    task_name: str | None = None,
    nickname: str | None = None,
    agent_role: str | None = None,
    session_source: object = "exec",
) -> ThreadStartedTraceMetadata:
    return ThreadStartedTraceMetadata(
        thread_id=thread_id,
        agent_path=agent_path,
        task_name=task_name,
        nickname=nickname,
        agent_role=agent_role,
        session_source=session_source,
        cwd=Path("/workspace"),
        rollout_path=Path("/tmp/rollout.jsonl"),
        model="gpt-test",
        provider_name="test-provider",
        approval_policy="never",
        sandbox_policy="danger-full-access",
    )


def single_bundle_dir(root: Path) -> Path:
    entries = sorted(path for path in root.iterdir() if path.is_dir())
    assert len(entries) == 1
    return entries[0]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_create_in_root_writes_thread_lifecycle_events(tmp_path):
    # Rust test: thread_tests.rs create_in_root_writes_replayable_lifecycle_events
    # Contract covered here before reducer replay: root tracing creates one
    # bundle, writes RolloutStarted/ThreadStarted with session metadata, and
    # root record_ended emits both ThreadEnded and RolloutEnded.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    assert trace.is_enabled()
    trace.record_ended(RolloutStatus.COMPLETED)

    bundle = single_bundle_dir(tmp_path)
    events = read_jsonl(bundle / "trace.jsonl")
    assert [event["payload"]["type"] for event in events] == [
        "rollout_started",
        "thread_started",
        "thread_ended",
        "rollout_ended",
    ]
    assert events[0]["payload"]["root_thread_id"] == "thread-root"
    assert events[1]["payload"]["thread_id"] == "thread-root"
    assert events[1]["payload"]["agent_path"] == "/root"
    assert events[1]["payload"]["metadata_payload"] == {
        "raw_payload_id": "raw_payload:1",
        "kind": {"type": RawPayloadKind.SESSION_METADATA.value},
        "path": "payloads/1.json",
    }
    assert events[2]["payload"] == {
        "type": "thread_ended",
        "thread_id": "thread-root",
        "status": "completed",
    }
    assert events[3]["payload"] == {"type": "rollout_ended", "status": "completed"}

    session_metadata = read_json(bundle / "payloads" / "1.json")
    assert session_metadata["thread_id"] == "thread-root"
    assert session_metadata["agent_path"] == "/root"
    assert session_metadata["model"] == "gpt-test"
    assert session_metadata["provider_name"] == "test-provider"


def test_spawned_thread_start_appends_to_root_bundle(tmp_path):
    # Rust test: thread_tests.rs spawned_thread_start_appends_to_root_bundle
    # Contract: child traces reuse the root writer/bundle, write their own
    # ThreadStarted metadata, and child record_ended does not end the rollout.
    root_trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    child_trace = root_trace.start_child_thread_trace_or_disabled(
        metadata(
            "thread-child",
            agent_path="/root/repo_file_counter",
            task_name="repo_file_counter",
            nickname="Kepler",
            agent_role="worker",
            session_source={
                "subagent": {
                    "thread_spawn": {
                        "parent_thread_id": "thread-root",
                        "depth": 1,
                        "agent_path": "/root/repo_file_counter",
                        "agent_nickname": "Kepler",
                        "agent_role": "worker",
                    }
                }
            },
        )
    )
    child_trace.record_ended(RolloutStatus.COMPLETED)

    bundle = single_bundle_dir(tmp_path)
    events = read_jsonl(bundle / "trace.jsonl")
    assert [event["payload"]["type"] for event in events] == [
        "rollout_started",
        "thread_started",
        "thread_started",
        "thread_ended",
    ]
    assert events[2]["payload"]["thread_id"] == "thread-child"
    assert events[2]["payload"]["agent_path"] == "/root/repo_file_counter"
    assert events[3]["payload"]["thread_id"] == "thread-child"
    assert not any(event["payload"]["type"] == "rollout_ended" for event in events)

    child_metadata_ref = events[2]["payload"]["metadata_payload"]
    child_metadata = read_json(bundle / child_metadata_ref["path"])
    assert child_metadata["task_name"] == "repo_file_counter"
    assert child_metadata["nickname"] == "Kepler"
    assert child_metadata["agent_role"] == "worker"
    assert child_metadata["session_source"]["subagent"]["thread_spawn"]["parent_thread_id"] == "thread-root"


def test_disabled_thread_context_accepts_trace_calls_without_writing_or_building_dispatch(tmp_path):
    # Rust test: thread_tests.rs disabled_thread_context_accepts_trace_calls_without_writing
    # Rust source: thread.rs code_cell_trace_context/inference_trace_context/
    # compaction_trace_context
    # Contract: disabled contexts are no-op handles, delegated trace handles
    # stay disabled, and lazy dispatch payload construction is not evaluated
    # when tracing is disabled.
    trace = ThreadTraceContext.disabled()
    built_dispatch_invocation = False

    def build_invocation():
        nonlocal built_dispatch_invocation
        built_dispatch_invocation = True
        return None

    trace.record_ended(RolloutStatus.COMPLETED)
    trace.record_agent_result_interaction(
        "turn-1",
        "thread-parent",
        AgentResultTracePayload("/root/child", "done", {"type": "completed", "message": "done"}),
    )
    dispatch_trace = trace.start_tool_dispatch_trace(build_invocation)
    code_cell_trace = trace.start_code_cell_trace("turn-1", "runtime-cell-1", "call-1", "1 + 1")
    existing_code_cell_trace = trace.code_cell_trace_context("turn-1", "runtime-cell-1")
    inference_trace = trace.inference_trace_context("turn-1", "gpt-test", "test-provider")
    compaction_trace = trace.compaction_trace_context(
        "turn-1",
        "compaction-1",
        "gpt-test",
        "test-provider",
    )

    assert not trace.is_enabled()
    assert not dispatch_trace.is_enabled()
    assert not code_cell_trace.is_enabled()
    assert not existing_code_cell_trace.is_enabled()
    assert not inference_trace.is_enabled()
    assert not compaction_trace.is_enabled()
    assert not built_dispatch_invocation
    assert list(tmp_path.iterdir()) == []


def test_record_codex_turn_started_uses_thread_context(tmp_path):
    # Rust source: thread.rs record_codex_turn_started
    # Contract: explicit turn-start events are appended with the enabled
    # thread's envelope context and thread id.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    trace.record_codex_turn_started("turn-1")

    event = read_jsonl(single_bundle_dir(tmp_path) / "trace.jsonl")[-1]
    assert event["thread_id"] == "thread-root"
    assert event["codex_turn_id"] == "turn-1"
    assert event["payload"] == {
        "type": "codex_turn_started",
        "codex_turn_id": "turn-1",
        "thread_id": "thread-root",
    }


def test_delegated_trace_contexts_use_thread_and_turn_context(tmp_path):
    # Rust source: thread.rs start_code_cell_trace, code_cell_trace_context,
    # inference_trace_context, and compaction_trace_context
    # Contract: enabled ThreadTraceContext delegates reusable child trace
    # contexts with the same writer, thread id, and codex turn id; starting a
    # code cell immediately records CodeCellStarted.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    inference = trace.inference_trace_context("turn-1", "gpt-test", "test-provider")
    inference_attempt = inference.start_attempt()
    inference_attempt.record_started({"input": [], "model": "gpt-test"})

    compaction = trace.compaction_trace_context(
        "turn-1",
        "compaction-1",
        "gpt-test",
        "test-provider",
    )
    compaction_attempt = compaction.start_attempt({"input": ["summary seed"]})

    code_cell = trace.start_code_cell_trace(
        "turn-1",
        "runtime-cell-1",
        "call-code-1",
        "console.log(1)",
    )
    code_cell.record_initial_response({"type": "yielded", "output": "waiting"})
    existing_code_cell = trace.code_cell_trace_context("turn-1", "runtime-cell-1")
    existing_code_cell.record_ended({"type": "result", "error_text": None, "output": "done"})

    assert inference.is_enabled()
    assert inference_attempt.is_enabled()
    assert compaction.is_enabled()
    assert compaction_attempt.is_enabled()
    assert code_cell.is_enabled()
    assert existing_code_cell.is_enabled()

    events = read_jsonl(single_bundle_dir(tmp_path) / "trace.jsonl")
    delegated_events = [
        event
        for event in events
        if event["payload"]["type"]
        in {
            "inference_started",
            "compaction_request_started",
            "code_cell_started",
            "code_cell_initial_response",
            "code_cell_ended",
        }
    ]
    assert [event["payload"]["type"] for event in delegated_events] == [
        "inference_started",
        "compaction_request_started",
        "code_cell_started",
        "code_cell_initial_response",
        "code_cell_ended",
    ]
    assert {event["thread_id"] for event in delegated_events} == {"thread-root"}
    assert {event["codex_turn_id"] for event in delegated_events} == {"turn-1"}

    inference_started = delegated_events[0]["payload"]
    assert inference_started["thread_id"] == "thread-root"
    assert inference_started["codex_turn_id"] == "turn-1"
    assert inference_started["model"] == "gpt-test"
    assert inference_started["provider_name"] == "test-provider"
    assert inference_started["request_payload"]["kind"] == {"type": RawPayloadKind.INFERENCE_REQUEST.value}

    compaction_started = delegated_events[1]["payload"]
    assert compaction_started["compaction_id"] == "compaction-1"
    assert compaction_started["thread_id"] == "thread-root"
    assert compaction_started["codex_turn_id"] == "turn-1"
    assert compaction_started["model"] == "gpt-test"
    assert compaction_started["provider_name"] == "test-provider"
    assert compaction_started["request_payload"]["kind"] == {"type": RawPayloadKind.COMPACTION_REQUEST.value}

    assert delegated_events[2]["payload"] == {
        "type": "code_cell_started",
        "runtime_cell_id": "runtime-cell-1",
        "model_visible_call_id": "call-code-1",
        "source_js": "console.log(1)",
    }
    assert delegated_events[3]["payload"]["runtime_cell_id"] == "runtime-cell-1"
    assert delegated_events[3]["payload"]["status"] == "yielded"
    assert delegated_events[3]["payload"]["response_payload"]["kind"] == {"type": RawPayloadKind.TOOL_RESULT.value}
    assert delegated_events[4]["payload"]["runtime_cell_id"] == "runtime-cell-1"
    assert delegated_events[4]["payload"]["status"] == "completed"
    assert delegated_events[4]["payload"]["response_payload"]["kind"] == {"type": RawPayloadKind.TOOL_RESULT.value}
