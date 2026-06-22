from __future__ import annotations

from types import SimpleNamespace

from pycodex.app_server.request_processors_thread_processor import (
    ThreadRequestProcessor,
    collect_resume_override_mismatches,
    has_model_resume_override,
    merge_persisted_resume_metadata,
    normalize_thread_list_cwd_filters,
    normalize_thread_turns_status,
    paginate_thread_turns,
    parse_thread_turns_cursor,
    reconstruct_thread_turns_for_turns_list,
    requested_permissions_trust_project,
    serialize_thread_turns_cursor,
    set_thread_name_from_title,
    unsupported_thread_store_operation,
    validate_dynamic_tools,
)
from pycodex.app_server_protocol import DynamicToolSpec, ThreadListCwdFilter, ThreadResumeParams, ThreadStatus, TurnStatus
from pycodex.app_server_protocol.thread_data import Thread, Turn


def test_thread_request_processor_new_preserves_dependency_surface() -> None:
    # Rust source: ThreadRequestProcessor::new stores all constructor handles.
    values = {name: object() for name in _processor_fields()}
    processor = ThreadRequestProcessor.new(**values)

    for name, value in values.items():
        assert getattr(processor, name) is value


def test_validate_dynamic_tools_rejects_rust_reserved_and_duplicate_names() -> None:
    # Rust source: validate_dynamic_tools.
    validate_dynamic_tools([DynamicToolSpec(name="tool_a", description="desc", input_schema={}, namespace="ns")])

    _assert_value_error(
        "dynamic tool name is reserved: mcp",
        lambda: validate_dynamic_tools([DynamicToolSpec(name="mcp", description="desc", input_schema={})]),
    )
    _assert_value_error(
        "duplicate dynamic tool name: tool_a",
        lambda: validate_dynamic_tools(
            [
                DynamicToolSpec(name="tool_a", description="desc", input_schema={}),
                DynamicToolSpec(name="tool_a", description="desc", input_schema={}),
            ]
        ),
    )
    _assert_value_error(
        "deferred dynamic tool must include a namespace: lazy",
        lambda: validate_dynamic_tools([DynamicToolSpec(name="lazy", description="desc", input_schema={}, defer_loading=True)]),
    )


def test_validate_dynamic_tools_rejects_namespace_collisions_and_schema_errors() -> None:
    _assert_value_error(
        "reserved Responses API namespace",
        lambda: validate_dynamic_tools([DynamicToolSpec(name="search", description="desc", input_schema={}, namespace="web")]),
    )

    def schema_validator(_schema):
        raise RuntimeError("schema no")

    _assert_value_error(
        "dynamic tool input schema is not supported for custom: schema no",
        lambda: validate_dynamic_tools(
            [DynamicToolSpec(name="custom", description="desc", input_schema={"type": "object"}, namespace="ns")],
            schema_validator=schema_validator,
        ),
    )


def test_thread_turns_cursor_serializes_camel_case_and_invalid_cursor_errors() -> None:
    # Rust source: serialize_thread_turns_cursor / parse_thread_turns_cursor.
    cursor = serialize_thread_turns_cursor("turn-2", False)

    assert cursor == '{"turnId":"turn-2","includeAnchor":false}'
    parsed = parse_thread_turns_cursor(cursor)
    assert parsed.turn_id == "turn-2"
    assert parsed.include_anchor is False

    try:
        parse_thread_turns_cursor("not-json")
    except Exception as exc:
        assert getattr(exc, "code") == -32600
        assert getattr(exc, "message") == "invalid cursor: not-json"
    else:
        raise AssertionError("expected invalid_request")


def test_paginate_thread_turns_matches_asc_desc_anchor_semantics() -> None:
    # Rust source: paginate_thread_turns.
    turns = [_turn("turn-1"), _turn("turn-2"), _turn("turn-3")]

    page = paginate_thread_turns(turns, limit=2, sort_direction="asc")
    assert [turn.id for turn in page.turns] == ["turn-1", "turn-2"]
    assert page.backwards_cursor == serialize_thread_turns_cursor("turn-1", True)
    assert page.next_cursor == serialize_thread_turns_cursor("turn-2", False)

    page = paginate_thread_turns(turns, cursor=page.next_cursor, limit=2, sort_direction="asc")
    assert [turn.id for turn in page.turns] == ["turn-3"]

    desc = paginate_thread_turns(turns, limit=2, sort_direction="desc")
    assert [turn.id for turn in desc.turns] == ["turn-3", "turn-2"]
    assert desc.next_cursor == serialize_thread_turns_cursor("turn-2", False)


