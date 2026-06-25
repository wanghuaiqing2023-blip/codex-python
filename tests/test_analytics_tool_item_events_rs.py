from pycodex.analytics import (
    AnalyticsReducer,
    CodexToolItemEventBase,
    CommandExecutionSource,
    FinalApprovalOutcome,
    SubAgentThreadStartedInput,
    ThreadInitializationMode,
    ThreadMetadataState,
    ToolItemKey,
    ToolItemFailureKind,
    ToolItemTerminalStatus,
    TurnState,
    WebSearchActionKind,
    codex_collab_agent_tool_call_event,
    codex_command_execution_event,
    codex_dynamic_tool_call_event,
    codex_file_change_event,
    codex_image_generation_event,
    codex_mcp_tool_call_event,
    codex_web_search_event,
)


def sample_app_server_client_metadata() -> dict:
    return {
        "product_client_id": "codex_tui",
        "client_name": "codex-tui",
        "client_version": "1.2.3",
        "rpc_transport": "websocket",
        "experimental_api_enabled": True,
    }


def sample_runtime_metadata() -> dict:
    return {
        "codex_rs_version": "0.99.0",
        "runtime_os": "macos",
        "runtime_os_version": "15.3.1",
        "runtime_arch": "aarch64",
    }


def sample_thread_metadata() -> ThreadMetadataState:
    return ThreadMetadataState(
        session_id="session-1",
        thread_source="user",
        initialization_mode=ThreadInitializationMode.NEW,
        subagent_source=None,
        parent_thread_id=None,
    )


def sample_tool_item_base() -> CodexToolItemEventBase:
    return CodexToolItemEventBase(
        thread_id="thread-1",
        turn_id="turn-1",
        item_id="item-1",
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_source="user",
        subagent_source=None,
        parent_thread_id=None,
        tool_name="shell",
        started_at_ms=123_000,
        completed_at_ms=125_000,
        duration_ms=2_000,
        execution_duration_ms=1_900,
        review_count=0,
        guardian_review_count=0,
        user_review_count=0,
        final_approval_outcome=FinalApprovalOutcome.NOT_NEEDED,
        terminal_status=ToolItemTerminalStatus.COMPLETED,
        failure_kind=None,
        requested_additional_permissions=False,
        requested_network_access=False,
    )


def expected_tool_item_base_payload(**updates) -> dict:
    payload = {
        "thread_id": "thread-1",
        "turn_id": "turn-1",
        "item_id": "item-1",
        "app_server_client": {
            "product_client_id": "codex_tui",
            "client_name": "codex-tui",
            "client_version": "1.2.3",
            "rpc_transport": "websocket",
            "experimental_api_enabled": True,
        },
        "runtime": {
            "codex_rs_version": "0.99.0",
            "runtime_os": "macos",
            "runtime_os_version": "15.3.1",
            "runtime_arch": "aarch64",
        },
        "thread_source": "user",
        "subagent_source": None,
        "parent_thread_id": None,
        "tool_name": "shell",
        "started_at_ms": 123_000,
        "completed_at_ms": 125_000,
        "duration_ms": 2_000,
        "execution_duration_ms": 1_900,
        "review_count": 0,
        "guardian_review_count": 0,
        "user_review_count": 0,
        "final_approval_outcome": "not_needed",
        "terminal_status": "completed",
        "failure_kind": None,
        "requested_additional_permissions": False,
        "requested_network_access": False,
    }
    payload.update(updates)
    return payload


def test_command_execution_event_serializes_expected_shape() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::command_execution_event_serializes_expected_shape
    # Contract: CodexCommandExecutionEventRequest serializes flattened tool-item base fields plus command metrics.
    payload = codex_command_execution_event(
        base=sample_tool_item_base(),
        command_execution_source=CommandExecutionSource.AGENT,
        exit_code=0,
        command_total_action_count=4,
        command_read_action_count=1,
        command_list_files_action_count=1,
        command_search_action_count=1,
        command_unknown_action_count=1,
    )

    assert payload == {
        "event_type": "codex_command_execution_event",
        "event_params": expected_tool_item_base_payload(
            command_execution_source="agent",
            exit_code=0,
            command_total_action_count=4,
            command_read_action_count=1,
            command_list_files_action_count=1,
            command_search_action_count=1,
            command_unknown_action_count=1,
        ),
    }


