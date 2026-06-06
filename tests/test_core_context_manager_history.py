"""Parity tests for ``codex-rs/core/src/context_manager/history.rs``."""

from pathlib import Path

from pycodex.core.context_manager.history import (
    ContextManager,
    estimate_item_token_count,
    estimate_response_item_model_visible_bytes,
    estimate_token_count_with_base_instructions,
)
from pycodex.protocol import (
    AskForApproval,
    BaseInstructions,
    ContentItem,
    FunctionCallOutputContentItem,
    FunctionCallOutputPayload,
    ImageDetail,
    InterAgentCommunication,
    ResponseItem,
    SandboxPolicy,
    TokenUsage,
    TruncationPolicyConfig,
    TurnContextItem,
)
from pycodex.utils.string import approx_token_count


def _assistant_msg(text: str) -> ResponseItem:
    return ResponseItem.message("assistant", (ContentItem.output_text(text),))


def _user_msg(text: str) -> ResponseItem:
    return ResponseItem.message("user", (ContentItem.input_text(text),))


def _developer_msg(text: str) -> ResponseItem:
    return ResponseItem.message("developer", (ContentItem.input_text(text),))


def _developer_msg_with_fragments(sections: tuple[str, ...]) -> ResponseItem:
    return ResponseItem.message("developer", tuple(ContentItem.input_text(section) for section in sections))


def _inter_agent_assistant_msg(text: str = "continue") -> ResponseItem:
    communication = InterAgentCommunication("/root", "/root/worker", text, True)
    return ResponseItem.from_response_input_item(communication.to_response_input_item())


def _function_call_output(call_id: str, output: str = "ok") -> ResponseItem:
    return ResponseItem(type="function_call_output", call_id=call_id, output=FunctionCallOutputPayload.from_text(output))


def _custom_tool_call_output(call_id: str, output: str = "ok") -> ResponseItem:
    return ResponseItem(
        type="custom_tool_call_output",
        call_id=call_id,
        output=FunctionCallOutputPayload.from_text(output),
    )


def _encrypted_reasoning(encoded_len: int) -> ResponseItem:
    return ResponseItem.reasoning("reasoning-id", encrypted_content="a" * encoded_len)


def _reference_context_item() -> TurnContextItem:
    return TurnContextItem(
        cwd=Path("C:/work/project"),
        approval_policy=AskForApproval.ON_REQUEST,
        sandbox_policy=SandboxPolicy.danger_full_access(),
        model="gpt-test",
    )


def _function_call_output_items(
    call_id: str,
    content_items: tuple[FunctionCallOutputContentItem, ...],
    *,
    success: bool | None = None,
) -> ResponseItem:
    return ResponseItem(
        type="function_call_output",
        call_id=call_id,
        output=FunctionCallOutputPayload.from_content_items(content_items, success=success),
    )


def test_estimate_token_count_with_base_instructions_uses_provided_text() -> None:
    """Rust unit test: ``estimate_token_count_with_base_instructions_uses_provided_text``."""

    history = ContextManager.from_items((_assistant_msg("hello from history"),))
    short_base = BaseInstructions("short")
    long_base = BaseInstructions("x" * 1_000)

    short_estimate = history.estimate_token_count_with_base_instructions(short_base)
    long_estimate = history.estimate_token_count_with_base_instructions(long_base)

    expected_delta = approx_token_count(long_base.text) - approx_token_count(short_base.text)
    assert long_estimate is not None
    assert short_estimate is not None
    assert long_estimate - short_estimate == expected_delta


def test_record_items_filters_non_api_messages() -> None:
    """Rust unit test: ``filters_non_api_messages``."""

    history = ContextManager.new()
    system = ResponseItem.message("system", (ContentItem.output_text("ignored"),))
    reasoning = ResponseItem.reasoning("", summary=("summary",), content=("thinking...",))
    user = _user_msg("hi")
    assistant = _assistant_msg("hello")

    history.record_items((system, reasoning, ResponseItem.other()))
    history.record_items((user, assistant))

    assert history.raw_items() == [reasoning, user, assistant]


