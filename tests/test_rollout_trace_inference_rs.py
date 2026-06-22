import uuid

from pycodex.rollout_trace import (
    ConversationItemKind,
    ConversationPart,
    ExecutionStatus,
    INFERENCE_CALL_ID_HEADER,
    ProducerRef,
    RawPayloadKind,
    RawTraceEventContext,
    RawTraceEventPayload,
    ThreadTraceContext,
    replay_bundle,
    trace_response_item_json,
)
from test_rollout_trace_thread_rs import metadata, read_json, single_bundle_dir


def test_disabled_attempt_adds_no_request_headers():
    # Rust test: inference.rs disabled_attempt_adds_no_request_headers
    attempt = ThreadTraceContext.disabled().inference_trace_context(
        "turn-1", "gpt-test", "test-provider"
    ).start_attempt()
    headers = {}

    attempt.add_request_headers(headers)

    assert headers == {}


def test_enabled_attempt_records_replayable_inference_attempt(tmp_path):
    # Rust test: inference.rs enabled_context_records_replayable_inference_attempt
    # Contract: enabled attempts add a propagation header, write request/response
    # payloads, and replay into an InferenceCall lifecycle object.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    headers = {}

    attempt.add_request_headers(headers)
    attempt.record_started(
        {
            "model": "gpt-test",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                }
            ],
        }
    )
    attempt.record_completed("resp-1", "req-1", None, [])

    assert INFERENCE_CALL_ID_HEADER in headers
    inference_call_id = headers[INFERENCE_CALL_ID_HEADER]
    replayed = replay_bundle(single_bundle_dir(tmp_path))
    inference = replayed.inference_calls[inference_call_id]
    assert inference.thread_id == "thread-root"
    assert inference.codex_turn_id == "turn-1"
    assert inference.execution.status == ExecutionStatus.COMPLETED
    assert inference.model == "gpt-test"
    assert inference.provider_name == "test-provider"
    assert inference.response_id == "resp-1"
    assert inference.upstream_request_id == "req-1"
    assert inference.raw_request_payload_id == "raw_payload:2"
    assert inference.raw_response_payload_id == "raw_payload:3"
    assert list(replayed.raw_payloads) == ["raw_payload:1", "raw_payload:2", "raw_payload:3"]


def test_enabled_attempt_adds_inference_request_header(tmp_path):
    # Rust test: inference.rs enabled_attempt_adds_inference_request_header
    # Contract: enabled attempts add x-codex-inference-call-id as the attempt UUID.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    headers = {}

    attempt.add_request_headers(headers)

    header = headers[INFERENCE_CALL_ID_HEADER]
    assert header == attempt.inference_call_id
    assert str(uuid.UUID(header)) == header


def test_traced_response_item_preserves_reasoning_content_omitted_by_normal_serializer(tmp_path):
    # Rust test: inference.rs traced_response_item_preserves_reasoning_content_omitted_by_normal_serializer
    # Contract: trace_response_item_json keeps reasoning.content that normal
    # protocol serialization omits for future request construction.
    item = {
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": "summary"}],
        "content": [{"type": "text", "text": "raw reasoning"}],
        "encrypted_content": "encoded",
    }
    normal = {key: value for key, value in item.items() if key != "content"}

    traced = trace_response_item_json(item)

    assert normal.get("content") is None
    assert traced == item

    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started({"input": []})
    attempt.record_completed("resp-1", "req-1", None, [item])

    replayed = replay_bundle(single_bundle_dir(tmp_path))
    payload_ref = replayed.raw_payloads[next(iter(replayed.inference_calls.values())).raw_response_payload_id]
    payload_body = read_json(single_bundle_dir(tmp_path) / payload_ref.path)
    assert payload_body["output_items"] == [item]


def test_attempt_terminal_event_is_recorded_once(tmp_path):
    # Rust source: inference.rs InferenceTraceAttempt::take_terminal_attempt
    # Contract: only the first terminal event is recorded for a concrete attempt.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started({"input": []})

    attempt.record_failed("first failure", "req-1", [])
    attempt.record_completed("resp-late", "req-late", None, [])

    replayed = replay_bundle(single_bundle_dir(tmp_path))
    inference = next(iter(replayed.inference_calls.values()))
    assert inference.execution.status == ExecutionStatus.FAILED
    assert inference.upstream_request_id == "req-1"
    assert inference.response_id is None
    assert inference.raw_response_payload_id is None