def test_item_lifecycle_notifications_publish_command_execution_event() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::item_lifecycle_notifications_publish_command_execution_event
    # Contract: ItemStarted records started_at; ItemCompleted updates turn tool counts and emits command execution telemetry.
    reducer = AnalyticsReducer()
    reducer.turns["turn-1"] = TurnState(connection_id=1, thread_id="thread-1", num_input_images=0)
    item_started = {
        "kind": "CommandExecution",
        "id": "item-1",
        "source": "agent",
        "status": "InProgress",
        "command_actions": [],
        "exit_code": None,
        "duration_ms": None,
    }

    assert (
        reducer.ingest_item_started(
            thread_id="thread-1",
            turn_id="turn-1",
            started_at_ms=1_000,
            item=item_started,
        )
        == []
    )

    item_completed = {
        "kind": "CommandExecution",
        "id": "item-1",
        "source": "agent",
        "status": "Completed",
        "command_actions": [
            {"kind": "Read"},
            {"kind": "ListFiles"},
            {"kind": "Search"},
            {"kind": "Unknown"},
        ],
        "exit_code": 0,
        "duration_ms": 42,
    }
    events = reducer.ingest_item_completed(
        thread_id="thread-1",
        turn_id="turn-1",
        completed_at_ms=1_045,
        item=item_completed,
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    assert len(events) == 1
    assert events[0] == {
        "event_type": "codex_command_execution_event",
        "event_params": expected_tool_item_base_payload(
            started_at_ms=1_000,
            completed_at_ms=1_045,
            duration_ms=45,
            execution_duration_ms=42,
            final_approval_outcome="unknown",
            command_execution_source="agent",
            exit_code=0,
            command_total_action_count=4,
            command_read_action_count=1,
            command_list_files_action_count=1,
            command_search_action_count=1,
            command_unknown_action_count=1,
        ),
    }
    counts = reducer.turns["turn-1"].tool_counts
    assert counts is not None
    assert counts.total == 1
    assert counts.shell_command == 1
    assert ToolItemKey("thread-1", "turn-1", "item-1") not in reducer.tool_items_started_at_ms


def test_item_completed_without_turn_state_does_not_create_turn_state() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::item_completed_without_turn_state_does_not_create_turn_state
    # Contract: ItemCompleted for a missing turn drops analytics and must not create reducer turn state.
    reducer = AnalyticsReducer()

    events = reducer.ingest_item_completed(
        thread_id="thread-2",
        turn_id="turn-2",
        completed_at_ms=1_000,
        item={
            "kind": "CommandExecution",
            "id": "item-1",
            "source": "agent",
            "status": "Completed",
            "command_actions": [],
            "exit_code": 0,
            "duration_ms": 1,
        },
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    assert events == []
    assert "turn-2" not in reducer.turns


def test_subagent_tool_items_inherit_parent_connection_metadata() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::subagent_tool_items_inherit_parent_connection_metadata
    # Contract: subagent ItemCompleted analytics resolves app client/runtime from the inherited parent connection.
    reducer = AnalyticsReducer()
    assert reducer.ingest_initialize(
        connection_id=7,
        product_client_id="codex-tui",
        client_name="codex-tui",
        client_version="1.0.0",
        rpc_transport="stdio",
        experimental_api_enabled=None,
        runtime=sample_runtime_metadata(),
    ) == []
    parent_events = reducer.ingest_thread_response(
        connection_id=7,
        thread_id="thread-1",
        session_id="session-parent",
        model="gpt-5",
        ephemeral=False,
        thread_source="user",
        initialization_mode=ThreadInitializationMode.NEW,
        created_at=120,
    )
    assert len(parent_events) == 1
    subagent_events = reducer.ingest_subagent_thread_started(
        SubAgentThreadStartedInput(
            session_id="session-root",
            thread_id="thread-subagent",
            parent_thread_id="thread-1",
            product_client_id="codex-tui",
            client_name="codex-tui",
            client_version="1.0.0",
            model="gpt-5",
            ephemeral=False,
            subagent_source="Review",
            created_at=128,
        ),
        runtime=sample_runtime_metadata(),
    )
    assert len(subagent_events) == 1
    assert reducer.ingest_turn_started(turn_id="turn-subagent", started_at=900) == []
    assert reducer.ingest_item_started(
        thread_id="thread-subagent",
        turn_id="turn-subagent",
        started_at_ms=1_000,
        item={
            "kind": "CommandExecution",
            "id": "item-1",
            "source": "agent",
            "status": "InProgress",
            "command_actions": [],
            "exit_code": None,
            "duration_ms": None,
        },
    ) == []

    events = reducer.ingest_item_completed(
        thread_id="thread-subagent",
        turn_id="turn-subagent",
        completed_at_ms=1_042,
        item={
            "kind": "CommandExecution",
            "id": "item-1",
            "source": "agent",
            "status": "Completed",
            "command_actions": [],
            "exit_code": 0,
            "duration_ms": 42,
        },
    )

    assert len(events) == 1
    params = events[0]["event_params"]
    assert events[0]["event_type"] == "codex_command_execution_event"
    assert params["thread_id"] == "thread-subagent"
    assert params["turn_id"] == "turn-subagent"
    assert params["thread_source"] == "subagent"
    assert params["subagent_source"] == "review"
    assert params["parent_thread_id"] == "thread-1"
    assert params["app_server_client"]["client_name"] == "codex-tui"
    assert params["app_server_client"]["rpc_transport"] == "stdio"
    assert params["runtime"] == sample_runtime_metadata()
    assert params["started_at_ms"] == 1_000
    assert params["completed_at_ms"] == 1_042
    assert params["execution_duration_ms"] == 42
    assert params["terminal_status"] == "completed"


def complete_lifecycle_item(item: dict, *, started_at_ms: int = 2_000, completed_at_ms: int = 2_120) -> dict:
    reducer = AnalyticsReducer()
    reducer.turns["turn-1"] = TurnState(connection_id=1, thread_id="thread-1", num_input_images=0)
    assert reducer.ingest_item_started(
        thread_id="thread-1",
        turn_id="turn-1",
        started_at_ms=started_at_ms,
        item={**item, "status": "InProgress"},
    ) == []
    events = reducer.ingest_item_completed(
        thread_id="thread-1",
        turn_id="turn-1",
        completed_at_ms=completed_at_ms,
        item=item,
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )
    assert len(events) == 1
    return events[0]


def test_file_change_lifecycle_publishes_file_change_event() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust item: tool_item_event ThreadItem::FileChange branch
    # Contract: completed file-change lifecycle emits apply_patch telemetry with file operation counts.
    event = complete_lifecycle_item(
        {
            "kind": "FileChange",
            "id": "file-1",
            "status": "Completed",
            "changes": [
                {"kind": "Add"},
                {"kind": "Update"},
                {"kind": "Delete"},
                {"kind": "Update", "move_path": "renamed.py"},
            ],
        }
    )

    assert event == {
        "event_type": "codex_file_change_event",
        "event_params": expected_tool_item_base_payload(
            item_id="file-1",
            tool_name="apply_patch",
            started_at_ms=2_000,
            completed_at_ms=2_120,
            duration_ms=120,
            execution_duration_ms=None,
            final_approval_outcome="unknown",
            file_change_count=4,
            file_add_count=1,
            file_update_count=1,
            file_delete_count=1,
            file_move_count=1,
        ),
    }


def test_mcp_and_dynamic_lifecycle_publish_tool_events() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust item: tool_item_event ThreadItem::McpToolCall and ThreadItem::DynamicToolCall branches
    # Contract: completed MCP/dynamic tool lifecycle emits server/tool/error and content-count telemetry.
    mcp_event = complete_lifecycle_item(
        {
            "kind": "McpToolCall",
            "id": "mcp-1",
            "server": "server-1",
            "tool": "list_records",
            "status": "Failed",
            "error": {"message": "boom"},
            "duration_ms": 77,
        }
    )
    dynamic_event = complete_lifecycle_item(
        {
            "kind": "DynamicToolCall",
            "id": "dynamic-1",
            "tool": "render_chart",
            "status": "Completed",
            "success": True,
            "duration_ms": 88,
            "content_items": [{"kind": "InputText"}, {"kind": "InputImage"}],
        }
    )

    assert mcp_event == {
        "event_type": "codex_mcp_tool_call_event",
        "event_params": expected_tool_item_base_payload(
            item_id="mcp-1",
            tool_name="list_records",
            started_at_ms=2_000,
            completed_at_ms=2_120,
            duration_ms=120,
            execution_duration_ms=77,
            final_approval_outcome="unknown",
            terminal_status="failed",
            failure_kind="tool_error",
            mcp_server_name="server-1",
            mcp_tool_name="list_records",
            mcp_error_present=True,
        ),
    }
    assert dynamic_event == {
        "event_type": "codex_dynamic_tool_call_event",
        "event_params": expected_tool_item_base_payload(
            item_id="dynamic-1",
            tool_name="render_chart",
            started_at_ms=2_000,
            completed_at_ms=2_120,
            duration_ms=120,
            execution_duration_ms=88,
            final_approval_outcome="unknown",
            dynamic_tool_name="render_chart",
            success=True,
            output_content_item_count=2,
            output_text_item_count=1,
            output_image_item_count=1,
        ),
    }


def test_web_search_image_generation_and_collab_lifecycle_publish_tool_events() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust item: tool_item_event ThreadItem::WebSearch, ImageGeneration, and CollabAgentToolCall branches
    # Contract: completed lifecycle emits web-search, image-generation, and collab-agent telemetry projections.
    web_event = complete_lifecycle_item(
        {
            "kind": "WebSearch",
            "id": "web-1",
            "query": "  python rust parity  ",
            "action": {"kind": "Search", "queries": ["python", "rust"]},
        }
    )
    image_event = complete_lifecycle_item(
        {
            "kind": "ImageGeneration",
            "id": "image-1",
            "status": "error",
            "revised_prompt": "draw it",
            "saved_path": "out.png",
        }
    )
    collab_event = complete_lifecycle_item(
        {
            "kind": "CollabAgentToolCall",
            "id": "collab-1",
            "tool": "SpawnAgent",
            "status": "Completed",
            "sender_thread_id": "sender-1",
            "receiver_thread_ids": ["r1", "r2"],
            "model": "gpt-5",
            "reasoning_effort": "high",
            "agent_states": {
                "r1": {"status": "Completed"},
                "r2": {"status": "Errored"},
            },
        }
    )

    assert web_event == {
        "event_type": "codex_web_search_event",
        "event_params": expected_tool_item_base_payload(
            item_id="web-1",
            tool_name="web_search",
            started_at_ms=2_000,
            completed_at_ms=2_120,
            duration_ms=120,
            execution_duration_ms=None,
            final_approval_outcome="unknown",
            web_search_action="search",
            query_present=True,
            query_count=2,
        ),
    }
    assert image_event == {
        "event_type": "codex_image_generation_event",
        "event_params": expected_tool_item_base_payload(
            item_id="image-1",
            tool_name="image_generation",
            started_at_ms=2_000,
            completed_at_ms=2_120,
            duration_ms=120,
            execution_duration_ms=None,
            final_approval_outcome="unknown",
            terminal_status="failed",
            failure_kind="tool_error",
            revised_prompt_present=True,
            saved_path_present=True,
        ),
    }
    assert collab_event == {
        "event_type": "codex_collab_agent_tool_call_event",
        "event_params": expected_tool_item_base_payload(
            item_id="collab-1",
            tool_name="spawn_agent",
            started_at_ms=2_000,
            completed_at_ms=2_120,
            duration_ms=120,
            execution_duration_ms=None,
            final_approval_outcome="unknown",
            sender_thread_id="sender-1",
            receiver_thread_count=2,
            receiver_thread_ids=["r1", "r2"],
            requested_model="gpt-5",
            requested_reasoning_effort="high",
            agent_state_count=2,
            completed_agent_count=1,
            failed_agent_count=1,
        ),
    }


def test_file_change_event_serializes_expected_shape() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust item: CodexFileChangeEventParams, CodexFileChangeEventRequest
    # Contract: file-change tool item event flattens base fields and appends file operation counters.
    base = sample_tool_item_base()
    base.tool_name = "apply_patch"
    base.execution_duration_ms = None
    base.terminal_status = ToolItemTerminalStatus.FAILED
    base.failure_kind = ToolItemFailureKind.TOOL_ERROR
    payload = codex_file_change_event(
        base=base,
        file_change_count=4,
        file_add_count=1,
        file_update_count=1,
        file_delete_count=1,
        file_move_count=1,
    )

    assert payload == {
        "event_type": "codex_file_change_event",
        "event_params": expected_tool_item_base_payload(
            tool_name="apply_patch",
            execution_duration_ms=None,
            terminal_status="failed",
            failure_kind="tool_error",
            file_change_count=4,
            file_add_count=1,
            file_update_count=1,
            file_delete_count=1,
            file_move_count=1,
        ),
    }


def test_mcp_tool_call_event_serializes_expected_shape() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust item: CodexMcpToolCallEventParams, CodexMcpToolCallEventRequest
    # Contract: MCP tool-call event flattens base fields and appends server/tool/error fields.
    base = sample_tool_item_base()
    base.tool_name = "list_records"
    base.execution_duration_ms = 275
    payload = codex_mcp_tool_call_event(
        base=base,
        mcp_server_name="mcp-server",
        mcp_tool_name="list_records",
        mcp_error_present=True,
    )

    assert payload == {
        "event_type": "codex_mcp_tool_call_event",
        "event_params": expected_tool_item_base_payload(
            tool_name="list_records",
            execution_duration_ms=275,
            mcp_server_name="mcp-server",
            mcp_tool_name="list_records",
            mcp_error_present=True,
        ),
    }


def test_dynamic_tool_call_event_serializes_expected_shape() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust item: CodexDynamicToolCallEventParams, CodexDynamicToolCallEventRequest
    # Contract: dynamic tool-call event flattens base fields and appends tool outcome/content counters.
    base = sample_tool_item_base()
    base.tool_name = "render_chart"
    payload = codex_dynamic_tool_call_event(
        base=base,
        dynamic_tool_name="render_chart",
        success=True,
        output_content_item_count=3,
        output_text_item_count=2,
        output_image_item_count=1,
    )

    assert payload == {
        "event_type": "codex_dynamic_tool_call_event",
        "event_params": expected_tool_item_base_payload(
            tool_name="render_chart",
            dynamic_tool_name="render_chart",
            success=True,
            output_content_item_count=3,
            output_text_item_count=2,
            output_image_item_count=1,
        ),
    }


def test_collab_agent_tool_call_event_serializes_expected_shape() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust item: CodexCollabAgentToolCallEventParams, CodexCollabAgentToolCallEventRequest
    # Contract: collab-agent tool-call event flattens base fields and appends thread/model/agent summary fields.
    base = sample_tool_item_base()
    base.tool_name = "spawn_agent"
    base.execution_duration_ms = None
    payload = codex_collab_agent_tool_call_event(
        base=base,
        sender_thread_id="sender-thread-1",
        receiver_thread_count=2,
        receiver_thread_ids=["receiver-1", "receiver-2"],
        requested_model="gpt-5",
        requested_reasoning_effort="high",
        agent_state_count=3,
        completed_agent_count=2,
        failed_agent_count=1,
    )

    assert payload == {
        "event_type": "codex_collab_agent_tool_call_event",
        "event_params": expected_tool_item_base_payload(
            tool_name="spawn_agent",
            execution_duration_ms=None,
            sender_thread_id="sender-thread-1",
            receiver_thread_count=2,
            receiver_thread_ids=["receiver-1", "receiver-2"],
            requested_model="gpt-5",
            requested_reasoning_effort="high",
            agent_state_count=3,
            completed_agent_count=2,
            failed_agent_count=1,
        ),
    }


def test_web_search_event_serializes_expected_shape() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust item: WebSearchActionKind, CodexWebSearchEventParams, CodexWebSearchEventRequest
    # Contract: web-search event flattens base fields and appends action/query presence fields.
    base = sample_tool_item_base()
    base.tool_name = "web_search"
    base.execution_duration_ms = None
    payload = codex_web_search_event(
        base=base,
        web_search_action=WebSearchActionKind.SEARCH,
        query_present=True,
        query_count=2,
    )

    assert [kind.value for kind in WebSearchActionKind] == [
        "search",
        "open_page",
        "find_in_page",
        "other",
    ]
    assert payload == {
        "event_type": "codex_web_search_event",
        "event_params": expected_tool_item_base_payload(
            tool_name="web_search",
            execution_duration_ms=None,
            web_search_action="search",
            query_present=True,
            query_count=2,
        ),
    }


def test_image_generation_event_serializes_expected_shape() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust item: CodexImageGenerationEventParams, CodexImageGenerationEventRequest
    # Contract: image-generation event flattens base fields and appends revised-prompt/saved-path presence fields.
    base = sample_tool_item_base()
    base.tool_name = "image_generation"
    base.execution_duration_ms = None
    payload = codex_image_generation_event(
        base=base,
        revised_prompt_present=True,
        saved_path_present=False,
    )

    assert payload == {
        "event_type": "codex_image_generation_event",
        "event_params": expected_tool_item_base_payload(
            tool_name="image_generation",
            execution_duration_ms=None,
            revised_prompt_present=True,
            saved_path_present=False,
        ),
    }
