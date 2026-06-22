"""Rust-derived tests for ``codex-code-mode/src/lib.rs``.

Rust crate: ``codex-code-mode``
Rust modules:
- ``src/lib.rs``
- ``src/description.rs``
- ``src/response.rs``

The V8 runtime modules are intentionally not exercised here; core-owned tests
cover the dependency-light service shim and this crate package exposes the
pure public facade.
"""

from __future__ import annotations

import pytest

import pycodex.code_mode as code_mode
from pycodex.protocol import ToolName


def _mcp_call_tool_result_schema(structured_content_schema: object) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "content": {"type": "array", "items": {"type": "object"}},
            "structuredContent": structured_content_schema,
            "isError": {"type": "boolean"},
            "_meta": {"type": "object"},
        },
        "required": ["content"],
        "additionalProperties": False,
    }


def test_crate_root_reexports_rust_public_facade() -> None:
    # Rust crate/module: codex-code-mode/src/lib.rs.
    # Contract: every public `pub use` and public tool-name constant from the
    # Rust crate root is available from the Python package root.
    expected = {
        "CODE_MODE_PRAGMA_PREFIX",
        "CodeModeToolKind",
        "ToolDefinition",
        "ToolNamespaceDescription",
        "augment_tool_definition",
        "build_exec_tool_description",
        "build_wait_tool_description",
        "is_code_mode_nested_tool",
        "normalize_code_mode_identifier",
        "parse_exec_source",
        "render_code_mode_sample",
        "render_json_schema_to_typescript",
        "DEFAULT_IMAGE_DETAIL",
        "FunctionCallOutputContentItem",
        "ImageDetail",
        "CodeModeNestedToolCall",
        "DEFAULT_EXEC_YIELD_TIME_MS",
        "DEFAULT_MAX_OUTPUT_TOKENS_PER_EXEC_CALL",
        "DEFAULT_WAIT_YIELD_TIME_MS",
        "ExecuteRequest",
        "ExecuteToPendingOutcome",
        "RuntimeResponse",
        "WaitOutcome",
        "WaitRequest",
        "WaitToPendingOutcome",
        "WaitToPendingRequest",
        "CodeModeService",
        "CodeModeTurnHost",
        "CodeModeTurnWorker",
        "PUBLIC_TOOL_NAME",
        "WAIT_TOOL_NAME",
    }

    missing = sorted(name for name in expected if not hasattr(code_mode, name))

    assert missing == []
    assert expected.issubset(set(code_mode.__all__))


def test_description_contracts_match_rust_tests_through_crate_facade() -> None:
    # Rust crate/module/tests: codex-code-mode/src/description.rs tests
    # parse_exec_source_with_pragma,
    # code_mode_only_description_groups_namespace_instructions_once, and
    # code_mode_only_description_renders_shared_mcp_types_once.
    parsed = code_mode.parse_exec_source(
        '// @exec: {"yield_time_ms": 10, "max_output_tokens": 20}\ntext("hi")'
    )
    assert parsed.code == 'text("hi")'
    assert parsed.yield_time_ms == 10
    assert parsed.max_output_tokens == 20

    namespace_descriptions = {
        "mcp__sample__": code_mode.ToolNamespaceDescription(
            name="mcp__sample",
            description="Shared namespace guidance.",
        )
    }
    tools = (
        code_mode.ToolDefinition(
            name="mcp__sample__alpha",
            tool_name=ToolName.namespaced("mcp__sample__", "alpha"),
            description="First tool",
            kind=code_mode.CodeModeToolKind.FUNCTION,
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            output_schema=_mcp_call_tool_result_schema(
                {"type": "object", "properties": {}, "additionalProperties": False}
            ),
        ),
        code_mode.ToolDefinition(
            name="mcp__sample__beta",
            tool_name=ToolName.namespaced("mcp__sample__", "beta"),
            description="Second tool",
            kind=code_mode.CodeModeToolKind.FUNCTION,
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            output_schema=_mcp_call_tool_result_schema(
                {"type": "object", "properties": {}, "additionalProperties": False}
            ),
        ),
    )

    description = code_mode.build_exec_tool_description(
        tools,
        namespace_descriptions,
        code_mode_only=True,
        deferred_tools_available=False,
    )

    assert description.count("## mcp__sample") == 1
    assert "## mcp__sample\nShared namespace guidance." in description
    assert description.count("Shared MCP Types:") == 1
    assert (
        "declare const tools: { mcp__sample__alpha(args: {}): "
        "Promise<CallToolResult<{}>>; };"
    ) in description
    assert (
        "declare const tools: { mcp__sample__beta(args: {}): "
        "Promise<CallToolResult<{}>>; };"
    ) in description