def test_cancelled_inference_reduces_partial_response_items(tmp_path):
    # Rust test: reducer/inference_tests.rs cancelled_inference_reduces_partial_response_items
    # Contract: an InferenceCancelled event with a partial response payload
    # closes the inference as cancelled and reduces observed output items into
    # conversation items produced by that inference call.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started(
        {
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "draft"}],
                }
            ]
        }
    )
    partial = trace.writer.write_json_payload(
        RawPayloadKind.INFERENCE_RESPONSE,
        {
            "response_id": None,
            "token_usage": None,
            "output_items": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "partial"}],
                }
            ],
        },
    )

    trace.writer.append(
        RawTraceEventPayload.variant(
            "InferenceCancelled",
            inference_call_id=attempt.inference_call_id,
            upstream_request_id="req-cancelled",
            reason="test interruption",
            partial_response_payload=partial,
        )
    )

    replayed = replay_bundle(single_bundle_dir(tmp_path))
    inference = replayed.inference_calls[attempt.inference_call_id]
    response_item_id = inference.response_item_ids[0]
    response_item = replayed.conversation_items[response_item_id]

    assert inference.execution.status == ExecutionStatus.CANCELLED
    assert inference.upstream_request_id == "req-cancelled"
    assert inference.raw_response_payload_id == partial.raw_payload_id
    assert len(inference.response_item_ids) == 1
    assert response_item.kind == ConversationItemKind.MESSAGE
    assert response_item.produced_by == [ProducerRef.Inference(attempt.inference_call_id)]
    assert response_item.body.parts == [ConversationPart.Text("partial")]


def test_cancelled_turn_closes_running_inference_call(tmp_path):
    # Rust test: reducer/inference_tests.rs cancelled_turn_closes_running_inference_call
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started({"input": [{"type": "message", "role": "user"}]})
    turn_end = trace.writer.append_with_context(
        RawTraceEventContext(thread_id="thread-root", codex_turn_id="turn-1"),
        RawTraceEventPayload.variant(
            "CodexTurnEnded",
            codex_turn_id="turn-1",
            status=ExecutionStatus.CANCELLED,
        ),
    )

    replayed = replay_bundle(single_bundle_dir(tmp_path))
    inference = next(iter(replayed.inference_calls.values()))
    assert inference.execution.status == ExecutionStatus.CANCELLED
    assert inference.execution.ended_seq == turn_end.seq


def test_late_cancelled_inference_preserves_turn_end_status_and_payload(tmp_path):
    # Rust test: reducer/inference_tests.rs late_cancelled_inference_preserves_turn_end_status
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started({"input": []})
    turn_end = trace.writer.append_with_context(
        RawTraceEventContext(thread_id="thread-root", codex_turn_id="turn-1"),
        RawTraceEventPayload.variant(
            "CodexTurnEnded",
            codex_turn_id="turn-1",
            status=ExecutionStatus.FAILED,
        ),
    )
    partial = trace.writer.write_json_payload(
        RawPayloadKind.INFERENCE_RESPONSE,
        {
            "response_id": None,
            "token_usage": None,
            "output_items": [{"type": "message", "role": "assistant"}],
        },
    )
    trace.writer.append(
        RawTraceEventPayload.variant(
            "InferenceCancelled",
            inference_call_id=attempt.inference_call_id,
            upstream_request_id="req-late-cancelled",
            reason="stream mapper noticed cancellation after turn end",
            partial_response_payload=partial,
        )
    )

    replayed = replay_bundle(single_bundle_dir(tmp_path))
    inference = next(iter(replayed.inference_calls.values()))
    assert inference.execution.status == ExecutionStatus.FAILED
    assert inference.execution.ended_seq == turn_end.seq
    assert inference.raw_response_payload_id == partial.raw_payload_id
    assert inference.upstream_request_id == "req-late-cancelled"