def test_normalize_thread_turns_status_interrupts_without_active_thread() -> None:
    # Rust source: normalize_thread_turns_status / reconstruct_thread_turns_for_turns_list.
    turns = [_turn("done", TurnStatus.COMPLETED), _turn("running", TurnStatus.IN_PROGRESS)]

    normalize_thread_turns_status(turns, ThreadStatus.idle(), False)

    assert [turn.status for turn in turns] == [TurnStatus.COMPLETED, TurnStatus.INTERRUPTED]

    active = reconstruct_thread_turns_for_turns_list(turns, ThreadStatus.idle(), False, _turn("active", TurnStatus.IN_PROGRESS))
    assert [turn.id for turn in active] == ["done", "running", "active"]
    assert active[-1].status is TurnStatus.IN_PROGRESS


def test_resume_override_metadata_helpers_follow_model_override_rules() -> None:
    # Rust source: has_model_resume_override / merge_persisted_resume_metadata.
    overrides = SimpleNamespace(model=None, model_provider=None)
    metadata = SimpleNamespace(model="gpt-5", model_provider="openai", reasoning_effort="high")

    request_overrides = merge_persisted_resume_metadata(None, overrides, metadata)

    assert overrides.model == "gpt-5"
    assert overrides.model_provider == "openai"
    assert request_overrides == {"model_reasoning_effort": "high"}
    assert has_model_resume_override({"model": "other"}, SimpleNamespace(model=None, model_provider=None)) is True


def test_collect_resume_override_mismatches_reports_ignored_running_overrides() -> None:
    snapshot = SimpleNamespace(
        model="active-model",
        model_provider_id="active-provider",
        service_tier="default",
        cwd="C:/repo",
        workspace_roots=("C:/repo",),
        approval_policy="never",
        approvals_reviewer="user",
        sandbox="workspace-write",
        active_permission_profile="workspace-write",
        personality="codex",
    )
    request = ThreadResumeParams(model="other", permissions="danger-full-access", config={"x": 1})

    details = collect_resume_override_mismatches(request, snapshot)

    assert any(detail.startswith("model requested=") for detail in details)
    assert "permissions override was provided and ignored while running; active='workspace-write'" in details
    assert "config overrides were provided and ignored while running" in details


def test_cwd_filters_name_and_permission_helpers() -> None:
    normalized = normalize_thread_list_cwd_filters(ThreadListCwdFilter([".", "."]))
    assert len(normalized) == 2

    thread = Thread(
        id="thread-1",
        session_id="thread-1",
        forked_from_id=None,
        preview="original",
        ephemeral=False,
        model_provider="openai",
        created_at=1,
        updated_at=1,
        status=ThreadStatus.not_loaded(),
        path=None,
        cwd=".",
        cli_version="test",
        source="unknown",
        turns=(),
    )
    assert set_thread_name_from_title(thread, "original") is thread
    renamed = set_thread_name_from_title(thread, "A better name")
    assert renamed.name == "A better name"

    assert requested_permissions_trust_project(SimpleNamespace(sandbox_mode="workspace-write"), ".") is True
    assert requested_permissions_trust_project(SimpleNamespace(default_permissions="danger-full-access"), ".") is True
    assert unsupported_thread_store_operation("thread/read").code == -32601


def _turn(turn_id: str, status=TurnStatus.COMPLETED) -> Turn:
    return Turn(id=turn_id, items=(), status=status)


def _assert_value_error(expected: str, fn) -> None:
    try:
        fn()
    except ValueError as exc:
        assert expected in str(exc)
    else:
        raise AssertionError("expected ValueError")


def _processor_fields() -> tuple[str, ...]:
    return (
        "auth_manager",
        "thread_manager",
        "outgoing",
        "arg0_paths",
        "config",
        "config_manager",
        "thread_store",
        "pending_thread_unloads",
        "thread_state_manager",
        "thread_watch_manager",
        "thread_list_state_permit",
        "thread_goal_processor",
        "state_db",
        "background_tasks",
        "skills_watcher",
    )
