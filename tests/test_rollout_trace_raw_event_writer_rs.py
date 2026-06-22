import json

import pytest

from pycodex.rollout_trace import (
    ExecutionStatus,
    MANIFEST_FILE_NAME,
    PAYLOADS_DIR_NAME,
    RawPayloadKind,
    RawPayloadRef,
    RAW_EVENT_LOG_FILE_NAME,
    RawToolCallRequester,
    RawTraceEventContext,
    RawTraceEventPayload,
    REDUCED_STATE_FILE_NAME,
    RolloutStatus,
    TraceWriter,
    replay_bundle,
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_raw_payload_kind_and_ref_match_payload_rs_serde_shape(tmp_path):
    # Rust source: codex-rollout-trace/src/payload.rs
    # Contract: RawPayloadKind uses serde tag="type"; RawPayloadRef embeds that
    # tagged kind object alongside raw_payload_id and bundle-relative path.
    writer = TraceWriter.create(tmp_path, "trace-1", "rollout-1", "thread-root")

    payload_ref = writer.write_json_payload(
        RawPayloadKind.INFERENCE_REQUEST,
        {"input": [{"type": "message", "role": "user"}]},
    )

    assert payload_ref == RawPayloadRef(
        raw_payload_id="raw_payload:1",
        kind=RawPayloadKind.INFERENCE_REQUEST,
        path="payloads/1.json",
    )
    event_payload = RawTraceEventPayload.variant(
        "InferenceStarted",
        inference_call_id="inference-1",
        thread_id="thread-root",
        codex_turn_id="turn-1",
        model="gpt-test",
        provider_name="test-provider",
        request_payload=payload_ref,
    )
    writer.append(event_payload)

    assert event_payload.raw_payload_refs() == [payload_ref]
    log_event = read_jsonl(tmp_path / "trace.jsonl")[0]
    assert log_event["payload"]["request_payload"] == {
        "raw_payload_id": "raw_payload:1",
        "kind": {"type": "inference_request"},
        "path": "payloads/1.json",
    }


def test_raw_trace_event_payload_is_internally_tagged_and_flattened(tmp_path):
    # Rust source: codex-rollout-trace/src/raw_event.rs
    # Contract: RawTraceEventPayload uses serde tag="type"; variant fields are
    # flattened into the payload object rather than nested under "fields".
    writer = TraceWriter.create(tmp_path, "trace-1", "rollout-1", "thread-root")

    writer.append_with_context(
        RawTraceEventContext(thread_id="thread-root", codex_turn_id="turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id="tool-1",
            model_visible_call_id="call-1",
            code_mode_runtime_tool_id=None,
            requester=RawToolCallRequester.Model(),
            kind={"type": "exec_command"},
            summary={"label": "echo hello"},
            invocation_payload=None,
        ),
    )

    log_event = read_jsonl(tmp_path / "trace.jsonl")[0]
    assert log_event["schema_version"] == 1
    assert log_event["seq"] == 1
    assert log_event["rollout_id"] == "rollout-1"
    assert log_event["thread_id"] == "thread-root"
    assert log_event["codex_turn_id"] == "turn-1"
    assert log_event["payload"] == {
        "type": "tool_call_started",
        "tool_call_id": "tool-1",
        "model_visible_call_id": "call-1",
        "code_mode_runtime_tool_id": None,
        "requester": {"type": "model"},
        "kind": {"type": "exec_command"},
        "summary": {"label": "echo hello"},
        "invocation_payload": None,
    }
    assert "fields" not in log_event["payload"]


def test_raw_payload_refs_follow_raw_event_rs_variant_contract():
    # Rust source: codex-rollout-trace/src/raw_event.rs RawTraceEventPayload::raw_payload_refs
    # Contract: only reference-bearing fields named by the Rust match arms are
    # returned; arbitrary refs inside metadata are intentionally ignored.
    request_ref = RawPayloadRef("raw_payload:1", RawPayloadKind.INFERENCE_REQUEST, "payloads/1.json")
    result_ref = RawPayloadRef("raw_payload:2", RawPayloadKind.TOOL_RESULT, "payloads/2.json")
    metadata_ref = RawPayloadRef("raw_payload:3", RawPayloadKind.PROTOCOL_EVENT, "payloads/3.json")

    assert (
        RawTraceEventPayload.variant(
            "InferenceFailed",
            inference_call_id="inference-1",
            upstream_request_id=None,
            error="stream closed",
            partial_response_payload=request_ref,
        ).raw_payload_refs()
        == [request_ref]
    )
    assert (
        RawTraceEventPayload.variant(
            "Other",
            kind="debug",
            summary="captured",
            payloads=[request_ref, result_ref],
            metadata={"ignored_ref": metadata_ref},
        ).raw_payload_refs()
        == [request_ref, result_ref]
    )
    assert (
        RawTraceEventPayload.variant(
            "RolloutStarted",
            trace_id="trace-1",
            root_thread_id="thread-root",
            metadata={"ignored_ref": metadata_ref},
        ).raw_payload_refs()
        == []
    )


def test_writer_records_manifest_payloads_and_event_sequence(tmp_path):
    # Rust test: writer.rs writer_records_payload_refs_and_replays_rollout_status
    # Contract: TraceWriter creates the standard bundle layout, writes payload
    # files before events that reference them, assigns contiguous event sequence
    # numbers, and produces a bundle that replays into the expected reduced
    # rollout status, thread, turn, inference, and raw-payload registry state.
    writer = TraceWriter.create(tmp_path, "trace-1", "rollout-1", "thread-root")

    manifest = read_json(tmp_path / "manifest.json")
    assert manifest["schema_version"] == 1
    assert manifest["trace_id"] == "trace-1"
    assert manifest["rollout_id"] == "rollout-1"
    assert manifest["root_thread_id"] == "thread-root"
    assert manifest["raw_event_log"] == "trace.jsonl"
    assert manifest["payloads_dir"] == "payloads"

    writer.append(
        RawTraceEventPayload.variant(
            "RolloutStarted",
            trace_id="trace-1",
            root_thread_id="thread-root",
        )
    )
    metadata_payload = writer.write_json_payload(
        RawPayloadKind.PROTOCOL_EVENT,
        {"source": "test", "model": "gpt-test"},
    )
    writer.append(
        RawTraceEventPayload.variant(
            "ThreadStarted",
            thread_id="thread-root",
            agent_path="/root",
            metadata_payload=metadata_payload,
        )
    )
    writer.append(
        RawTraceEventPayload.variant(
            "CodexTurnStarted",
            codex_turn_id="turn-1",
            thread_id="thread-root",
        )
    )
    inference_request = writer.write_json_payload(
        RawPayloadKind.INFERENCE_REQUEST,
        {
            "model": "gpt-test",
            "provider_name": "test-provider",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                }
            ],
        },
    )
    writer.append(
        RawTraceEventPayload.variant(
            "InferenceStarted",
            inference_call_id="inference-1",
            thread_id="thread-root",
            codex_turn_id="turn-1",
            model="gpt-test",
            provider_name="test-provider",
            request_payload=inference_request,
        )
    )
    inference_response = writer.write_json_payload(
        RawPayloadKind.INFERENCE_RESPONSE,
        {
            "response_id": "resp-1",
            "output_items": [],
        },
    )
    writer.append(
        RawTraceEventPayload.variant(
            "InferenceCompleted",
            inference_call_id="inference-1",
            response_id="resp-1",
            upstream_request_id="req-1",
            response_payload=inference_response,
        )
    )
    writer.append(
        RawTraceEventPayload.variant(
            "CodexTurnEnded",
            codex_turn_id="turn-1",
            status=ExecutionStatus.COMPLETED,
        )
    )
    writer.append(RawTraceEventPayload.variant("RolloutEnded", status=RolloutStatus.COMPLETED))

    assert read_json(tmp_path / "payloads" / "1.json") == {
        "source": "test",
        "model": "gpt-test",
    }
    events = read_jsonl(tmp_path / "trace.jsonl")
    assert [event["seq"] for event in events] == [1, 2, 3, 4, 5, 6, 7]
    assert events[1]["payload"]["metadata_payload"]["path"] == "payloads/1.json"
    assert events[-1]["payload"] == {"type": "rollout_ended", "status": "completed"}

    rollout = replay_bundle(tmp_path)

    assert rollout.status == RolloutStatus.COMPLETED
    assert rollout.root_thread_id == "thread-root"
    assert rollout.threads["thread-root"].agent_path == "/root"
    assert rollout.codex_turns["turn-1"].thread_id == "thread-root"
    assert rollout.codex_turns["turn-1"].execution.status == ExecutionStatus.COMPLETED
    assert rollout.inference_calls["inference-1"].raw_request_payload_id == inference_request.raw_payload_id
    assert rollout.inference_calls["inference-1"].raw_response_payload_id == inference_response.raw_payload_id
    assert rollout.raw_payloads[metadata_payload.raw_payload_id].path == "payloads/1.json"