def test_record_items_truncates_function_call_output_content() -> None:
    """Rust unit test: ``record_items_truncates_function_call_output_content``."""

    history = ContextManager.new()
    long_output = "a very long line to trigger truncation\n" * 2_500
    item = ResponseItem(
        type="function_call_output",
        call_id="call-100",
        output=FunctionCallOutputPayload.from_text(long_output, success=True),
    )

    history.record_items((item,), TruncationPolicyConfig.tokens(1_000))

    stored = history.raw_items()[0]
    content = stored.output.to_text()
    assert stored.type == "function_call_output"
    assert stored.output.success is True
    assert content != long_output
    assert "tokens truncated" in content


def test_record_items_truncates_custom_tool_call_output_content() -> None:
    """Rust unit test: ``record_items_truncates_custom_tool_call_output_content``."""

    history = ContextManager.new()
    long_output = "custom output that is very long\n" * 2_500
    item = ResponseItem(
        type="custom_tool_call_output",
        call_id="tool-200",
        output=FunctionCallOutputPayload.from_text(long_output),
    )

    history.record_items((item,), TruncationPolicyConfig.tokens(1_000))

    stored = history.raw_items()[0]
    content = stored.output.to_text()
    assert stored.type == "custom_tool_call_output"
    assert content != long_output
    assert "tokens truncated" in content


def test_record_items_respects_custom_token_limit() -> None:
    """Rust unit test: ``record_items_respects_custom_token_limit``."""

    history = ContextManager.new()
    long_output = "tokenized content repeated many times " * 200
    item = ResponseItem(
        type="function_call_output",
        call_id="call-custom-limit",
        output=FunctionCallOutputPayload.from_text(long_output, success=True),
    )

    history.record_items((item,), TruncationPolicyConfig.tokens(10))

    assert "tokens truncated" in history.raw_items()[0].output.to_text()


def test_non_last_reasoning_tokens_return_zero_when_no_user_messages() -> None:
    """Rust unit test: ``non_last_reasoning_tokens_return_zero_when_no_user_messages``."""

    history = ContextManager.from_items((_encrypted_reasoning(800),))

    assert history.get_non_last_reasoning_items_tokens() == 0


def test_non_last_reasoning_tokens_ignore_entries_after_last_user() -> None:
    """Rust unit test: ``non_last_reasoning_tokens_ignore_entries_after_last_user``."""

    history = ContextManager.from_items(
        (
            _encrypted_reasoning(900),
            _user_msg("first"),
            _encrypted_reasoning(1_000),
            _user_msg("second"),
            _encrypted_reasoning(2_000),
        )
    )

    assert history.get_non_last_reasoning_items_tokens() == 32


def test_items_after_last_model_generated_tokens_include_user_and_tool_output() -> None:
    """Rust unit test: ``items_after_last_model_generated_tokens_include_user_and_tool_output``."""

    added_user = _user_msg("new user message")
    added_tool_output = _custom_tool_call_output("call-tail", "new tool output")
    history = ContextManager.from_items((_assistant_msg("already counted by API"), added_user, added_tool_output))

    expected_tokens = estimate_item_token_count(added_user) + estimate_item_token_count(added_tool_output)

    assert sum(estimate_item_token_count(item) for item in history.items_after_last_model_generated_item()) == expected_tokens


def test_items_after_last_model_generated_tokens_are_zero_without_model_generated_items() -> None:
    """Rust unit test: ``items_after_last_model_generated_tokens_are_zero_without_model_generated_items``."""

    history = ContextManager.from_items((_user_msg("no model output yet"),))

    assert sum(estimate_item_token_count(item) for item in history.items_after_last_model_generated_item()) == 0


