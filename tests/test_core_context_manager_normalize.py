"""Parity tests for ``codex-rs/core/src/context_manager/normalize.rs``."""

from pycodex.core.context_manager.normalize import (
    IMAGE_CONTENT_OMITTED_PLACEHOLDER,
    ensure_call_outputs_present,
    normalize_call_outputs,
    remove_corresponding_for,
    remove_orphan_outputs,
    strip_images_when_unsupported,
)
from pycodex.protocol import ContentItem, FunctionCallOutputContentItem, FunctionCallOutputPayload, ImageDetail, ResponseItem


def _function_call_output(call_id: str, output: str = "ok") -> ResponseItem:
    return ResponseItem(type="function_call_output", call_id=call_id, output=FunctionCallOutputPayload.from_text(output))


def _custom_tool_call_output(call_id: str, output: str = "ok") -> ResponseItem:
    return ResponseItem(type="custom_tool_call_output", call_id=call_id, output=FunctionCallOutputPayload.from_text(output))


def _local_shell_call(call_id: str) -> ResponseItem:
    return ResponseItem.from_mapping(
        {
            "type": "local_shell_call",
            "call_id": call_id,
            "status": "completed",
            "action": {"type": "exec", "command": ["echo", "hi"]},
        }
    )


def _tool_search_output(call_id: str | None, *, execution: str = "client") -> ResponseItem:
    return ResponseItem(type="tool_search_output", call_id=call_id, status="completed", execution=execution, tools=())


def test_ensure_call_outputs_present_inserts_synthetic_outputs_after_calls() -> None:
    """Rust tests: missing function/custom/local-shell outputs and tool search output insertion."""

    function_call = ResponseItem.function_call("do_it", "{}", "call-x")
    tool_search_call = ResponseItem.tool_search_call("{}", call_id="search-call-x", execution="client")
    custom_tool_call = ResponseItem.custom_tool_call("custom", "{}", "tool-x")
    local_shell_call = _local_shell_call("shell-1")
    existing_call = ResponseItem.function_call("already", "{}", "done-1")
    existing_output = _function_call_output("done-1")

    normalized = ensure_call_outputs_present(
        (function_call, tool_search_call, custom_tool_call, local_shell_call, existing_call, existing_output)
    )

    assert [item.type for item in normalized] == [
        "function_call",
        "function_call_output",
        "tool_search_call",
        "tool_search_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "local_shell_call",
        "function_call_output",
        "function_call",
        "function_call_output",
    ]
    assert normalized[1].call_id == "call-x"
    assert normalized[1].output.to_text() == "aborted"
    assert normalized[3].call_id == "search-call-x"
    assert normalized[3].status == "completed"
    assert normalized[3].execution == "client"
    assert normalized[3].tools == ()
    assert normalized[5].call_id == "tool-x"
    assert normalized[5].output.to_text() == "aborted"
    assert normalized[7].call_id == "shell-1"
    assert normalized[7].output.to_text() == "aborted"
    assert normalized[-1] is existing_output


def test_remove_orphan_outputs_keeps_only_outputs_with_matching_calls() -> None:
    """Rust tests: orphan outputs are removed while matching and server search outputs remain."""

    function_call = ResponseItem.function_call("tool", "{}", "call-1")
    function_output = _function_call_output("call-1")
    local_shell_call = _local_shell_call("shell-1")
    local_shell_output = _function_call_output("shell-1")
    tool_search_call = ResponseItem.tool_search_call("{}", call_id="search-1", execution="client")
    paired_search_output = _tool_search_output("search-1")
    server_search_output = _tool_search_output("server-1", execution="server")
    unpaired_search_output = _tool_search_output(None)
    custom_tool_call = ResponseItem.custom_tool_call("custom", "input", "custom-1")
    custom_tool_output = _custom_tool_call_output("custom-1")

    retained = remove_orphan_outputs(
        (
            function_call,
            function_output,
            _function_call_output("orphan-function"),
            local_shell_call,
            local_shell_output,
            tool_search_call,
            paired_search_output,
            server_search_output,
            unpaired_search_output,
            _tool_search_output("orphan-search"),
            custom_tool_call,
            custom_tool_output,
            _custom_tool_call_output("orphan-custom"),
        )
    )

    assert retained == (
        function_call,
        function_output,
        local_shell_call,
        local_shell_output,
        tool_search_call,
        paired_search_output,
        server_search_output,
        unpaired_search_output,
        custom_tool_call,
        custom_tool_output,
    )