def test_response_types_match_rust_serialization_surface() -> None:
    # Rust crate/module: codex-code-mode/src/response.rs.
    # Contract: ImageDetail uses lowercase wire values, DEFAULT_IMAGE_DETAIL
    # is High, and content items use the input_text/input_image tagged shape.
    assert code_mode.DEFAULT_IMAGE_DETAIL is code_mode.ImageDetail.HIGH
    assert code_mode.ImageDetail.AUTO.value == "auto"
    assert code_mode.ImageDetail.ORIGINAL.value == "original"

    text = code_mode.FunctionCallOutputContentItem.input_text("hello")
    image = code_mode.FunctionCallOutputContentItem.input_image(
        "data:image/png;base64,AAA",
        code_mode.ImageDetail.ORIGINAL,
    )

    assert text.to_mapping() == {"type": "input_text", "text": "hello"}
    assert image.to_mapping() == {
        "type": "input_image",
        "image_url": "data:image/png;base64,AAA",
        "detail": "original",
    }


def test_runtime_public_models_match_rust_runtime_mod_contracts() -> None:
    # Rust crate/module: codex-code-mode/src/runtime/mod.rs.
    # Rust anchors: ExecuteRequest, WaitRequest, WaitToPendingRequest,
    # RuntimeResponse, WaitOutcome, ExecuteToPendingOutcome,
    # WaitToPendingOutcome, CodeModeNestedToolCall, and
    # impl From<WaitOutcome> for RuntimeResponse.
    tool_definition = code_mode.ToolDefinition(
        name="lookup_order",
        tool_name=ToolName.plain("lookup_order"),
        description="Look up",
        kind=code_mode.CodeModeToolKind.FUNCTION,
        input_schema={"type": "object"},
    )

    request = code_mode.ExecuteRequest(
        cell_id="cell-1",
        tool_call_id="call-1",
        enabled_tools=[tool_definition],
        source="text('hi')",
        yield_time_ms=5,
        max_output_tokens=10,
    )
    assert request.cell_id == "cell-1"
    assert request.tool_call_id == "call-1"
    assert request.enabled_tools == (tool_definition,)
    assert request.source == "text('hi')"
    assert request.yield_time_ms == 5
    assert request.max_output_tokens == 10

    wait_request = code_mode.WaitRequest(
        cell_id="cell-1",
        yield_time_ms=11,
        terminate=True,
    )
    assert wait_request.cell_id == "cell-1"
    assert wait_request.yield_time_ms == 11
    assert wait_request.terminate is True
    assert code_mode.WaitToPendingRequest("cell-1").cell_id == "cell-1"

    yielded = code_mode.RuntimeResponse.from_mapping(
        {
            "Yielded": {
                "cell_id": "cell-1",
                "content_items": [{"type": "input_text", "text": "running"}],
            }
        }
    )
    assert yielded == code_mode.RuntimeResponse.yielded(
        cell_id="cell-1",
        content_items=(code_mode.FunctionCallOutputContentItem.input_text("running"),),
    )
    assert yielded.to_mapping() == {
        "type": "yielded",
        "cell_id": "cell-1",
        "content_items": [{"type": "input_text", "text": "running"}],
    }

    result = code_mode.RuntimeResponse.from_mapping(
        {
            "Result": {
                "cell_id": "cell-1",
                "content_items": [{"type": "input_text", "text": "done"}],
                "error_text": None,
            }
        }
    )
    assert result == code_mode.RuntimeResponse.result(
        cell_id="cell-1",
        content_items=(code_mode.FunctionCallOutputContentItem.input_text("done"),),
    )
    assert code_mode.WaitOutcome.live_cell(result).into_runtime_response() == result
    assert code_mode.WaitOutcome.missing_cell({"Result": {
        "cell_id": "missing",
        "content_items": [],
        "error_text": "exec cell missing not found",
    }}).into_runtime_response() == code_mode.RuntimeResponse.result(
        cell_id="missing",
        error_text="exec cell missing not found",
    )

    pending = code_mode.ExecuteToPendingOutcome.pending(
        cell_id="cell-1",
        content_items=(code_mode.FunctionCallOutputContentItem.input_text("pending"),),
        pending_tool_call_ids=("tool-1", "tool-2"),
    )
    assert pending.cell_id == "cell-1"
    assert pending.pending_tool_call_ids == ("tool-1", "tool-2")
    assert code_mode.ExecuteToPendingOutcome.completed(
        {"Terminated": {"cell_id": "cell-2", "content_items": []}}
    ).response == code_mode.RuntimeResponse.terminated(cell_id="cell-2")
    assert code_mode.WaitToPendingOutcome.live_cell(
        {
            "Pending": {
                "cell_id": "cell-1",
                "content_items": [],
                "pending_tool_call_ids": ["tool-3"],
            }
        }
    ).outcome == code_mode.ExecuteToPendingOutcome.pending(
        cell_id="cell-1",
        pending_tool_call_ids=("tool-3",),
    )
    assert code_mode.WaitToPendingOutcome.missing_cell(result).response == result

    nested_call_input = {"order_id": "42"}
    nested_call = code_mode.CodeModeNestedToolCall(
        cell_id="cell-1",
        runtime_tool_call_id="runtime-tool-1",
        tool_name=ToolName.plain("lookup_order"),
        tool_kind=code_mode.CodeModeToolKind.FUNCTION,
        input=nested_call_input,
    )
    nested_call_input["order_id"] = "changed"
    assert nested_call.cell_id == "cell-1"
    assert nested_call.runtime_tool_call_id == "runtime-tool-1"
    assert nested_call.tool_name == ToolName.plain("lookup_order")
    assert nested_call.tool_kind is code_mode.CodeModeToolKind.FUNCTION
    assert nested_call.input == {"order_id": "42"}


