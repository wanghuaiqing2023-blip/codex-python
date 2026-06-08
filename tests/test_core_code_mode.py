import unittest
from types import SimpleNamespace

from pycodex.core.tools.code_mode import (
    CODE_MODE_FREEFORM_GRAMMAR,
    EXEC_MAIN_MODULE_NAME,
    CodeModeExecuteHandler,
    CodeModeRuntimeStore,
    CodeModeRuntimeToolState,
    CodeModeService,
    CodeModeNestedToolCall,
    CodeModeToolDefinition,
    CodeModeToolKind,
    CodeModeWaitHandler,
    CompletionState,
    ExecWaitArgs,
    ExecuteRequest,
    ExecuteToPendingOutcome,
    EXIT_SENTINEL,
    NextRuntimeCommandResult,
    PendingResult,
    PendingRuntimeMode,
    ParsedExecSource,
    RUNTIME_TOOL_CALL_ID_PREFIX,
    RuntimeCommand,
    RuntimeControlCommand,
    RuntimeEvent,
    RuntimeResponse,
    ToolNamespaceDescription,
    U64_MAX,
    UNSUPPORTED_DYNAMIC_IMPORT_ERROR,
    WaitOutcome,
    WaitRequest,
    WaitToPendingOutcome,
    augment_tool_spec_for_code_mode,
    build_all_tools_metadata,
    build_exec_tool_description,
    build_nested_tool_payload,
    build_runtime_image_event,
    build_runtime_notify_event,
    build_runtime_text_event,
    build_runtime_tool_call_event,
    build_runtime_yield_event,
    build_wait_tool_description,
    code_mode_namespace_name,
    code_mode_name_for_tool_name,
    collect_code_mode_exec_prompt_tool_definitions,
    clear_timeout_id_from_value,
    completion_state_from_exit,
    completion_state_from_rejection,
    create_code_mode_tool,
    create_wait_tool,
    enabled_tool_metadata,
    format_script_status,
    handle_runtime_response,
    into_function_call_output_content_items,
    is_exec_tool_name,
    is_exit_exception,
    is_exit_sentinel,
    missing_cell_response,
    next_runtime_command,
    next_runtime_tool_call_sequence,
    normalize_notify_text,
    normalize_output_image,
    normalize_code_mode_identifier,
    normalize_runtime_tool_input,
    normalize_store_key,
    normalize_timeout_delay_ms,
    parse_exec_source,
    parse_wait_arguments,
    pending_result_response,
    render_json_schema_to_typescript,
    runtime_exit_exception,
    runtime_tool_call_id,
    runtime_tool_index_from_callback_data,
    script_status_header,
    serialize_output_text,
    serialize_stored_value,
    sort_code_mode_tool_definitions,
    tool_spec_to_code_mode_tool_definition,
    truncate_code_mode_result,
    unsupported_dynamic_import_error,
    unsupported_static_import_error,
    value_to_error_text,
)
from pycodex.core.tools.context import ToolPayload
from pycodex.protocol import DEFAULT_IMAGE_DETAIL, FunctionCallOutputContentItem, ImageDetail, ToolName
from pycodex import code_mode as external_code_mode


def function_spec(name: str, description: str = "Tool") -> dict[str, object]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        },
    }


def mcp_call_tool_result_schema(structured_content_schema: object) -> dict[str, object]:
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