def test_normalize_call_outputs_inserts_missing_outputs_then_removes_orphans() -> None:
    """Rust unit test: ``normalize_mixed_inserts_and_removals`` core contract."""

    function_call = ResponseItem.function_call("f1", "{}", "c1")
    orphan = _function_call_output("c2")
    custom_tool_call = ResponseItem.custom_tool_call("tool", "{}", "t1")
    local_shell_call = _local_shell_call("s1")

    normalized = normalize_call_outputs((function_call, orphan, custom_tool_call, local_shell_call))

    assert [item.type for item in normalized] == [
        "function_call",
        "function_call_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "local_shell_call",
        "function_call_output",
    ]
    assert normalized[1].call_id == "c1"
    assert normalized[1].output.to_text() == "aborted"
    assert normalized[3].call_id == "t1"
    assert normalized[3].output.to_text() == "aborted"
    assert normalized[5].call_id == "s1"
    assert normalized[5].output.to_text() == "aborted"


def test_remove_corresponding_for_prefers_function_call_before_local_shell() -> None:
    """Rust source contract: function-call-output removal searches function call before local shell."""

    function_call = ResponseItem.function_call("tool", "{}", "shared")
    local_shell_call = _local_shell_call("shared")
    items = [local_shell_call, function_call]

    remove_corresponding_for(items, _function_call_output("shared"))

    assert items == [local_shell_call]


def test_strip_images_when_unsupported_replaces_images_and_clears_image_generation_result() -> None:
    """Rust tests: ``for_prompt_strips_images_when_model_does_not_support_images`` and image generation clearing."""

    message = ResponseItem.message(
        "user",
        (
            ContentItem.input_text("look at this"),
            ContentItem.input_image("https://example.com/img.png", detail=ImageDetail.HIGH),
            ContentItem.input_text("caption"),
        ),
    )
    function_output = ResponseItem(
        type="function_call_output",
        call_id="call-1",
        output=FunctionCallOutputPayload.from_content_items(
            (
                FunctionCallOutputContentItem.input_text("image result"),
                FunctionCallOutputContentItem.input_image("https://example.com/result.png", detail=ImageDetail.HIGH),
            )
        ),
    )
    custom_output = ResponseItem(
        type="custom_tool_call_output",
        call_id="tool-1",
        output=FunctionCallOutputPayload.from_content_items(
            (
                FunctionCallOutputContentItem.input_text("js repl result"),
                FunctionCallOutputContentItem.input_image("https://example.com/js-repl-result.png", detail=ImageDetail.HIGH),
            ),
            success=True,
        ),
    )
    image_generation = ResponseItem.image_generation_call("ig_123", "completed", "Zm9v", revised_prompt="lobster")

    stripped = strip_images_when_unsupported(("text",), (message, function_output, custom_output, image_generation))

    assert stripped[0].content == (
        ContentItem.input_text("look at this"),
        ContentItem.input_text(IMAGE_CONTENT_OMITTED_PLACEHOLDER),
        ContentItem.input_text("caption"),
    )
    assert stripped[1].output.content_items == (
        FunctionCallOutputContentItem.input_text("image result"),
        FunctionCallOutputContentItem.input_text(IMAGE_CONTENT_OMITTED_PLACEHOLDER),
    )
    assert stripped[2].output.content_items == (
        FunctionCallOutputContentItem.input_text("js repl result"),
        FunctionCallOutputContentItem.input_text(IMAGE_CONTENT_OMITTED_PLACEHOLDER),
    )
    assert stripped[2].output.success is True
    assert stripped[3].result == ""


def test_strip_images_when_supported_preserves_history() -> None:
    """Rust tests: image input support preserves message images and image-generation result."""

    message = ResponseItem.message(
        "user",
        (ContentItem.input_image("https://example.com/img.png", detail=ImageDetail.HIGH),),
    )
    image_generation = ResponseItem.image_generation_call("ig_123", "generating", "Zm9v", revised_prompt="lobster")

    assert strip_images_when_unsupported(("text", "image"), (image_generation, message)) == (image_generation, message)