def test_service_public_facade_matches_rust_service_contracts() -> None:
    # Rust crate/module: codex-code-mode/src/service.rs.
    # Rust tests/contracts: CodeModeService::new, allocate_cell_id,
    # wait_reports_missing_cell_separately_from_runtime_results, and the
    # service pending/completed lifecycle paths that carry RuntimeResponse,
    # ExecuteToPendingOutcome, WaitOutcome, and WaitToPendingOutcome.
    service = code_mode.CodeModeService()

    assert service.allocate_cell_id() == "1"
    assert service.allocate_cell_id() == "2"
    assert service.wait(code_mode.WaitRequest(cell_id="missing")) == code_mode.WaitOutcome.missing_cell(
        code_mode.RuntimeResponse.result(
            cell_id="missing",
            error_text="exec cell missing not found",
        )
    )
    assert service.wait_to_pending({"cell_id": "missing"}) == code_mode.WaitToPendingOutcome.missing_cell(
        code_mode.RuntimeResponse.result(
            cell_id="missing",
            error_text="exec cell missing not found",
        )
    )

    captured_execute: list[code_mode.ExecuteRequest] = []
    captured_wait: list[code_mode.WaitRequest] = []
    captured_wait_to_pending: list[code_mode.WaitToPendingRequest] = []

    def execute_callback(request: code_mode.ExecuteRequest) -> code_mode.RuntimeResponse:
        captured_execute.append(request)
        return code_mode.RuntimeResponse.result(
            cell_id=request.cell_id,
            content_items=(code_mode.FunctionCallOutputContentItem.input_text(request.source),),
        )

    def wait_callback(request: code_mode.WaitRequest) -> code_mode.RuntimeResponse:
        captured_wait.append(request)
        return code_mode.RuntimeResponse.terminated(cell_id=request.cell_id)

    def wait_to_pending_callback(
        request: code_mode.WaitToPendingRequest,
    ) -> code_mode.ExecuteToPendingOutcome:
        captured_wait_to_pending.append(request)
        return code_mode.ExecuteToPendingOutcome.completed(
            code_mode.RuntimeResponse.result(cell_id=request.cell_id)
        )

    callback_service = code_mode.CodeModeService(
        execute_callback=execute_callback,
        wait_callback=wait_callback,
        wait_to_pending_callback=wait_to_pending_callback,
    )
    request = code_mode.ExecuteRequest(
        cell_id="cell-1",
        tool_call_id="call-1",
        enabled_tools=(),
        source="text('hi')",
    )

    assert callback_service.execute(request) == code_mode.RuntimeResponse.result(
        cell_id="cell-1",
        content_items=(code_mode.FunctionCallOutputContentItem.input_text("text('hi')"),),
    )
    assert callback_service.execute_to_pending(request) == code_mode.ExecuteToPendingOutcome.completed(
        code_mode.RuntimeResponse.result(
            cell_id="cell-1",
            content_items=(code_mode.FunctionCallOutputContentItem.input_text("text('hi')"),),
        )
    )
    assert callback_service.wait({"cell_id": "cell-1", "yield_time_ms": 7}) == code_mode.WaitOutcome.live_cell(
        code_mode.RuntimeResponse.terminated(cell_id="cell-1")
    )
    assert callback_service.wait_to_pending({"cell_id": "cell-1"}) == code_mode.WaitToPendingOutcome.live_cell(
        code_mode.ExecuteToPendingOutcome.completed(
            code_mode.RuntimeResponse.result(cell_id="cell-1")
        )
    )

    assert captured_execute == [request, request]
    assert captured_wait == [code_mode.WaitRequest(cell_id="cell-1", yield_time_ms=7)]
    assert captured_wait_to_pending == [code_mode.WaitToPendingRequest(cell_id="cell-1")]


def test_exec_pragma_error_contracts_match_rust() -> None:
    # Rust crate/module: codex-code-mode/src/description.rs::parse_exec_source.
    with pytest.raises(ValueError, match="raw JavaScript source text"):
        code_mode.parse_exec_source("   ")
    with pytest.raises(ValueError, match="must be followed by JavaScript"):
        code_mode.parse_exec_source('// @exec: {"yield_time_ms": 1}')
    with pytest.raises(ValueError, match="only supports"):
        code_mode.parse_exec_source('// @exec: {"bad": 1}\n1')
    with pytest.raises(ValueError, match="non-negative safe integer"):
        code_mode.parse_exec_source('// @exec: {"yield_time_ms": 9007199254740992}\n1')