def test_total_token_usage_includes_all_items_after_last_model_generated_item() -> None:
    """Rust unit test: ``total_token_usage_includes_all_items_after_last_model_generated_item``."""

    history = ContextManager.from_items((_assistant_msg("already counted by API"),))
    history.update_token_info(TokenUsage(total_tokens=100), None)
    added_user = _user_msg("new user message")
    added_tool_output = _custom_tool_call_output("tool-tail", "new tool output")

    history.record_items((added_user, added_tool_output), TruncationPolicyConfig.tokens(10_000))

    assert history.get_total_token_usage(True) == (
        100 + estimate_item_token_count(added_user) + estimate_item_token_count(added_tool_output)
    )


def test_total_token_usage_breakdown_reports_last_usage_and_tail_estimates() -> None:
    """Rust source contract: ``get_total_token_usage_breakdown`` reports last usage plus local tail estimates."""

    counted = _assistant_msg("already counted by API")
    added_user = _user_msg("new user message")
    added_tool_output = _custom_tool_call_output("tool-tail", "new tool output")
    history = ContextManager.from_items((counted, added_user, added_tool_output))
    history.update_token_info(TokenUsage(total_tokens=100), None)

    breakdown = history.get_total_token_usage_breakdown()

    assert breakdown.last_api_response_total_tokens == 100
    assert breakdown.all_history_items_model_visible_bytes == sum(
        estimate_response_item_model_visible_bytes(item) for item in (counted, added_user, added_tool_output)
    )
    assert breakdown.estimated_tokens_of_items_added_since_last_successful_api_response == (
        estimate_item_token_count(added_user) + estimate_item_token_count(added_tool_output)
    )
    assert breakdown.estimated_bytes_of_items_added_since_last_successful_api_response == (
        estimate_response_item_model_visible_bytes(added_user)
        + estimate_response_item_model_visible_bytes(added_tool_output)
    )


def test_for_prompt_preserves_inter_agent_assistant_messages() -> None:
    """Rust unit test: ``for_prompt_preserves_inter_agent_assistant_messages``."""

    item = _inter_agent_assistant_msg("continue")
    history = ContextManager.from_items((item,))

    assert history.raw_items() == [item]
    assert history.for_prompt(("text", "image")) == [item]


def test_drop_last_n_user_turns_treats_inter_agent_assistant_messages_as_instruction_turns() -> None:
    """Rust unit test: ``drop_last_n_user_turns_treats_inter_agent_assistant_messages_as_instruction_turns``."""

    first_turn = _user_msg("first")
    first_reply = _assistant_msg("done")
    inter_agent_turn = _inter_agent_assistant_msg("continue")
    inter_agent_reply = _assistant_msg("worker reply")
    history = ContextManager.from_items((first_turn, first_reply, inter_agent_turn, inter_agent_reply))

    history.drop_last_n_user_turns(1)

    assert history.raw_items() == [first_turn, first_reply]


def test_drop_last_n_user_turns_preserves_prefix() -> None:
    """Rust unit test: ``drop_last_n_user_turns_preserves_prefix``."""

    prefix = _assistant_msg("session prefix item")
    u1 = _user_msg("u1")
    a1 = _assistant_msg("a1")
    u2 = _user_msg("u2")
    a2 = _assistant_msg("a2")
    history = ContextManager.from_items((prefix, u1, a1, u2, a2))

    history.drop_last_n_user_turns(1)

    assert history.for_prompt(("text", "image")) == [prefix, u1, a1]

    history = ContextManager.from_items((prefix, u1, a1, u2, a2))
    history.drop_last_n_user_turns(99)

    assert history.for_prompt(("text", "image")) == [prefix]


