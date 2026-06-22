import pytest

from pycodex.rollout_trace import (
    CompactionCheckpointTracePayload,
    ConversationChannel,
    ConversationItemKind,
    ConversationPart,
    ConversationRole,
    ExecutionStatus,
    ProducerRef,
    RawPayloadKind,
    RawToolCallRequester,
    RawTraceEventContext,
    RawTraceEventPayload,
    TokenUsage,
    ThreadTraceContext,
    replay_bundle,
)
from test_rollout_trace_thread_rs import metadata, single_bundle_dir


def message(role: str, text: str) -> dict:
    return {
        "type": "message",
        "role": role,
        "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}],
    }


def test_request_snapshots_reuse_history_without_deduping_new_identical_items(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # request_snapshots_reuse_history_without_deduping_new_identical_items
    # Contract: full request snapshots reconcile by prior snapshot position and
    # content, but repeated new identical items remain distinct.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    first = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    first.record_started({"input": [message("user", "ok")]})

    trace.record_codex_turn_started("turn-2")
    second = trace.inference_trace_context("turn-2", "gpt-test", "test-provider").start_attempt()
    second.record_started(
        {
            "input": [
                message("user", "ok"),
                message("assistant", "ack"),
                message("user", "ok"),
            ]
        }
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    first_items = rollout.inference_calls[first.inference_call_id].request_item_ids
    second_items = rollout.inference_calls[second.inference_call_id].request_item_ids

    assert len(first_items) == 1
    assert len(second_items) == 3
    assert second_items[0] == first_items[0]
    assert second_items[2] != first_items[0]
    assert len(rollout.conversation_items) == 3
    assert rollout.threads["thread-root"].conversation_item_ids == second_items


def test_response_outputs_enter_thread_conversation_on_completion(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # response_outputs_enter_thread_conversation_on_completion
    # Contract: response output items are appended immediately as
    # model-produced conversation items and extend the thread transcript.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started({"input": [message("user", "run tests")]})
    attempt.record_completed(
        "resp-1",
        "req-1",
        None,
        [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "tests passed"}],
            }
        ],
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    inference = rollout.inference_calls[attempt.inference_call_id]
    expected_thread_items = inference.request_item_ids + inference.response_item_ids
    response_item = rollout.conversation_items[inference.response_item_ids[0]]

    assert len(inference.response_item_ids) == 1
    assert rollout.threads["thread-root"].conversation_item_ids == expected_thread_items
    assert response_item.role == ConversationRole.ASSISTANT
    assert response_item.kind == ConversationItemKind.MESSAGE
    assert response_item.body.parts == [ConversationPart.Text("tests passed")]
    assert response_item.produced_by[0].inference_call_id == attempt.inference_call_id


def test_later_full_request_reuses_prior_json_tool_call_by_position(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # later_full_request_reuses_prior_json_tool_call_by_position
    # Contract: JSON conversation body matching ignores raw payload id, so a
    # function_call produced in a response can be reused by the next full request.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    first = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    first.record_started({"input": [message("user", "run tests")]})
    first.record_completed(
        "resp-1",
        "req-1",
        None,
        [
            {
                "type": "function_call",
                "name": "shell",
                "arguments": '{"cmd":"cargo test"}',
                "call_id": "call-1",
            }
        ],
    )

    trace.record_codex_turn_started("turn-2")
    second = trace.inference_trace_context("turn-2", "gpt-test", "test-provider").start_attempt()
    second.record_started(
        {
            "input": [
                message("user", "run tests"),
                {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": '{"cmd":"cargo test"}',
                    "call_id": "call-1",
                },
            ]
        }
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    first_call = rollout.inference_calls[first.inference_call_id]
    second_call = rollout.inference_calls[second.inference_call_id]

    assert second_call.request_item_ids == [
        first_call.request_item_ids[0],
        first_call.response_item_ids[0],
    ]
    assert len(rollout.conversation_items) == 2


def test_incremental_request_carries_prior_request_and_response_items_forward(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # incremental_request_carries_prior_request_and_response_items_forward
    # Contract: previous_response_id requests expose the reconstructed full
    # model-visible prefix plus the new delta item.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    first = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    first.record_started({"input": [message("user", "run tests")]})
    first.record_completed(
        "resp-1",
        "req-1",
        {
            "input_tokens": 10,
            "cached_input_tokens": 1,
            "output_tokens": 5,
            "reasoning_output_tokens": 2,
            "total_tokens": 15,
        },
        [
            {
                "type": "function_call",
                "name": "shell",
                "arguments": '{"cmd":"cargo test"}',
                "call_id": "call-1",
            }
        ],
    )

    trace.record_codex_turn_started("turn-2")
    second = trace.inference_trace_context("turn-2", "gpt-test", "test-provider").start_attempt()
    second.record_started(
        {
            "type": "response.create",
            "previous_response_id": "resp-1",
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": "tests passed",
                }
            ],
        }
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    first_call = rollout.inference_calls[first.inference_call_id]
    second_call = rollout.inference_calls[second.inference_call_id]

    assert len(first_call.response_item_ids) == 1
    assert second_call.request_item_ids == [
        first_call.request_item_ids[0],
        first_call.response_item_ids[0],
        rollout.threads["thread-root"].conversation_item_ids[2],
    ]
    assert rollout.threads["thread-root"].conversation_item_ids == second_call.request_item_ids
    assert first_call.usage == TokenUsage(
        input_tokens=10,
        cached_input_tokens=1,
        output_tokens=5,
        reasoning_output_tokens=2,
    )


def test_tool_call_links_model_call_and_followup_output_items(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # tool_call_links_model_call_and_followup_output_items
    # Contract: a runtime tool call with model_visible_call_id links to the
    # response function_call item, the originating inference, and the later
    # function_call_output item observed in the follow-up request.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    first = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    first.record_started({"input": [message("user", "run tests")]})
    first.record_completed(
        "resp-1",
        "req-1",
        None,
        [
            {
                "type": "function_call",
                "name": "exec_command",
                "arguments": '{"cmd":"cargo test"}',
                "call_id": "call-1",
            }
        ],
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id="tool-1",
            model_visible_call_id="call-1",
            code_mode_runtime_tool_id=None,
            requester=RawToolCallRequester.Model(),
            kind="exec_command",
            summary={
                "type": "generic",
                "label": "exec_command",
                "input_preview": "cargo test",
                "output_preview": None,
            },
            invocation_payload=None,
        ),
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallEnded",
            tool_call_id="tool-1",
            status=ExecutionStatus.COMPLETED,
            result_payload=None,
        ),
    )

    trace.record_codex_turn_started("turn-2")
    second = trace.inference_trace_context("turn-2", "gpt-test", "test-provider").start_attempt()
    second.record_started(
        {
            "type": "response.create",
            "previous_response_id": "resp-1",
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": "tests passed",
                }
            ],
        }
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    first_inference = rollout.inference_calls[first.inference_call_id]
    second_inference = rollout.inference_calls[second.inference_call_id]
    tool_call = rollout.tool_calls["tool-1"]
    output_item_id = second_inference.request_item_ids[-1]

    assert first_inference.tool_call_ids_started_by_response == ["tool-1"]
    assert tool_call.model_visible_call_item_ids == first_inference.response_item_ids
    assert tool_call.model_visible_output_item_ids == [output_item_id]
    assert rollout.conversation_items[output_item_id].produced_by == [
        ProducerRef.Tool("tool-1")
    ]


def test_full_request_snapshot_can_reorder_existing_items_and_insert_summary(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # full_request_snapshot_can_reorder_existing_items_and_insert_summary
    # Contract: full request snapshots are authoritative; they may reorder
    # previous items by content and insert a fresh summary item.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    first = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    first.record_started(
        {
            "input": [
                message("developer", "follow the repo rules"),
                message("user", "count files"),
            ]
        }
    )

    trace.record_codex_turn_started("turn-2")
    second = trace.inference_trace_context("turn-2", "gpt-test", "test-provider").start_attempt()
    second.record_started(
        {
            "input": [
                message("user", "count files"),
                message("user", "summary from a compacted prior attempt"),
                message("developer", "follow the repo rules"),
            ]
        }
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    first_items = rollout.inference_calls[first.inference_call_id].request_item_ids
    second_items = rollout.inference_calls[second.inference_call_id].request_item_ids

    assert second_items[0] == first_items[1]
    assert second_items[2] == first_items[0]
    assert second_items[1] not in first_items
    assert len(rollout.conversation_items) == 3


def test_reasoning_body_preserves_text_summary_and_encoded_content(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # reasoning_body_preserves_text_summary_and_encoded_content
    # Contract: reasoning output preserves readable text, summary text, and
    # encrypted content as distinct ordered conversation parts.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started({"input": [message("user", "think visibly")]})
    attempt.record_completed(
        "resp-1",
        "req-1",
        None,
        [
            {
                "type": "reasoning",
                "content": [{"type": "reasoning_text", "text": "raw reasoning"}],
                "summary": [{"type": "summary_text", "text": "brief summary"}],
                "encrypted_content": "encoded-reasoning",
            }
        ],
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    reasoning_item_id = rollout.inference_calls[attempt.inference_call_id].response_item_ids[0]

    assert rollout.conversation_items[reasoning_item_id].body.parts == [
        ConversationPart.Text("raw reasoning"),
        ConversationPart.Summary("brief summary"),
        ConversationPart.Encoded("encrypted_content", "encoded-reasoning"),
    ]


def test_encrypted_reasoning_reuses_response_item_in_later_request(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # encrypted_reasoning_reuses_response_item_in_later_request
    # Contract: encrypted_content is the stable identity for reasoning items,
    # so a later request that only carries encrypted reasoning reuses the
    # earlier response item and keeps readable evidence.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    user = message("user", "count files")
    function_call = {
        "type": "function_call",
        "name": "shell",
        "arguments": '{"cmd":"find . -maxdepth 1 -type f | wc -l"}',
        "call_id": "call-1",
    }
    readable_reasoning = {
        "type": "reasoning",
        "content": [{"type": "text", "text": "need count"}],
        "summary": [],
        "encrypted_content": "encoded-reasoning",
    }
    encrypted_reasoning = {
        "type": "reasoning",
        "summary": [],
        "encrypted_content": "encoded-reasoning",
    }

    trace.record_codex_turn_started("turn-1")
    first = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    first.record_started({"input": [user]})
    first.record_completed("resp-1", "req-1", None, [readable_reasoning, function_call])

    trace.record_codex_turn_started("turn-2")
    second = trace.inference_trace_context("turn-2", "gpt-test", "test-provider").start_attempt()
    second.record_started(
        {
            "input": [
                user,
                encrypted_reasoning,
                function_call,
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": "31\n",
                },
            ]
        }
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    first_call = rollout.inference_calls[first.inference_call_id]
    second_call = rollout.inference_calls[second.inference_call_id]
    output_item_id = rollout.threads["thread-root"].conversation_item_ids[3]

    assert second_call.request_item_ids == [
        first_call.request_item_ids[0],
        first_call.response_item_ids[0],
        first_call.response_item_ids[1],
        output_item_id,
    ]
    assert rollout.conversation_items[first_call.response_item_ids[0]].body.parts == [
        ConversationPart.Text("need count"),
        ConversationPart.Encoded("encrypted_content", "encoded-reasoning"),
    ]
    assert len(rollout.conversation_items) == 4
    assert rollout.threads["thread-root"].conversation_item_ids == second_call.request_item_ids


def test_encrypted_reasoning_upgrades_when_later_sighting_has_more_readable_body(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # encrypted_reasoning_upgrades_when_later_sighting_has_more_readable_body
    # Contract: same encrypted reasoning identity reuses one item and merges
    # complementary readable text and summary evidence.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    user = message("user", "count files")
    text_only_reasoning = {
        "type": "reasoning",
        "content": [{"type": "text", "text": "need count"}],
        "summary": [],
        "encrypted_content": "encoded-reasoning",
    }
    summary_only_reasoning = {
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": "counting files"}],
        "encrypted_content": "encoded-reasoning",
    }

    trace.record_codex_turn_started("turn-1")
    first = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    first.record_started({"input": [user, text_only_reasoning]})

    trace.record_codex_turn_started("turn-2")
    second = trace.inference_trace_context("turn-2", "gpt-test", "test-provider").start_attempt()
    second.record_started({"input": [user, summary_only_reasoning]})

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    first_call = rollout.inference_calls[first.inference_call_id]
    second_call = rollout.inference_calls[second.inference_call_id]
    reasoning_item_id = first_call.request_item_ids[1]

    assert second_call.request_item_ids[1] == reasoning_item_id
    assert rollout.conversation_items[reasoning_item_id].body.parts == [
        ConversationPart.Text("need count"),
        ConversationPart.Summary("counting files"),
        ConversationPart.Encoded("encrypted_content", "encoded-reasoning"),
    ]
    assert len(rollout.conversation_items) == 2


def test_same_encrypted_reasoning_with_different_text_reuses_first_readable_body(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # same_encrypted_reasoning_with_different_text_reuses_first_readable_body
    # Contract: same encrypted reasoning identity reuses the first item, but a
    # later conflicting readable text does not overwrite earlier evidence.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    user = message("user", "count files")

    trace.record_codex_turn_started("turn-1")
    first = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    first.record_started({"input": [user]})
    first.record_completed(
        "resp-1",
        "req-1",
        None,
        [
            {
                "type": "reasoning",
                "content": [{"type": "text", "text": "first text"}],
                "summary": [],
                "encrypted_content": "encoded-reasoning",
            }
        ],
    )

    trace.record_codex_turn_started("turn-2")
    second = trace.inference_trace_context("turn-2", "gpt-test", "test-provider").start_attempt()
    second.record_started(
        {
            "input": [
                user,
                {
                    "type": "reasoning",
                    "content": [{"type": "text", "text": "different text"}],
                    "summary": [],
                    "encrypted_content": "encoded-reasoning",
                },
            ]
        }
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    first_call = rollout.inference_calls[first.inference_call_id]
    second_call = rollout.inference_calls[second.inference_call_id]
    reasoning_item_id = first_call.response_item_ids[0]

    assert second_call.request_item_ids == [first_call.request_item_ids[0], reasoning_item_id]
    assert rollout.conversation_items[reasoning_item_id].body.parts == [
        ConversationPart.Text("first text"),
        ConversationPart.Encoded("encrypted_content", "encoded-reasoning"),
    ]
    assert len(rollout.conversation_items) == 2


def test_compaction_boundary_repeats_prefix_and_reuses_replacement_items(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # compaction_boundary_repeats_prefix_and_reuses_replacement_items
    # Contract: installing a compaction checkpoint records input history,
    # appends a structural marker, creates fresh replacement items, and makes
    # the next full request reconcile against replacement history.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    developer = message("developer", "follow repo rules")
    user = message("user", "count files")
    summary = message("user", "summary from compacted history")
    compaction_summary = {"type": "compaction", "encrypted_content": "encrypted-summary"}

    trace.record_codex_turn_started("turn-1")
    first = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    first.record_started({"input": [developer, user]})
    compaction = trace.compaction_trace_context(
        "turn-1", "compaction-1", "gpt-test", "test-provider"
    )
    compaction.record_installed(
        CompactionCheckpointTracePayload(
            input_history=[developer, user],
            replacement_history=[user, summary, compaction_summary],
        )
    )

    trace.record_codex_turn_started("turn-2")
    second = trace.inference_trace_context("turn-2", "gpt-test", "test-provider").start_attempt()
    second.record_started({"input": [developer, user, summary, compaction_summary]})

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    first_call = rollout.inference_calls[first.inference_call_id]
    second_call = rollout.inference_calls[second.inference_call_id]
    installed = rollout.compactions["compaction-1"]
    marker = rollout.conversation_items[installed.marker_item_id]

    assert installed.input_item_ids == first_call.request_item_ids
    assert len(second_call.request_item_ids) == 4
    assert second_call.request_item_ids[1:] == installed.replacement_item_ids
    assert marker.kind == ConversationItemKind.COMPACTION_MARKER
    assert marker.body.parts == []
    assert marker.produced_by == [ProducerRef.Compaction("compaction-1")]
    assert second_call.request_item_ids[0] != first_call.request_item_ids[0]
    assert installed.replacement_item_ids[0] != first_call.request_item_ids[1]
    assert rollout.conversation_items[installed.replacement_item_ids[0]].produced_by == [
        ProducerRef.Compaction("compaction-1")
    ]
    assert rollout.conversation_items[installed.replacement_item_ids[1]].produced_by == [
        ProducerRef.Compaction("compaction-1")
    ]
    summary_item = rollout.conversation_items[installed.replacement_item_ids[2]]
    assert summary_item.channel == ConversationChannel.SUMMARY
    assert summary_item.kind == ConversationItemKind.MESSAGE
    assert summary_item.body.parts == [
        ConversationPart.Encoded("encrypted_content", "encrypted-summary")
    ]


def test_context_compaction_boundary_repeats_prefix_and_reuses_replacement_items(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # context_compaction_boundary_repeats_prefix_and_reuses_replacement_items
    # Contract: context_compaction replacement summaries use the same
    # summary-channel message shape as compaction summaries.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    developer = message("developer", "follow repo rules")
    user = message("user", "count files")
    summary = message("user", "summary from compacted history")
    compaction_summary = {"type": "context_compaction", "encrypted_content": "encrypted-summary"}

    trace.record_codex_turn_started("turn-1")
    first = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    first.record_started({"input": [developer, user]})
    compaction = trace.compaction_trace_context(
        "turn-1", "compaction-1", "gpt-test", "test-provider"
    )
    compaction.record_installed(
        CompactionCheckpointTracePayload(
            input_history=[developer, user],
            replacement_history=[user, summary, compaction_summary],
        )
    )

    trace.record_codex_turn_started("turn-2")
    second = trace.inference_trace_context("turn-2", "gpt-test", "test-provider").start_attempt()
    second.record_started({"input": [developer, user, summary, compaction_summary]})

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    installed = rollout.compactions["compaction-1"]
    summary_item = rollout.conversation_items[installed.replacement_item_ids[2]]

    assert rollout.inference_calls[second.inference_call_id].request_item_ids[1:] == installed.replacement_item_ids
    assert summary_item.channel == ConversationChannel.SUMMARY
    assert summary_item.kind == ConversationItemKind.MESSAGE
    assert summary_item.body.parts == [
        ConversationPart.Encoded("encrypted_content", "encrypted-summary")
    ]


def test_model_visible_call_id_reuse_with_different_content_is_reducer_error(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # model_visible_call_id_reuse_with_different_content_is_reducer_error
    # Contract: a model-visible call_id cannot be reused for a different
    # function_call body in the same thread.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    first = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    first.record_started(
        {
            "input": [
                {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": '{"cmd":"cargo test"}',
                    "call_id": "call-1",
                }
            ]
        }
    )

    trace.record_codex_turn_started("turn-2")
    second = trace.inference_trace_context("turn-2", "gpt-test", "test-provider").start_attempt()
    second.record_started(
        {
            "input": [
                {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": '{"cmd":"cargo check"}',
                    "call_id": "call-1",
                }
            ]
        }
    )

    with pytest.raises(
        ValueError,
        match="model-visible call id call-1 was reused with different content",
    ):
        replay_bundle(single_bundle_dir(tmp_path))


def test_unsupported_model_item_is_reducer_error(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # unsupported_model_item_is_reducer_error
    # Contract: unknown model item types fail replay instead of being skipped.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started(
        {
            "input": [
                {
                    "type": "new_unhandled_model_item",
                    "payload": "must not be silently skipped",
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="unsupported model item type new_unhandled_model_item"):
        replay_bundle(single_bundle_dir(tmp_path))


def test_normalize_rejects_model_items_without_string_type(tmp_path):
    # Rust source contract: reducer/conversation/normalize.rs
    # normalize_model_item
    # Contract: model items without a string type fail with the same parse
    # boundary error used before item-specific dispatch.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started({"input": [{"role": "user", "content": []}]})

    with pytest.raises(ValueError, match="did not contain a string type"):
        replay_bundle(single_bundle_dir(tmp_path))


def test_normalize_rejects_messages_without_string_role(tmp_path):
    # Rust source contract: reducer/conversation/normalize.rs
    # normalize_message_item
    # Contract: message items without a string role fail before role enum
    # conversion.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started({"input": [{"type": "message", "content": []}]})

    with pytest.raises(ValueError, match="did not contain a string role"):
        replay_bundle(single_bundle_dir(tmp_path))


def test_normalize_rejects_unsupported_message_role(tmp_path):
    # Rust source contract: reducer/conversation/normalize.rs
    # role_from_str
    # Contract: only system/developer/user/assistant/tool roles are accepted.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started(
        {
            "input": [
                {
                    "type": "message",
                    "role": "critic",
                    "content": [{"type": "input_text", "text": "no"}],
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="unsupported message role critic"):
        replay_bundle(single_bundle_dir(tmp_path))


def test_normalize_rejects_malformed_reasoning_parts(tmp_path):
    # Rust source contract: reducer/conversation/normalize.rs
    # normalize_reasoning_item/append_reasoning_parts
    # Contract: reasoning content and summary arrays accept only Rust-known
    # typed text entries, and a reasoning item must contain at least one body
    # part or encrypted_content.
    cases = [
        (
            {"type": "reasoning", "content": [{"type": "delta", "text": "x"}]},
            "unsupported content type delta",
        ),
        (
            {"type": "reasoning", "summary": [{"type": "text", "text": "x"}]},
            "unsupported summary type text",
        ),
        (
            {"type": "reasoning", "content": []},
            "contained no content, summary, or encrypted_content",
        ),
        (
            {"type": "reasoning", "summary": [{"type": "summary_text"}]},
            "had summary entry without string text",
        ),
    ]

    for index, (payload, expected) in enumerate(cases):
        case_path = tmp_path / f"case-{index}"
        case_path.mkdir()
        trace = ThreadTraceContext.start_root_in_root_for_test(case_path, metadata(f"thread-{index}"))
        trace.record_codex_turn_started("turn-1")
        attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
        attempt.record_started({"input": [payload]})

        with pytest.raises(ValueError, match=expected):
            replay_bundle(single_bundle_dir(case_path))


def test_missing_request_input_is_reducer_error(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # missing_request_input_is_reducer_error
    # Contract: inference request payloads must contain an input field.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started({"model": "gpt-test"})

    with pytest.raises(ValueError, match="did not contain input"):
        replay_bundle(single_bundle_dir(tmp_path))


def test_unknown_previous_response_id_is_reducer_error(tmp_path):
    # Rust test: reducer/conversation_tests.rs
    # unknown_previous_response_id_is_reducer_error
    # Contract: incremental requests must reference a known prior response id
    # from the same thread.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started(
        {
            "previous_response_id": "resp-missing",
            "input": [message("user", "still here")],
        }
    )

    with pytest.raises(ValueError, match="unknown previous_response_id resp-missing"):
        replay_bundle(single_bundle_dir(tmp_path))


def test_custom_tool_call_variants_follow_normalize_rs_contract(tmp_path):
    # Rust source contract: reducer/conversation/normalize.rs
    # normalize_model_item/custom_tool_call_body/custom_tool_call_output
    # Contract: custom tool calls are commentary assistant custom-tool items;
    # exec inputs become JavaScript code parts, other string inputs are text,
    # and custom tool outputs are commentary tool custom-tool-output items.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started({"input": [message("user", "run custom tools")]})
    attempt.record_completed(
        "resp-1",
        "req-1",
        None,
        [
            {
                "type": "custom_tool_call",
                "name": "exec",
                "input": "console.log('ok')",
                "call_id": "custom-exec",
            },
            {
                "type": "custom_tool_call",
                "name": "apply_patch",
                "input": "*** Begin Patch",
                "call_id": "custom-text",
            },
            {
                "type": "custom_tool_call_output",
                "call_id": "custom-text",
                "output": "patched",
            },
        ],
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    response_ids = rollout.inference_calls[attempt.inference_call_id].response_item_ids
    exec_item = rollout.conversation_items[response_ids[0]]
    text_item = rollout.conversation_items[response_ids[1]]
    output_item = rollout.conversation_items[response_ids[2]]

    assert exec_item.role == ConversationRole.ASSISTANT
    assert exec_item.channel == ConversationChannel.COMMENTARY
    assert exec_item.kind == ConversationItemKind.CUSTOM_TOOL_CALL
    assert exec_item.call_id == "custom-exec"
    assert exec_item.body.parts == [ConversationPart.Code("javascript", "console.log('ok')")]
    assert text_item.kind == ConversationItemKind.CUSTOM_TOOL_CALL
    assert text_item.call_id == "custom-text"
    assert text_item.body.parts == [ConversationPart.Text("*** Begin Patch")]
    assert output_item.role == ConversationRole.TOOL
    assert output_item.channel == ConversationChannel.COMMENTARY
    assert output_item.kind == ConversationItemKind.CUSTOM_TOOL_CALL_OUTPUT
    assert output_item.call_id == "custom-text"
    assert output_item.body.parts == [ConversationPart.Text("patched")]


def test_hosted_call_variants_use_json_backed_function_call_contract(tmp_path):
    # Rust source contract: reducer/conversation/normalize.rs
    # normalize_model_item for tool_search/web_search/image_generation/
    # local_shell calls and tool_search/mcp outputs.
    # Contract: these hosted/tool variants enter the conversation as
    # commentary function-call/function-call-output items with JSON bodies.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started({"input": [message("user", "search and shell")]})
    output_items = [
        {
            "type": "tool_search_call",
            "call_id": "search-1",
            "execution": "client",
            "arguments": {"query": "docs"},
        },
        {
            "type": "web_search_call",
            "call_id": "web-1",
            "action": {"type": "search", "query": "weather"},
        },
        {
            "type": "image_generation_call",
            "call_id": "image-1",
            "status": "completed",
            "result": "base64",
        },
        {
            "type": "local_shell_call",
            "call_id": "shell-1",
            "status": "completed",
            "action": {"type": "exec", "command": ["echo", "ok"]},
        },
        {
            "type": "tool_search_output",
            "call_id": "search-1",
            "status": "completed",
            "execution": "client",
            "output": "found",
            "tools": [],
        },
        {
            "type": "mcp_tool_call_output",
            "call_id": "mcp-1",
            "output": "mcp result",
        },
    ]
    attempt.record_completed("resp-1", "req-1", None, output_items)

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    response_ids = rollout.inference_calls[attempt.inference_call_id].response_item_ids
    items = [rollout.conversation_items[item_id] for item_id in response_ids]

    assert [item.kind for item in items[:4]] == [ConversationItemKind.FUNCTION_CALL] * 4
    assert [item.role for item in items[:4]] == [ConversationRole.ASSISTANT] * 4
    assert [item.channel for item in items[:4]] == [ConversationChannel.COMMENTARY] * 4
    assert [item.call_id for item in items[:4]] == ["search-1", "web-1", "image-1", "shell-1"]
    assert [item.kind for item in items[4:]] == [ConversationItemKind.FUNCTION_CALL_OUTPUT] * 2
    assert [item.role for item in items[4:]] == [ConversationRole.TOOL] * 2
    assert [item.channel for item in items[4:]] == [ConversationChannel.COMMENTARY] * 2
    assert [item.call_id for item in items[4:]] == ["search-1", "mcp-1"]
    assert items[0].body.parts == [
        ConversationPart.Json(
            '{"type":"tool_search_call","call_id":"search-1","execution":"client","arguments":{"query":"docs"}}',
            rollout.inference_calls[attempt.inference_call_id].raw_response_payload_id,
        )
    ]
    assert items[4].body.parts == [
        ConversationPart.Json(
            '{"type":"tool_search_output","call_id":"search-1","status":"completed","execution":"client","output":"found","tools":[]}',
            rollout.inference_calls[attempt.inference_call_id].raw_response_payload_id,
        )
    ]


def test_inference_start_rejects_unknown_codex_turn(tmp_path):
    # Rust test: reducer/conversation_tests.rs inference_start_rejects_unknown_codex_turn
    # Contract: inference starts are rejected when their codex_turn_id has not
    # been started in the reduced graph.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    request = trace.writer.write_json_payload(
        RawPayloadKind.INFERENCE_REQUEST,
        {"input": [message("user", "hello")]},
    )
    trace.writer.append(
        RawTraceEventPayload.variant(
            "InferenceStarted",
            inference_call_id="inference-1",
            thread_id="thread-root",
            codex_turn_id="turn-missing",
            model="gpt-test",
            provider_name="test-provider",
            request_payload=request,
        )
    )

    with pytest.raises(ValueError, match="referenced unknown codex turn turn-missing"):
        replay_bundle(single_bundle_dir(tmp_path))