def test_other_raw_event_replay_errors_like_reducer_mod_rs(tmp_path):
    # Rust source: codex-rollout-trace/src/reducer/mod.rs TraceReducer::apply_event
    # Contract: raw payload refs are registered before the payload-specific
    # match, then RawTraceEventPayload::Other explicitly bails with the stable
    # reducer message because no semantic reducer arm exists yet.
    writer = TraceWriter.create(tmp_path, "trace-1", "rollout-1", "thread-root")
    payload_ref = writer.write_json_payload(
        RawPayloadKind.PROTOCOL_EVENT,
        {"kind": "debug"},
    )
    writer.append(
        RawTraceEventPayload.variant(
            "Other",
            kind="debug",
            summary="captured",
            payloads=[payload_ref],
            metadata={"note": "small metadata"},
        )
    )

    with pytest.raises(ValueError) as excinfo:
        replay_bundle(tmp_path)

    message = str(excinfo.value)
    assert "apply trace event line 1: raw trace event has no reducer implementation" in message
    assert ": other" not in message


def test_bundle_layout_constants_and_fixed_replay_log_name(tmp_path):
    # Rust source: codex-rollout-trace/src/bundle.rs and reducer/mod.rs
    # Contract: REDUCED_STATE_FILE_NAME is public, the manifest records the
    # standard local layout, and replay_bundle reads the fixed
    # RAW_EVENT_LOG_FILE_NAME rather than treating manifest.raw_event_log as an
    # override.
    assert REDUCED_STATE_FILE_NAME == "state.json"
    assert MANIFEST_FILE_NAME == "manifest.json"
    assert RAW_EVENT_LOG_FILE_NAME == "trace.jsonl"
    assert PAYLOADS_DIR_NAME == "payloads"

    writer = TraceWriter.create(tmp_path, "trace-1", "rollout-1", "thread-root")
    writer.append(RawTraceEventPayload.variant("RolloutEnded", status=RolloutStatus.COMPLETED))

    manifest_path = tmp_path / MANIFEST_FILE_NAME
    manifest = read_json(manifest_path)
    manifest["raw_event_log"] = "alternate.jsonl"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "alternate.jsonl").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "seq": 1,
                "wall_time_unix_ms": 1,
                "rollout_id": "rollout-1",
                "thread_id": None,
                "codex_turn_id": None,
                "payload": {"type": "rollout_ended", "status": "aborted"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert replay_bundle(tmp_path).status == RolloutStatus.COMPLETED