def test_drop_last_n_user_turns_ignores_session_prefix_user_messages() -> None:
    """Rust unit test: ``drop_last_n_user_turns_ignores_session_prefix_user_messages``."""

    prefix_items = (
        _user_msg("<environment_context>ctx</environment_context>"),
        _user_msg("# AGENTS.md instructions for test_directory\n\n<INSTRUCTIONS>\ntest_text\n</INSTRUCTIONS>"),
        _user_msg("<skill>\n<name>demo</name>\n<path>skills/demo/SKILL.md</path>\nbody\n</skill>"),
        _user_msg("<user_shell_command>echo 42</user_shell_command>"),
        _user_msg('<subagent_notification>{"agent_id":"a","status":"completed"}</subagent_notification>'),
    )
    turn_1 = (_user_msg("turn 1 user"), _assistant_msg("turn 1 assistant"))
    turn_2 = (_user_msg("turn 2 user"), _assistant_msg("turn 2 assistant"))

    history = ContextManager.from_items((*prefix_items, *turn_1, *turn_2))
    history.drop_last_n_user_turns(1)

    assert history.for_prompt(("text", "image")) == [*prefix_items, *turn_1]

    history = ContextManager.from_items((*prefix_items, *turn_1, *turn_2))
    history.drop_last_n_user_turns(2)

    assert history.for_prompt(("text", "image")) == list(prefix_items)

    history = ContextManager.from_items((*prefix_items, *turn_1, *turn_2))
    history.drop_last_n_user_turns(3)

    assert history.for_prompt(("text", "image")) == list(prefix_items)


def test_drop_last_n_user_turns_trims_context_updates_above_rolled_back_turn() -> None:
    """Rust unit test: ``drop_last_n_user_turns_trims_context_updates_above_rolled_back_turn``."""

    items = (
        _assistant_msg("session prefix item"),
        _user_msg("turn 1 user"),
        _assistant_msg("turn 1 assistant"),
        _developer_msg("Generated images are saved to /tmp as /tmp/image-1.png by default."),
        _developer_msg("<collaboration_mode>ROLLED_BACK_DEV_INSTRUCTIONS</collaboration_mode>"),
        _user_msg("<environment_context><cwd>PRETURN_CONTEXT_DIFF_CWD</cwd></environment_context>"),
        _user_msg("turn 2 user"),
        _assistant_msg("turn 2 assistant"),
    )
    history = ContextManager.from_items(items)
    reference_context_item = _reference_context_item()
    history.set_reference_context_item(reference_context_item)

    history.drop_last_n_user_turns(1)

    assert history.for_prompt(("text", "image")) == [
        _assistant_msg("session prefix item"),
        _user_msg("turn 1 user"),
        _assistant_msg("turn 1 assistant"),
        _developer_msg("Generated images are saved to /tmp as /tmp/image-1.png by default."),
    ]
    assert history.reference_context_item() == reference_context_item


def test_drop_last_n_user_turns_clears_reference_context_for_mixed_developer_context_bundles() -> None:
    """Rust unit test: ``drop_last_n_user_turns_clears_reference_context_for_mixed_developer_context_bundles``."""

    items = (
        _user_msg("turn 1 user"),
        _assistant_msg("turn 1 assistant"),
        _developer_msg_with_fragments(
            (
                "<permissions instructions>contextual permissions</permissions instructions>",
                "persistent plugin instructions",
            )
        ),
        _user_msg("<environment_context><cwd>PRETURN_CONTEXT_DIFF_CWD</cwd></environment_context>"),
        _user_msg("turn 2 user"),
        _assistant_msg("turn 2 assistant"),
    )
    history = ContextManager.from_items(items)
    history.set_reference_context_item(_reference_context_item())

    history.drop_last_n_user_turns(1)

    assert history.for_prompt(("text", "image")) == [
        _user_msg("turn 1 user"),
        _assistant_msg("turn 1 assistant"),
    ]
    assert history.reference_context_item() is None