class CodeModeTests(unittest.TestCase):
    def test_parse_exec_source_supports_optional_pragma(self) -> None:
        self.assertEqual(parse_exec_source("text('hi')"), ParsedExecSource(code="text('hi')"))
        self.assertEqual(
            parse_exec_source(
                '// @exec: {"yield_time_ms": 10, "max_output_tokens": 20}\ntext("hi")'
            ),
            ParsedExecSource(
                code='text("hi")',
                yield_time_ms=10,
                max_output_tokens=20,
            ),
        )

        with self.assertRaisesRegex(ValueError, "only supports"):
            parse_exec_source('// @exec: {"unknown": 1}\ntext("hi")')

    def test_code_mode_name_matches_upstream_namespace_rules(self) -> None:
        self.assertEqual(code_mode_name_for_tool_name(ToolName.plain("apply_patch")), "apply_patch")
        self.assertEqual(
            code_mode_name_for_tool_name(ToolName.namespaced("mcp__calendar__", "create_event")),
            "mcp__calendar__create_event",
        )
        self.assertEqual(
            code_mode_name_for_tool_name(ToolName.namespaced("codex_app", "automation_update")),
            "codex_app_automation_update",
        )
        self.assertEqual(
            code_mode_name_for_tool_name(ToolName.namespaced("codex_app", "_hidden")),
            "codex_app_hidden",
        )

    def test_collect_exec_prompt_definitions_sorts_dedups_and_skips_exec_wait(self) -> None:
        specs = [
            {"type": "custom", "name": "apply_patch", "description": "Apply a patch"},
            {"type": "function", "name": "exec", "description": "Run code", "parameters": {}},
            {"type": "function", "name": "wait", "description": "Wait", "parameters": {}},
            {
                "type": "namespace",
                "name": "mcp__calendar__",
                "tools": [
                    {"type": "function", "name": "create_event", "description": "Create"},
                    {"type": "function", "name": "create_event", "description": "Duplicate"},
                ],
            },
            {
                "type": "namespace",
                "name": "codex_app",
                "tools": [
                    {
                        "type": "function",
                        "name": "automation_update",
                        "description": "Automate",
                    }
                ],
            },
            {"type": "web_search", "external_web_access": True},
        ]

        definitions = collect_code_mode_exec_prompt_tool_definitions(specs)

        self.assertEqual(
            [definition.name for definition in definitions],
            ["apply_patch", "codex_app_automation_update", "mcp__calendar__create_event"],
        )
        self.assertEqual(definitions[0].kind, CodeModeToolKind.FREEFORM)
        self.assertEqual(
            definitions[2].tool_name,
            ToolName.namespaced("mcp__calendar__", "create_event"),
        )

    def test_sort_code_mode_tool_definitions_matches_upstream_namespace_order(self) -> None:
        definitions = [
            CodeModeToolDefinition(
                name="mcp__beta__search",
                tool_name=ToolName.namespaced("mcp__beta__", "search"),
                description="Beta search",
                kind=CodeModeToolKind.FUNCTION,
            ),
            CodeModeToolDefinition(
                name="mcp__alpha__list",
                tool_name=ToolName.namespaced("mcp__alpha__", "list"),
                description="Alpha list",
                kind=CodeModeToolKind.FUNCTION,
            ),
            CodeModeToolDefinition(
                name="z_direct",
                tool_name=ToolName.plain("z_direct"),
                description="Direct",
                kind=CodeModeToolKind.FUNCTION,
            ),
            CodeModeToolDefinition(
                name="mcp__unknown__aaa",
                tool_name=ToolName.namespaced("mcp__unknown__", "aaa"),
                description="Unknown namespace",
                kind=CodeModeToolKind.FUNCTION,
            ),
        ]
        namespace_descriptions = {
            "mcp__beta__": ToolNamespaceDescription("Beta", "Beta tools."),
            "mcp__alpha__": ToolNamespaceDescription("Alpha", "Alpha tools."),
        }

        sorted_definitions = sort_code_mode_tool_definitions(definitions, namespace_descriptions)

        self.assertEqual(
            [definition.name for definition in sorted_definitions],
            ["mcp__unknown__aaa", "z_direct", "mcp__alpha__list", "mcp__beta__search"],
        )
        self.assertEqual(
            code_mode_namespace_name(definitions[1], namespace_descriptions),
            "Alpha",
        )
        self.assertIsNone(code_mode_namespace_name(definitions[2], namespace_descriptions))

    def test_build_all_tools_metadata_matches_runtime_globals_shape(self) -> None:
        definition = CodeModeToolDefinition(
            name="hidden-dynamic-tool",
            tool_name=ToolName.plain("hidden-dynamic-tool"),
            description="Hidden dynamic tool.",
            kind=CodeModeToolKind.FREEFORM,
        )
        metadata = enabled_tool_metadata(definition)

        self.assertEqual(metadata.global_name, "hidden_dynamic_tool")
        self.assertEqual(
            build_all_tools_metadata([definition, metadata]),
            (
                {"name": "hidden_dynamic_tool", "description": "Hidden dynamic tool."},
                {"name": "hidden_dynamic_tool", "description": "Hidden dynamic tool."},
            ),
        )

    def test_tool_spec_to_code_mode_definition_returns_augmented_freeform_tool(self) -> None:
        spec = {"type": "custom", "name": "apply_patch", "description": "Apply a patch"}

        self.assertEqual(
            tool_spec_to_code_mode_tool_definition(spec),
            CodeModeToolDefinition(
                name="apply_patch",
                tool_name=ToolName.plain("apply_patch"),
                description=(
                    "Apply a patch\n\n"
                    "exec tool declaration:\n"
                    "```ts\n"
                    "declare const tools: { apply_patch(input: string): Promise<unknown>; };\n"
                    "```"
                ),
                kind=CodeModeToolKind.FREEFORM,
            ),
        )

    def test_augment_tool_spec_for_code_mode_updates_descriptions(self) -> None:
        augmented = augment_tool_spec_for_code_mode(function_spec("lookup_order", "Look up an order"))

        self.assertEqual(
            augmented["description"],
            (
                "Look up an order\n\n"
                "exec tool declaration:\n"
                "```ts\n"
                "declare const tools: { "
                "lookup_order(args: { order_id: string; }): Promise<{ ok: boolean; }>; "
                "};\n"
                "```"
            ),
        )

        exec_spec = {"type": "custom", "name": "exec", "description": "Run code"}
        self.assertEqual(augment_tool_spec_for_code_mode(exec_spec)["description"], "Run code")

    def test_render_json_schema_to_typescript_includes_property_comments(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "weather": {
                    "type": "array",
                    "description": "look up weather for a given list of locations",
                    "items": {
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                        "required": ["location"],
                    },
                }
            },
            "required": ["weather"],
        }

        self.assertEqual(
            render_json_schema_to_typescript(schema),
            (
                "{\n"
                "  // look up weather for a given list of locations\n"
                "  weather: Array<{ location: string; }>;\n"
                "}"
            ),
        )

    def test_exec_description_groups_namespaces_and_shared_mcp_types(self) -> None:
        definitions = [
            CodeModeToolDefinition(
                name="mcp__sample__alpha",
                tool_name=ToolName.namespaced("mcp__sample__", "alpha"),
                description="First tool",
                kind=CodeModeToolKind.FUNCTION,
                input_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                output_schema=mcp_call_tool_result_schema(
                    {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    }
                ),
            ),
            CodeModeToolDefinition(
                name="mcp__sample__beta",
                tool_name=ToolName.namespaced("mcp__sample__", "beta"),
                description="Second tool",
                kind=CodeModeToolKind.FUNCTION,
                input_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                output_schema=mcp_call_tool_result_schema(
                    {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    }
                ),
            ),
        ]

        description = build_exec_tool_description(
            definitions,
            {
                "mcp__sample__": ToolNamespaceDescription(
                    name="mcp__sample",
                    description="Shared namespace guidance.",
                )
            },
            code_mode_only=True,
            deferred_tools_available=True,
        )

        self.assertEqual(description.count("## mcp__sample"), 1)
        self.assertIn("## mcp__sample\nShared namespace guidance.", description)
        self.assertIn("Some nested MCP/app tools may be omitted", description)
        self.assertEqual(
            description.count("type CallToolResult<TStructured = { [key: string]: unknown }>"),
            1,
        )
        self.assertIn(
            "declare const tools: { "
            "mcp__sample__alpha(args: {}): Promise<CallToolResult<{}>>; };",
            description,
        )

    def test_normalize_identifier_rewrites_invalid_characters(self) -> None:
        self.assertEqual(
            normalize_code_mode_identifier("mcp__ologs__get_profile"),
            "mcp__ologs__get_profile",
        )
        self.assertEqual(normalize_code_mode_identifier("hidden-dynamic-tool"), "hidden_dynamic_tool")
        self.assertEqual(normalize_code_mode_identifier("1bad"), "_bad")


    def test_code_mode_structs_reject_implicit_coercions(self) -> None:
        with self.assertRaises(TypeError):
            CodeModeToolDefinition(
                name=123,
                tool_name=ToolName.plain("lookup_order"),
                description="Look up",
                kind=CodeModeToolKind.FUNCTION,
            )
        with self.assertRaises(TypeError):
            ToolNamespaceDescription("sample", 123)
        with self.assertRaises(ValueError):
            ExecWaitArgs(cell_id="cell-1", yield_time_ms=True)
        with self.assertRaises(TypeError):
            ExecWaitArgs(cell_id="cell-1", terminate=1)
        with self.assertRaises(TypeError):
            ExecuteRequest(
                cell_id=1,
                tool_call_id="call-1",
                enabled_tools=(),
                source="text('hi')",
            )
        with self.assertRaises(TypeError):
            RuntimeResponse.result(cell_id="cell-1", error_text=123)
        with self.assertRaises(TypeError):
            ExecuteToPendingOutcome.pending(cell_id="cell-1", pending_tool_call_ids=(1,))
        with self.assertRaises(TypeError):
            CodeModeRuntimeStore({1: {"count": 1}})

    def test_runtime_requests_and_outcomes_coerce_upstream_shapes(self) -> None:
        tool_definition = CodeModeToolDefinition(
            name="lookup_order",
            tool_name=ToolName.plain("lookup_order"),
            description="Look up",
            kind=CodeModeToolKind.FUNCTION,
        )
        request = ExecuteRequest(
            cell_id="cell-1",
            tool_call_id="call-1",
            enabled_tools=[tool_definition],
            source="text('hi')",
            yield_time_ms=5,
            max_output_tokens=10,
        )
        self.assertEqual(request.enabled_tools, (tool_definition,))

        wait_request = WaitRequest(cell_id="cell-1", yield_time_ms=10, terminate=True)
        self.assertTrue(wait_request.terminate)

        response = RuntimeResponse.from_mapping(
            {
                "Result": {
                    "cell_id": "cell-1",
                    "content_items": [{"type": "input_text", "text": "done"}],
                    "error_text": None,
                }
            }
        )
        self.assertEqual(
            response,
            RuntimeResponse.result(
                cell_id="cell-1",
                content_items=(FunctionCallOutputContentItem.input_text("done"),),
            ),
        )
        self.assertEqual(WaitOutcome.live_cell(response).into_runtime_response(), response)
        self.assertEqual(
            ExecuteToPendingOutcome.pending(
                cell_id="cell-1",
                content_items=(FunctionCallOutputContentItem.input_text("pending"),),
                pending_tool_call_ids=("tool-1",),
            ).pending_tool_call_ids,
            ("tool-1",),
        )
        self.assertEqual(
            WaitToPendingOutcome.missing_cell(response).response,
            response,
        )

    def test_script_status_helpers_match_core_code_mode_text(self) -> None:
        self.assertTrue(is_exec_tool_name(ToolName.plain("exec")))
        self.assertFalse(is_exec_tool_name(ToolName.namespaced("mcp__", "exec")))
        self.assertEqual(
            format_script_status(RuntimeResponse.yielded(cell_id="42")),
            "Script running with cell ID 42",
        )
        self.assertEqual(
            format_script_status(RuntimeResponse.terminated(cell_id="42")),
            "Script terminated",
        )
        self.assertEqual(
            format_script_status(RuntimeResponse.result(cell_id="42")),
            "Script completed",
        )
        self.assertEqual(
            format_script_status(RuntimeResponse.result(cell_id="42", error_text="boom")),
            "Script failed",
        )
        self.assertEqual(
            script_status_header("Script completed", 0.56),
            "Script completed\nWall time 0.6 seconds\nOutput:\n",
        )

    def test_nested_tool_payload_uses_function_and_freeform_kinds(self) -> None:
        self.assertEqual(
            build_nested_tool_payload(
                CodeModeToolKind.FUNCTION,
                ToolName.plain("example"),
                {"value": 1},
            ),
            ToolPayload.function('{"value":1}'),
        )
        self.assertEqual(
            build_nested_tool_payload(
                CodeModeToolKind.FREEFORM,
                ToolName.plain("apply_patch"),
                "raw patch",
            ),
            ToolPayload.custom("raw patch"),
        )
        self.assertEqual(
            build_nested_tool_payload(
                CodeModeToolKind.FUNCTION,
                ToolName.plain("example"),
                None,
            ),
            ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(ValueError, "expects a JSON object"):
            build_nested_tool_payload(CodeModeToolKind.FUNCTION, ToolName.plain("example"), [])
        with self.assertRaisesRegex(ValueError, "expects a string input"):
            build_nested_tool_payload(CodeModeToolKind.FREEFORM, ToolName.plain("example"), {})

    def test_code_mode_nested_tool_call_coerces_names_and_kinds(self) -> None:
        call = CodeModeNestedToolCall(
            cell_id="cell-1",
            runtime_tool_call_id="runtime-1",
            tool_name={"namespace": "mcp__", "name": "search"},
            tool_kind="function",
            input={"q": "codex"},
        )

        self.assertEqual(call.tool_name, ToolName.namespaced("mcp__", "search"))
        self.assertEqual(call.tool_kind, CodeModeToolKind.FUNCTION)
        self.assertEqual(call.input, {"q": "codex"})

        plain_call = CodeModeNestedToolCall(
            cell_id="cell-2",
            runtime_tool_call_id="runtime-2",
            tool_name="lookup",
            tool_kind="function",
            input={},
        )
        self.assertEqual(plain_call.tool_name, ToolName.plain("lookup"))

        with self.assertRaises(TypeError):
            CodeModeNestedToolCall(
                cell_id="cell-3",
                runtime_tool_call_id="runtime-3",
                tool_name=123,
                tool_kind="function",
                input={},
            )
        with self.assertRaises(TypeError):
            CodeModeNestedToolCall(
                cell_id="cell-4",
                runtime_tool_call_id="runtime-4",
                tool_name={"namespace": "mcp__", "name": 123},
                tool_kind="function",
                input={},
            )

    def test_runtime_command_and_event_shapes_match_upstream_variants(self) -> None:
        self.assertEqual(PendingRuntimeMode.CONTINUE.value, "continue")
        self.assertEqual(PendingRuntimeMode.PAUSE_UNTIL_RESUMED.value, "pause_until_resumed")
        self.assertEqual(RuntimeControlCommand.RESUME.value, "resume")
        self.assertEqual(RuntimeControlCommand.TERMINATE.value, "terminate")

        response_command = RuntimeCommand.tool_response("tool-1", {"ok": True})
        self.assertEqual(
            response_command.to_mapping(),
            {"type": "tool_response", "id": "tool-1", "result": {"ok": True}},
        )
        self.assertEqual(
            RuntimeCommand.from_mapping(
                {"ToolError": {"id": "tool-1", "error_text": "boom"}}
            ),
            RuntimeCommand.tool_error("tool-1", "boom"),
        )
        self.assertEqual(
            RuntimeCommand.from_mapping({"TimeoutFired": {"id": 3}}),
            RuntimeCommand.timeout_fired(3),
        )
        self.assertEqual(RuntimeCommand.from_mapping({"Terminate": {}}), RuntimeCommand.terminate())

        tool_call = CodeModeNestedToolCall(
            cell_id="cell-1",
            runtime_tool_call_id="tool-1",
            tool_name=ToolName.plain("lookup"),
            tool_kind=CodeModeToolKind.FUNCTION,
            input={"id": 1},
        )
        self.assertEqual(RuntimeEvent.started().to_mapping(), {"type": "started"})
        self.assertEqual(RuntimeEvent.pending().to_mapping(), {"type": "pending"})
        self.assertEqual(
            RuntimeEvent.content_item(FunctionCallOutputContentItem.input_text("hello")).to_mapping(),
            {"type": "content_item", "content_item": {"type": "input_text", "text": "hello"}},
        )
        self.assertEqual(RuntimeEvent.tool_call(tool_call).nested_tool_call, tool_call)
        self.assertEqual(
            RuntimeEvent.notify(call_id="call-1", text="heads up").to_mapping(),
            {"type": "notify", "call_id": "call-1", "text": "heads up"},
        )
        self.assertEqual(
            RuntimeEvent.result(
                stored_value_writes={"state": {"ok": True}},
                error_text="boom",
            ).to_mapping(),
            {
                "type": "result",
                "stored_value_writes": {"state": {"ok": True}},
                "error_text": "boom",
            },
        )
        self.assertEqual(
            RuntimeEvent.from_mapping(
                {
                    "ToolCall": {
                        "cell_id": "cell-1",
                        "id": "tool-1",
                        "name": {"namespace": None, "name": "lookup"},
                        "kind": "function",
                        "input": {"id": 1},
                    }
                }
            ),
            RuntimeEvent.tool_call(tool_call),
        )

    def test_module_loader_completion_helpers_match_upstream_boundaries(self) -> None:
        self.assertEqual(EXEC_MAIN_MODULE_NAME, "exec_main.mjs")
        self.assertEqual(UNSUPPORTED_DYNAMIC_IMPORT_ERROR, "unsupported import in exec")
        self.assertEqual(
            unsupported_static_import_error("node:fs"),
            "Unsupported import in exec: node:fs",
        )
        self.assertEqual(unsupported_dynamic_import_error(), "unsupported import in exec")

        self.assertEqual(CompletionState.pending().to_mapping(), {"type": "pending"})
        completed = CompletionState.completed(
            stored_value_writes={"state": {"ok": True}},
            error_text="boom",
        )
        self.assertEqual(
            completed.to_mapping(),
            {
                "type": "completed",
                "stored_value_writes": {"state": {"ok": True}},
                "error_text": "boom",
            },
        )
        self.assertEqual(
            CompletionState.from_mapping(
                {"Completed": {"stored_value_writes": {"state": 1}, "error_text": None}}
            ),
            CompletionState.completed(stored_value_writes={"state": 1}),
        )

        self.assertEqual(value_to_error_text({"stack": "Error: boom\n at exec"}), "Error: boom\n at exec")
        self.assertEqual(value_to_error_text({"message": "boom"}), '{"message":"boom"}')
        self.assertTrue(is_exit_exception(True, EXIT_SENTINEL))
        self.assertFalse(is_exit_exception(False, EXIT_SENTINEL))
        self.assertEqual(
            completion_state_from_rejection(
                EXIT_SENTINEL,
                exit_requested=True,
                stored_value_writes={"state": "done"},
            ),
            CompletionState.completed(stored_value_writes={"state": "done"}),
        )
        self.assertEqual(
            completion_state_from_rejection(
                {"stack": "Error: rejected"},
                exit_requested=True,
                stored_value_writes={"state": "done"},
            ),
            CompletionState.completed(
                stored_value_writes={"state": "done"},
                error_text="Error: rejected",
            ),
        )

    def test_next_runtime_command_matches_pending_mode_control_flow(self) -> None:
        command = RuntimeCommand.tool_response("tool-1", {"ok": True})
        self.assertEqual(
            next_runtime_command([command]),
            NextRuntimeCommandResult(command),
        )
        self.assertEqual(
            next_runtime_command([None, command]),
            NextRuntimeCommandResult(command, (RuntimeEvent.pending(),)),
        )
        self.assertEqual(
            next_runtime_command(
                [None, command],
                [RuntimeControlCommand.RESUME],
                pending_mode=PendingRuntimeMode.PAUSE_UNTIL_RESUMED,
            ),
            NextRuntimeCommandResult(
                command,
                (RuntimeEvent.pending(),),
                (RuntimeControlCommand.RESUME,),
            ),
        )
        self.assertEqual(
            next_runtime_command(
                [None],
                ["terminate"],
                pending_mode="pause_until_resumed",
            ),
            NextRuntimeCommandResult(
                RuntimeCommand.terminate(),
                (RuntimeEvent.pending(),),
                (RuntimeControlCommand.TERMINATE,),
            ),
        )
        self.assertEqual(next_runtime_command([]), NextRuntimeCommandResult(None))
        self.assertEqual(
            next_runtime_command(
                [None],
                [],
                pending_mode=PendingRuntimeMode.PAUSE_UNTIL_RESUMED,
            ),
            NextRuntimeCommandResult(None, (RuntimeEvent.pending(),)),
        )

    def test_runtime_tool_callback_helpers_build_nested_tool_events(self) -> None:
        definitions = [
            CodeModeToolDefinition(
                name="lookup_order",
                tool_name=ToolName.plain("lookup_order"),
                description="Look up order",
                kind=CodeModeToolKind.FUNCTION,
            ),
            CodeModeToolDefinition(
                name="apply_patch",
                tool_name=ToolName.plain("apply_patch"),
                description="Patch",
                kind=CodeModeToolKind.FREEFORM,
            ),
        ]

        self.assertEqual(RUNTIME_TOOL_CALL_ID_PREFIX, "tool-")
        self.assertEqual(runtime_tool_index_from_callback_data("01"), 1)
        with self.assertRaisesRegex(ValueError, "invalid tool callback data"):
            runtime_tool_index_from_callback_data(" 1")
        self.assertEqual(runtime_tool_call_id(7), "tool-7")
        self.assertEqual(next_runtime_tool_call_sequence(7), 8)
        self.assertEqual(next_runtime_tool_call_sequence(U64_MAX), U64_MAX)
        self.assertEqual(normalize_runtime_tool_input({"ok": True}), {"ok": True})
        with self.assertRaisesRegex(ValueError, "failed to serialize JavaScript value"):
            normalize_runtime_tool_input({"bad": object()})

        event, next_sequence = build_runtime_tool_call_event(
            cell_id="cell-1",
            tool_index="0",
            enabled_tools=definitions,
            input={"order_id": "A123"},
            next_tool_call_id=2,
        )
        self.assertEqual(next_sequence, 3)
        self.assertEqual(
            event,
            RuntimeEvent.tool_call(
                CodeModeNestedToolCall(
                    cell_id="cell-1",
                    runtime_tool_call_id="tool-2",
                    tool_name=ToolName.plain("lookup_order"),
                    tool_kind=CodeModeToolKind.FUNCTION,
                    input={"order_id": "A123"},
                )
            ),
        )
        with self.assertRaisesRegex(ValueError, "tool callback data is out of range"):
            build_runtime_tool_call_event(
                cell_id="cell-1",
                tool_index=2,
                enabled_tools=definitions,
            )

        state = CodeModeRuntimeToolState(
            cell_id="cell-9",
            enabled_tools=tuple(enabled_tool_metadata(definition) for definition in definitions),
        )
        emitted = state.emit_tool_call(1, "raw patch")
        self.assertEqual(state.next_tool_call_id, 2)
        self.assertEqual(state.pending_tool_call_ids, ["tool-1"])
        self.assertEqual(emitted.nested_tool_call.tool_kind, CodeModeToolKind.FREEFORM)
        self.assertEqual(emitted.nested_tool_call.input, "raw patch")

    def test_text_and_image_callback_helpers_emit_content_events(self) -> None:
        self.assertEqual(
            build_runtime_text_event({"ok": True}),
            RuntimeEvent.content_item(FunctionCallOutputContentItem.input_text('{"ok":true}')),
        )
        self.assertEqual(
            build_runtime_text_event(),
            RuntimeEvent.content_item(FunctionCallOutputContentItem.input_text("null")),
        )

        self.assertEqual(
            build_runtime_image_event(
                {"image_url": "https://example.com/a.png", "detail": "original"},
                detail_override="high",
            ),
            RuntimeEvent.content_item(
                FunctionCallOutputContentItem.input_image(
                    "https://example.com/a.png",
                    ImageDetail.HIGH,
                )
            ),
        )
        self.assertEqual(
            build_runtime_image_event(
                {"type": "image", "data": "QUJD", "mimeType": "image/png"}
            ),
            RuntimeEvent.content_item(
                FunctionCallOutputContentItem.input_image(
                    "data:image/png;base64,QUJD",
                    DEFAULT_IMAGE_DETAIL,
                )
            ),
        )
        with self.assertRaisesRegex(ValueError, "only accepts MCP image blocks"):
            build_runtime_image_event({"type": "text", "data": "abc"})

    def test_create_code_mode_tool_matches_upstream_freeform_spec(self) -> None:
        enabled_tool = CodeModeToolDefinition(
            name="update_plan",
            tool_name=ToolName.plain("update_plan"),
            description="Update the plan",
            kind=CodeModeToolKind.FUNCTION,
        )

        spec = create_code_mode_tool(
            [enabled_tool],
            {},
            code_mode_only=True,
            deferred_tools_available=False,
        )

        self.assertEqual(
            spec.to_mapping(),
            {
                "type": "custom",
                "name": "exec",
                "description": build_exec_tool_description(
                    (enabled_tool,),
                    {},
                    code_mode_only=True,
                    deferred_tools_available=False,
                ),
                "format": {
                    "type": "grammar",
                    "syntax": "lark",
                    "definition": CODE_MODE_FREEFORM_GRAMMAR,
                },
            },
        )

    def test_create_wait_tool_matches_upstream_schema(self) -> None:
        spec = create_wait_tool()

        self.assertEqual(
            spec,
            {
                "type": "function",
                "name": "wait",
                "description": (
                    "Waits on a yielded `exec` cell and returns new output or completion.\n"
                    f"{build_wait_tool_description().strip()}"
                ),
                "strict": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cell_id": {
                            "type": "string",
                            "description": "Identifier of the running exec cell.",
                        },
                        "yield_time_ms": {
                            "type": "number",
                            "description": (
                                "How long to wait (in milliseconds) for more output before yielding again."
                            ),
                        },
                        "max_tokens": {
                            "type": "number",
                            "description": (
                                "Maximum number of output tokens to return for this wait call."
                            ),
                        },
                        "terminate": {
                            "type": "boolean",
                            "description": "Whether to terminate the running exec cell.",
                        },
                    },
                    "required": ["cell_id"],
                    "additionalProperties": False,
                },
            },
        )

    def test_parse_wait_arguments_applies_defaults_and_validates_numbers(self) -> None:
        # Rust source: codex-rs/core/src/tools/code_mode/wait_handler.rs
        # Contract: ExecWaitArgs is serde-deserialized, so string/bool fields are
        # not implicitly coerced from arbitrary JSON values.
        self.assertEqual(
            parse_wait_arguments('{"cell_id":"cell-1"}'),
            ExecWaitArgs(cell_id="cell-1"),
        )
        self.assertEqual(
            parse_wait_arguments(
                '{"cell_id":"cell-1","yield_time_ms":5,"max_tokens":20,"terminate":true}'
            ),
            ExecWaitArgs(cell_id="cell-1", yield_time_ms=5, max_tokens=20, terminate=True),
        )

        with self.assertRaisesRegex(ValueError, "missing field"):
            parse_wait_arguments("{}")
        with self.assertRaisesRegex(ValueError, "must be an integer"):
            parse_wait_arguments('{"cell_id":"cell-1","yield_time_ms":1.5}')
        with self.assertRaisesRegex(ValueError, "field `cell_id` must be a string"):
            parse_wait_arguments('{"cell_id":1}')
        with self.assertRaisesRegex(ValueError, "field `terminate` must be a boolean"):
            parse_wait_arguments('{"cell_id":"cell-1","terminate":1}')

    def test_code_mode_response_adapter_defaults_image_detail(self) -> None:
        items = into_function_call_output_content_items(
            (
                {"type": "input_text", "text": "hello"},
                {"type": "input_image", "image_url": "data:image/png;base64,AAA"},
            )
        )

        self.assertEqual(items[0], FunctionCallOutputContentItem.input_text("hello"))
        self.assertEqual(
            items[1],
            FunctionCallOutputContentItem.input_image(
                "data:image/png;base64,AAA",
                DEFAULT_IMAGE_DETAIL,
            ),
        )

    def test_code_mode_response_adapter_maps_external_code_mode_items(self) -> None:
        # Rust source: codex-rs/core/src/tools/code_mode/response_adapter.rs
        # Contract: codex_code_mode content items are converted to protocol content items.
        items = into_function_call_output_content_items(
            (
                external_code_mode.FunctionCallOutputContentItem(
                    type="input_text",
                    text="hello",
                ),
                external_code_mode.FunctionCallOutputContentItem(
                    type="input_image",
                    image_url="data:image/png;base64,AUTO",
                    detail=external_code_mode.ImageDetail.AUTO,
                ),
                external_code_mode.FunctionCallOutputContentItem(
                    type="input_image",
                    image_url="data:image/png;base64,LOW",
                    detail=external_code_mode.ImageDetail.LOW,
                ),
                external_code_mode.FunctionCallOutputContentItem(
                    type="input_image",
                    image_url="data:image/png;base64,HIGH",
                    detail=external_code_mode.ImageDetail.HIGH,
                ),
                external_code_mode.FunctionCallOutputContentItem(
                    type="input_image",
                    image_url="data:image/png;base64,ORIGINAL",
                    detail=external_code_mode.ImageDetail.ORIGINAL,
                ),
                external_code_mode.FunctionCallOutputContentItem(
                    type="input_image",
                    image_url="data:image/png;base64,DEFAULT",
                    detail=None,
                ),
            )
        )

        self.assertEqual(items[0], FunctionCallOutputContentItem.input_text("hello"))
        self.assertEqual(items[1].detail, ImageDetail.AUTO)
        self.assertEqual(items[2].detail, ImageDetail.LOW)
        self.assertEqual(items[3].detail, ImageDetail.HIGH)
        self.assertEqual(items[4].detail, ImageDetail.ORIGINAL)
        self.assertEqual(items[5].detail, DEFAULT_IMAGE_DETAIL)

    def test_handle_runtime_response_formats_successful_yield(self) -> None:
        output = handle_runtime_response(
            RuntimeResponse.yielded(
                cell_id="cell-42",
                content_items=(FunctionCallOutputContentItem.input_text("partial"),),
            ),
            max_output_tokens=None,
            wall_time_seconds=1.24,
        )

        self.assertTrue(output.success)
        self.assertEqual(
            output.body[0],
            FunctionCallOutputContentItem.input_text(
                "Script running with cell ID cell-42\nWall time 1.2 seconds\nOutput:\n"
            ),
        )
        self.assertEqual(output.body[1], FunctionCallOutputContentItem.input_text("partial"))

    def test_handle_runtime_response_appends_error_and_reports_failure(self) -> None:
        output = handle_runtime_response(
            RuntimeResponse.result(
                cell_id="cell-1",
                content_items=(FunctionCallOutputContentItem.input_text("before"),),
                error_text="boom",
            ),
            max_output_tokens=None,
            wall_time_seconds=0.04,
        )

        self.assertFalse(output.success)
        self.assertEqual(
            output.body[0],
            FunctionCallOutputContentItem.input_text(
                "Script failed\nWall time 0.0 seconds\nOutput:\n"
            ),
        )
        self.assertEqual(output.body[-1], FunctionCallOutputContentItem.input_text("Script error:\nboom"))

    def test_handle_runtime_response_sanitizes_images_and_truncates_mixed_content(self) -> None:
        output = handle_runtime_response(
            RuntimeResponse.result(
                cell_id="cell-1",
                content_items=(
                    FunctionCallOutputContentItem.input_text("this text is omitted"),
                    FunctionCallOutputContentItem.input_image(
                        "data:image/png;base64,AAA",
                        ImageDetail.ORIGINAL,
                    ),
                ),
            ),
            max_output_tokens=0,
            wall_time_seconds=0.0,
            can_request_original_detail=False,
        )

        self.assertTrue(output.success)
        self.assertEqual(
            output.body[1],
            FunctionCallOutputContentItem.input_image(
                "data:image/png;base64,AAA",
                DEFAULT_IMAGE_DETAIL,
            ),
        )
        self.assertEqual(
            output.body[2],
            FunctionCallOutputContentItem.input_text("[omitted 1 text items ...]"),
        )

    def test_truncate_code_mode_result_uses_formatted_text_path_for_text_only(self) -> None:
        items = truncate_code_mode_result(
            (FunctionCallOutputContentItem.input_text("line 1\nline 2"),),
            0,
        )

        self.assertEqual(len(items), 1)
        self.assertTrue((items[0].text or "").startswith("Total output lines: 2"))

    def test_execute_handler_builds_request_and_adapts_response(self) -> None:
        captured: list[ExecuteRequest] = []

        def execute_callback(request: ExecuteRequest) -> RuntimeResponse:
            captured.append(request)
            return RuntimeResponse.yielded(
                cell_id=request.cell_id,
                content_items=(FunctionCallOutputContentItem.input_text("running"),),
            )

        handler = CodeModeExecuteHandler(
            nested_tool_specs=(function_spec("lookup_order"),),
            execute_callback=execute_callback,
            cell_id_allocator=lambda: "cell-1",
        )
        invocation = SimpleNamespace(
            call_id="call-1",
            tool_name=ToolName.plain("exec"),
            payload=ToolPayload.custom('// @exec: {"yield_time_ms": 5, "max_output_tokens": 7}\ntext("hi")'),
        )

        output = handler.handle(invocation)

        self.assertTrue(handler.matches_kind(invocation.payload))
        self.assertFalse(handler.matches_kind(ToolPayload.function("{}")))
        self.assertEqual(handler.tool_name(), ToolName.plain("exec"))
        self.assertEqual(handler.spec().name, "exec")
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].cell_id, "cell-1")
        self.assertEqual(captured[0].tool_call_id, "call-1")
        self.assertEqual(captured[0].source, 'text("hi")')
        self.assertEqual(captured[0].yield_time_ms, 5)
        self.assertEqual(captured[0].max_output_tokens, 7)
        self.assertEqual([definition.name for definition in captured[0].enabled_tools], ["lookup_order"])
        self.assertTrue(output.success)
        self.assertIn("Script running with cell ID cell-1", output.body[0].text or "")
        self.assertEqual(output.body[1], FunctionCallOutputContentItem.input_text("running"))

    def test_execute_handler_rejects_non_exec_custom_payloads(self) -> None:
        handler = CodeModeExecuteHandler(
            execute_callback=lambda request: RuntimeResponse.result(cell_id=request.cell_id),
        )

        with self.assertRaisesRegex(ValueError, "expects raw JavaScript source text"):
            handler.handle(ToolPayload.function("{}"))
        with self.assertRaisesRegex(ValueError, "expects raw JavaScript source text"):
            handler.handle(
                SimpleNamespace(
                    tool_name=ToolName.namespaced("mcp__", "exec"),
                    payload=ToolPayload.custom("text('hi')"),
                )
            )

    def test_wait_handler_builds_request_and_adapts_response(self) -> None:
        captured: list[WaitRequest] = []

        def wait_callback(request: WaitRequest) -> WaitOutcome:
            captured.append(request)
            return WaitOutcome.live_cell(
                RuntimeResponse.result(
                    cell_id=request.cell_id,
                    content_items=(FunctionCallOutputContentItem.input_text("done"),),
                )
            )

        handler = CodeModeWaitHandler(wait_callback=wait_callback)
        invocation = SimpleNamespace(
            tool_name=ToolName.plain("wait"),
            payload=ToolPayload.function(
                '{"cell_id":"cell-1","yield_time_ms":11,"max_tokens":12,"terminate":true}'
            ),
        )

        output = handler.handle(invocation)

        self.assertTrue(handler.matches_kind(invocation.payload))
        self.assertFalse(handler.matches_kind(ToolPayload.custom("raw")))
        self.assertEqual(handler.tool_name(), ToolName.plain("wait"))
        self.assertEqual(handler.spec()["name"], "wait")
        self.assertEqual(captured, [WaitRequest(cell_id="cell-1", yield_time_ms=11, terminate=True)])
        self.assertTrue(output.success)
        self.assertIn("Script completed", output.body[0].text or "")
        self.assertEqual(output.body[1], FunctionCallOutputContentItem.input_text("done"))
        self.assertIsNone(handler.pre_tool_use_payload(invocation))
        self.assertIsNone(handler.post_tool_use_payload(invocation, output))

    def test_wait_handler_rejects_non_wait_function_payloads(self) -> None:
        handler = CodeModeWaitHandler(
            wait_callback=lambda request: RuntimeResponse.result(cell_id=request.cell_id),
        )

        with self.assertRaisesRegex(ValueError, "expects JSON arguments"):
            handler.handle(ToolPayload.custom("raw"))
        with self.assertRaisesRegex(ValueError, "expects JSON arguments"):
            handler.handle(
                SimpleNamespace(
                    tool_name=ToolName.namespaced("mcp__", "wait"),
                    payload=ToolPayload.function('{"cell_id":"cell-1"}'),
                )
            )

    def test_service_allocates_cell_ids_and_returns_missing_waits(self) -> None:
        service = CodeModeService()

        self.assertEqual(service.allocate_cell_id(), "1")
        self.assertEqual(service.allocate_cell_id(), "2")
        self.assertEqual(
            service.wait(WaitRequest(cell_id="missing")),
            WaitOutcome.missing_cell(missing_cell_response("missing")),
        )
        self.assertEqual(
            service.wait_to_pending({"cell_id": "missing"}),
            WaitToPendingOutcome.missing_cell(missing_cell_response("missing")),
        )

    def test_service_delegates_execute_and_pending_callbacks(self) -> None:
        request = ExecuteRequest(
            cell_id="cell-1",
            tool_call_id="call-1",
            enabled_tools=(),
            source="text('hi')",
        )
        service = CodeModeService(
            execute_callback=lambda received: RuntimeResponse.result(
                cell_id=received.cell_id,
                content_items=(FunctionCallOutputContentItem.input_text(received.source),),
            ),
            execute_to_pending_callback=lambda received: ExecuteToPendingOutcome.pending(
                cell_id=received.cell_id,
                pending_tool_call_ids=("tool-1",),
            ),
            wait_callback=lambda received: RuntimeResponse.terminated(cell_id=received.cell_id),
            wait_to_pending_callback=lambda received: ExecuteToPendingOutcome.completed(
                RuntimeResponse.result(cell_id=received.cell_id)
            ),
        )

        self.assertEqual(
            service.execute(request),
            RuntimeResponse.result(
                cell_id="cell-1",
                content_items=(FunctionCallOutputContentItem.input_text("text('hi')"),),
            ),
        )
        self.assertEqual(
            service.execute_to_pending(request),
            ExecuteToPendingOutcome.pending(
                cell_id="cell-1",
                pending_tool_call_ids=("tool-1",),
            ),
        )
        self.assertEqual(
            service.wait({"cell_id": "cell-1", "yield_time_ms": 5}),
            WaitOutcome.live_cell(RuntimeResponse.terminated(cell_id="cell-1")),
        )
        self.assertEqual(
            service.wait_to_pending({"cell_id": "cell-1"}),
            WaitToPendingOutcome.live_cell(
                ExecuteToPendingOutcome.completed(RuntimeResponse.result(cell_id="cell-1"))
            ),
        )

    def test_pending_and_missing_response_helpers_match_upstream_text(self) -> None:
        self.assertEqual(
            missing_cell_response("abc"),
            RuntimeResponse.result(cell_id="abc", error_text="exec cell abc not found"),
        )
        self.assertEqual(
            pending_result_response(
                "abc",
                PendingResult(
                    content_items=(FunctionCallOutputContentItem.input_text("done"),),
                    error_text="boom",
                ),
            ),
            RuntimeResponse.result(
                cell_id="abc",
                content_items=(FunctionCallOutputContentItem.input_text("done"),),
                error_text="boom",
            ),
        )

    def test_serialize_output_text_matches_js_helper_for_json_values(self) -> None:
        self.assertEqual(serialize_output_text(None), "null")
        self.assertEqual(serialize_output_text(True), "true")
        self.assertEqual(serialize_output_text(False), "false")
        self.assertEqual(serialize_output_text(12), "12")
        self.assertEqual(serialize_output_text("hello"), "hello")
        self.assertEqual(serialize_output_text({"b": [1, 2]}), '{"b":[1,2]}')

    def test_normalize_output_image_accepts_strings_and_non_mcp_objects(self) -> None:
        self.assertEqual(
            normalize_output_image("https://example.com/a.png"),
            FunctionCallOutputContentItem.input_image(
                "https://example.com/a.png",
                DEFAULT_IMAGE_DETAIL,
            ),
        )
        self.assertEqual(
            normalize_output_image({"image_url": "data:image/png;base64,AAA", "detail": "original"}),
            FunctionCallOutputContentItem.input_image(
                "data:image/png;base64,AAA",
                ImageDetail.ORIGINAL,
            ),
        )
        self.assertEqual(
            normalize_output_image(
                {"image_url": "data:image/png;base64,AAA", "detail": "original"},
                detail_override="high",
            ),
            FunctionCallOutputContentItem.input_image(
                "data:image/png;base64,AAA",
                ImageDetail.HIGH,
            ),
        )

    def test_normalize_output_image_accepts_mcp_image_blocks(self) -> None:
        self.assertEqual(
            normalize_output_image(
                {
                    "type": "image",
                    "data": "QUJD",
                    "mimeType": "image/png",
                    "_meta": {"codex/imageDetail": "original"},
                }
            ),
            FunctionCallOutputContentItem.input_image(
                "data:image/png;base64,QUJD",
                ImageDetail.ORIGINAL,
            ),
        )
        self.assertEqual(
            normalize_output_image({"type": "image", "data": "data:image/jpeg;base64,AAA"}),
            FunctionCallOutputContentItem.input_image(
                "data:image/jpeg;base64,AAA",
                DEFAULT_IMAGE_DETAIL,
            ),
        )

    def test_normalize_output_image_rejects_invalid_shapes(self) -> None:
        with self.assertRaisesRegex(ValueError, "image expects"):
            normalize_output_image("")
        with self.assertRaisesRegex(ValueError, "http\\(s\\) or data URL"):
            normalize_output_image("file:///tmp/a.png")
        with self.assertRaisesRegex(ValueError, "image detail must be a string"):
            normalize_output_image({"image_url": "https://example.com/a.png", "detail": 1})
        with self.assertRaisesRegex(ValueError, "one of: high, original"):
            normalize_output_image({"image_url": "https://example.com/a.png", "detail": "low"})
        with self.assertRaisesRegex(ValueError, "got \"text\""):
            normalize_output_image({"type": "text", "data": "abc"})
        with self.assertRaisesRegex(ValueError, "expected MCP image data"):
            normalize_output_image({"type": "image", "data": ""})

    def test_timeout_helpers_match_upstream_timer_normalization(self) -> None:
        self.assertEqual(normalize_timeout_delay_ms(), 0)
        self.assertEqual(normalize_timeout_delay_ms(None), 0)
        self.assertEqual(normalize_timeout_delay_ms(False), 0)
        self.assertEqual(normalize_timeout_delay_ms(True), 1)
        self.assertEqual(normalize_timeout_delay_ms(-1), 0)
        self.assertEqual(normalize_timeout_delay_ms(12.9), 12)
        self.assertEqual(normalize_timeout_delay_ms(" 25.5 "), 25)
        self.assertEqual(normalize_timeout_delay_ms("not numeric"), 0)
        self.assertEqual(normalize_timeout_delay_ms(float("inf")), 0)
        self.assertEqual(normalize_timeout_delay_ms(1 << 80), U64_MAX)

        self.assertIsNone(clear_timeout_id_from_value())
        self.assertIsNone(clear_timeout_id_from_value(None))
        self.assertIsNone(clear_timeout_id_from_value(0))
        self.assertIsNone(clear_timeout_id_from_value(-1))
        self.assertIsNone(clear_timeout_id_from_value(float("nan")))
        self.assertIsNone(clear_timeout_id_from_value("not numeric"))
        self.assertEqual(clear_timeout_id_from_value(7.8), 7)
        self.assertEqual(clear_timeout_id_from_value(" 8.2 "), 8)
        self.assertEqual(clear_timeout_id_from_value(1 << 80), U64_MAX)
        with self.assertRaisesRegex(ValueError, "clearTimeout expects a numeric timeout id"):
            clear_timeout_id_from_value({})

    def test_runtime_store_helpers_match_store_load_callbacks(self) -> None:
        self.assertEqual(normalize_store_key(None), "null")
        self.assertEqual(normalize_store_key(True), "true")
        self.assertEqual(normalize_store_key(12.0), "12")
        self.assertEqual(normalize_store_key(float("inf")), "Infinity")
        self.assertEqual(normalize_store_key(float("-inf")), "-Infinity")
        self.assertEqual(normalize_store_key(float("nan")), "NaN")

        stored = serialize_stored_value("state", {"items": [1, {"ok": True}]})
        self.assertEqual(stored, {"items": [1, {"ok": True}]})
        with self.assertRaisesRegex(
            ValueError,
            'Unable to store "state". Only plain serializable objects can be stored.',
        ):
            serialize_stored_value("state", {"bad": object()})
        with self.assertRaisesRegex(
            ValueError,
            'Unable to store "state". Only plain serializable objects can be stored.',
        ):
            serialize_stored_value("state", float("nan"))

        runtime_store = CodeModeRuntimeStore({"state": {"count": 1}})
        loaded = runtime_store.load("state")
        self.assertEqual(loaded, {"count": 1})
        assert isinstance(loaded, dict)
        loaded["count"] = 2
        self.assertEqual(runtime_store.load("state"), {"count": 1})
        self.assertIsNone(runtime_store.load("missing"))

        runtime_store.store("state", {"count": 3})
        runtime_store.store(True, ["yes"])
        self.assertEqual(runtime_store.load("state"), {"count": 3})
        self.assertEqual(runtime_store.load("true"), ["yes"])
        self.assertEqual(
            runtime_store.writes(),
            {"state": {"count": 3}, "true": ["yes"]},
        )

    def test_notify_and_exit_helpers_match_runtime_callbacks(self) -> None:
        self.assertEqual(normalize_notify_text({"ok": True}), '{"ok":true}')
        self.assertEqual(normalize_notify_text(0), "0")
        self.assertEqual(
            build_runtime_notify_event("call-1", {"ok": True}),
            RuntimeEvent.notify(call_id="call-1", text='{"ok":true}'),
        )
        with self.assertRaisesRegex(ValueError, "notify expects non-empty text"):
            normalize_notify_text("   ")
        with self.assertRaisesRegex(ValueError, "notify expects non-empty text"):
            build_runtime_notify_event("call-1", "   ")

        self.assertEqual(build_runtime_yield_event(), RuntimeEvent.yield_requested())

        self.assertTrue(is_exit_sentinel(EXIT_SENTINEL))
        self.assertFalse(is_exit_sentinel("__codex_code_mode_exit__ "))
        self.assertFalse(is_exit_sentinel(None))
        self.assertEqual(runtime_exit_exception(), EXIT_SENTINEL)
        self.assertEqual(
            completion_state_from_exit({"state": "done"}),
            CompletionState.completed(stored_value_writes={"state": "done"}),
        )


if __name__ == "__main__":
    unittest.main()