def test_for_prompt_normalizes_outputs_and_strips_images() -> None:
    """Rust source contract: ``for_prompt`` applies normalize then image stripping."""

    function_call = ResponseItem.function_call("tool", "{}", "call-1")
    orphan = _function_call_output("orphan", "drop")
    image_message = ResponseItem.message(
        "user",
        (ContentItem.input_image("data:image/png;base64,AAA", detail=ImageDetail.HIGH),),
    )
    history = ContextManager.from_items((function_call, orphan, image_message))

    prompt_items = history.for_prompt(("text",))

    assert [item.type for item in prompt_items] == ["function_call", "function_call_output", "message"]
    assert prompt_items[1].call_id == "call-1"
    assert prompt_items[1].output.to_text() == "aborted"
    assert prompt_items[2].content == (ContentItem.input_text("image content omitted because you do not support image input"),)


def test_normalize_history_mutates_items_like_rust_helper() -> None:
    """Rust source contract: ``normalize_history`` mutates the stored history items."""

    function_call = ResponseItem.function_call("tool", "{}", "call-1")
    history = ContextManager.from_items((function_call,))

    history.normalize_history(("text", "image"))

    assert [item.type for item in history.raw_items()] == ["function_call", "function_call_output"]
    assert history.raw_items()[1].call_id == "call-1"


def test_module_function_matches_context_manager_method() -> None:
    """Rust source contract: module helper applies the same estimate as ``ContextManager``."""

    items = (_assistant_msg("hello from history"),)
    base = BaseInstructions("base instructions")

    assert estimate_token_count_with_base_instructions(items, base) == (
        ContextManager.from_items(items).estimate_token_count_with_base_instructions(base)
    )


def test_estimate_response_item_model_visible_bytes_uses_compact_json_mapping_bytes() -> None:
    """Rust source contract: fallback path measures compact serialized ``ResponseItem`` bytes."""

    item = _assistant_msg("hello")

    assert estimate_response_item_model_visible_bytes(item) == len(
        '{"type":"message","role":"assistant","content":[{"type":"output_text","text":"hello"}]}'.encode("utf-8")
    )


def test_estimate_response_item_model_visible_bytes_discounts_inline_image_payload() -> None:
    """Rust source contract: image data URLs replace raw base64 payload bytes with fixed image estimate."""

    image_url = "data:image/png;base64,QUJDREVGRw=="
    item = ResponseItem.message(
        "user",
        (ContentItem.input_image(image_url, detail=ImageDetail.HIGH),),
    )
    raw_json_bytes = len(item.to_mapping().__repr__().encode("utf-8"))
    compact_json_bytes = len(
        (
            '{"type":"message","role":"user","content":[{"type":"input_image",'
            '"image_url":"data:image/png;base64,QUJDREVGRw==","detail":"high"}]}'
        ).encode("utf-8")
    )

    assert raw_json_bytes != compact_json_bytes
    assert estimate_response_item_model_visible_bytes(item) == compact_json_bytes - len("QUJDREVGRw==") + 7373


def test_estimate_response_item_model_visible_bytes_uses_original_png_patch_estimate() -> None:
    """Rust source contract: original-detail image data URLs estimate bytes from 32px image patches."""

    png_1x1_payload = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    image_url = f"data:image/png;base64,{png_1x1_payload}"
    item = ResponseItem.message(
        "user",
        (ContentItem.input_image(image_url, detail=ImageDetail.ORIGINAL),),
    )
    compact_json_bytes = len(
        (
            '{"type":"message","role":"user","content":[{"type":"input_image",'
            f'"image_url":"{image_url}","detail":"original"'
            "}]}".encode("utf-8")
        )
    )

    assert estimate_response_item_model_visible_bytes(item) == compact_json_bytes - len(png_1x1_payload) + 4


def test_estimate_response_item_model_visible_bytes_falls_back_for_invalid_original_image_payload() -> None:
    """Rust source contract: undecodable original-detail images fall back to the resized image estimate."""

    invalid_payload = "not valid base64!"
    image_url = f"data:image/png;base64,{invalid_payload}"
    item = ResponseItem.message(
        "user",
        (ContentItem.input_image(image_url, detail=ImageDetail.ORIGINAL),),
    )
    compact_json_bytes = len(
        (
            '{"type":"message","role":"user","content":[{"type":"input_image",'
            f'"image_url":"{image_url}","detail":"original"'
            "}]}".encode("utf-8")
        )
    )

    assert estimate_response_item_model_visible_bytes(item) == compact_json_bytes - len(invalid_payload) + 7373


def test_remove_first_item_removes_matching_output_for_function_call() -> None:
    """Rust unit test: ``remove_first_item_removes_matching_output_for_function_call``."""

    history = ContextManager.from_items(
        (
            ResponseItem.function_call("do_it", "{}", "call-1"),
            _function_call_output("call-1"),
        )
    )

    history.remove_first_item()

    assert history.raw_items() == []


def test_remove_first_item_removes_matching_call_for_output() -> None:
    """Rust unit test: ``remove_first_item_removes_matching_call_for_output``."""

    history = ContextManager.from_items(
        (
            _function_call_output("call-2"),
            ResponseItem.function_call("do_it", "{}", "call-2"),
        )
    )

    history.remove_first_item()

    assert history.raw_items() == []


def test_remove_last_item_removes_matching_call_for_output() -> None:
    """Rust unit test: ``remove_last_item_removes_matching_call_for_output``."""

    prefix = _user_msg("before tool call")
    history = ContextManager.from_items(
        (
            prefix,
            ResponseItem.function_call("do_it", "{}", "call-delete-last"),
            _function_call_output("call-delete-last"),
        )
    )

    assert history.remove_last_item() is True
    assert history.raw_items() == [prefix]
    assert history.history_version == 1


def test_remove_first_item_handles_local_shell_pair() -> None:
    """Rust unit test: ``remove_first_item_handles_local_shell_pair``."""

    history = ContextManager.from_items(
        (
            ResponseItem(type="local_shell_call", call_id="call-3", status="completed"),
            _function_call_output("call-3"),
        )
    )

    history.remove_first_item()

    assert history.raw_items() == []


def test_remove_first_item_handles_custom_tool_pair() -> None:
    """Rust unit test: ``remove_first_item_handles_custom_tool_pair``."""

    history = ContextManager.from_items(
        (
            ResponseItem.custom_tool_call("my_tool", "{}", "tool-1"),
            ResponseItem(
                type="custom_tool_call_output",
                call_id="tool-1",
                output=FunctionCallOutputPayload.from_text("ok"),
            ),
        )
    )

    history.remove_first_item()

    assert history.raw_items() == []


def test_replace_last_turn_images_replaces_tool_output_images() -> None:
    """Rust unit test: ``replace_last_turn_images_replaces_tool_output_images``."""

    history = ContextManager.from_items(
        (
            _user_msg("hi"),
            _function_call_output_items(
                "call-1",
                (FunctionCallOutputContentItem.input_image("data:image/png;base64,AAA", detail=ImageDetail.HIGH),),
                success=True,
            ),
        )
    )

    assert history.replace_last_turn_images("Invalid image") is True

    assert history.raw_items() == [
        _user_msg("hi"),
        _function_call_output_items(
            "call-1",
            (FunctionCallOutputContentItem.input_text("Invalid image"),),
            success=True,
        ),
    ]
    assert history.history_version == 1


def test_replace_last_turn_images_does_not_touch_user_images() -> None:
    """Rust unit test: ``replace_last_turn_images_does_not_touch_user_images``."""

    items = (
        ResponseItem.message(
            "user",
            (ContentItem.input_image("data:image/png;base64,AAA", detail=ImageDetail.HIGH),),
        ),
    )
    history = ContextManager.from_items(items)

    assert history.replace_last_turn_images("Invalid image") is False
    assert history.raw_items() == list(items)
