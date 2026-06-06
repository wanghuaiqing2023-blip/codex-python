from pathlib import Path
from types import SimpleNamespace

from pycodex.core.context_manager.history import estimate_item_token_count
from pycodex.core.state.session import SessionState
from pycodex.protocol import (
    AccountPlanType,
    AdditionalPermissionProfile,
    AskForApproval,
    ContentItem,
    CreditsSnapshot,
    FileSystemPermissions,
    FunctionCallOutputPayload,
    NetworkPermissions,
    RateLimitSnapshot,
    RateLimitWindow,
    ResponseItem,
    SandboxPolicy,
    TokenUsage,
    TurnContextItem,
)


def _assistant_msg(text: str) -> ResponseItem:
    return ResponseItem.message("assistant", (ContentItem.output_text(text),))


def _user_msg(text: str) -> ResponseItem:
    return ResponseItem.message("user", (ContentItem.input_text(text),))


def _custom_tool_call_output(call_id: str, output: str = "ok") -> ResponseItem:
    return ResponseItem(
        type="custom_tool_call_output",
        call_id=call_id,
        output=FunctionCallOutputPayload.from_text(output),
    )


def _reference_context_item() -> TurnContextItem:
    return TurnContextItem(
        cwd=Path("C:/work/project"),
        approval_policy=AskForApproval.ON_REQUEST,
        sandbox_policy=SandboxPolicy.danger_full_access(),
        model="gpt-test",
    )


def test_session_state_token_info_delegates_to_history() -> None:
    """Rust source contract: ``SessionState::update_token_info_from_usage`` delegates to history."""

    state = SessionState.new()

    state.update_token_info_from_usage(TokenUsage(total_tokens=100), 8_000)

    info = state.token_info()
    assert info is not None
    assert info.total_token_usage.total_tokens == 100
    assert info.last_token_usage.total_tokens == 100
    assert info.model_context_window == 8_000
    assert state.token_info_and_rate_limits() == (info, None)


def test_session_state_set_token_usage_full_delegates_to_history() -> None:
    """Rust source contract: ``SessionState::set_token_usage_full`` delegates to history."""

    state = SessionState.new()

    state.set_token_usage_full(4_096)

    info = state.token_info()
    assert info is not None
    assert info.total_token_usage.total_tokens == 4_096
    assert info.last_token_usage.total_tokens == 4_096
    assert info.model_context_window == 4_096


def test_session_state_total_token_usage_delegates_to_history_tail_accounting() -> None:
    """Rust source contract: ``SessionState::get_total_token_usage`` delegates to history."""

    state = SessionState.new()
    counted = _assistant_msg("already counted by API")
    added_user = _user_msg("new user message")
    added_tool_output = _custom_tool_call_output("tool-tail", "new tool output")

    state.record_items((counted,))
    state.update_token_info_from_usage(TokenUsage(total_tokens=100), None)
    state.record_items((added_user, added_tool_output))

    assert state.get_total_token_usage(True) == (
        100 + estimate_item_token_count(added_user) + estimate_item_token_count(added_tool_output)
    )


def test_session_state_record_items_delegates_to_history_filtering() -> None:
    """Rust source contract: ``SessionState::record_items`` delegates to ``ContextManager``."""

    state = SessionState.new()
    system = ResponseItem.message("system", (ContentItem.output_text("drop"),))
    user = _user_msg("keep")

    state.record_items((system, user))

    assert state.history.raw_items() == [user]


def test_session_state_clone_history_preserves_history_state_and_is_independent() -> None:
    """Rust source contract: ``SessionState::clone_history`` clones the context manager."""

    state = SessionState.new()
    user = _user_msg("original")
    reference = _reference_context_item()
    state.record_items((user,))
    state.update_token_info_from_usage(TokenUsage(total_tokens=42), 8_000)
    state.set_reference_context_item(reference)

    cloned = state.clone_history()
    state.replace_history((_user_msg("replacement"),), None)

    assert cloned.raw_items() == [user]
    assert cloned.token_info() == state.token_info()
    assert cloned.reference_context_item() == reference
    assert state.history.raw_items() == [_user_msg("replacement")]
    assert state.reference_context_item() is None


def test_session_state_previous_turn_settings_round_trip() -> None:
    """Rust source contract: ``previous_turn_settings`` returns the stored optional settings."""

    state = SessionState.new()
    settings = SimpleNamespace(model="gpt-old", realtime_active=True)

    assert state.previous_turn_settings() is None
    state.set_previous_turn_settings(settings)
    assert state.previous_turn_settings() is settings
    state.set_previous_turn_settings(None)
    assert state.previous_turn_settings() is None


def test_session_state_take_next_turn_is_first_consumes_default_true() -> None:
    """Rust source contract: ``take_next_turn_is_first`` returns current value then clears it."""

    state = SessionState.new()

    assert state.take_next_turn_is_first() is True
    assert state.take_next_turn_is_first() is False
    state.set_next_turn_is_first(True)
    assert state.take_next_turn_is_first() is True
    assert state.take_next_turn_is_first() is False
    state.set_next_turn_is_first(False)
    assert state.take_next_turn_is_first() is False


def test_session_state_replace_history_sets_reference_context_and_clears_auto_compact_prefill() -> None:
    """Rust source contract: ``SessionState::replace_history`` clears auto-compact prefill."""

    state = SessionState.new()
    reference = _reference_context_item()
    item = _user_msg("replacement")
    state.set_auto_compact_window_estimated_prefill(123)

    state.replace_history((item,), reference)

    assert state.history.raw_items() == [item]
    assert state.history.history_version == 1
    assert state.reference_context_item() == reference
    assert state.auto_compact_window_snapshot().prefill_input_tokens is None


def test_session_state_auto_compact_window_helpers_delegate() -> None:
    """Rust source contract: SessionState auto-compact helpers delegate to ``AutoCompactWindow``."""

    state = SessionState.new()

    state.set_auto_compact_window_estimated_prefill(50)
    assert state.auto_compact_window_snapshot().prefill_input_tokens == 50

    state.ensure_auto_compact_window_server_prefill_from_usage(TokenUsage(input_tokens=77))
    assert state.auto_compact_window_snapshot().prefill_input_tokens == 77

    state.start_next_auto_compact_window()
    snapshot = state.auto_compact_window_snapshot()
    assert snapshot.ordinal == 2
    assert snapshot.prefill_input_tokens is None


def test_session_state_rate_limits_default_missing_limit_id_and_preserve_credit_plan() -> None:
    """Rust source contract: ``SessionState::set_rate_limits`` merges missing fields."""

    state = SessionState.new()
    previous = RateLimitSnapshot(
        limit_id="codex",
        credits=CreditsSnapshot(has_credits=True, unlimited=False, balance="10"),
        plan_type=AccountPlanType.PRO,
    )

    state.set_rate_limits(previous)
    state.set_rate_limits(RateLimitSnapshot(primary=RateLimitWindow(used_percent=100.0, window_minutes=60)))

    assert state.latest_rate_limits is not None
    assert state.latest_rate_limits.limit_id == "codex"
    assert state.latest_rate_limits.primary.used_percent == 100.0
    assert state.latest_rate_limits.credits == previous.credits
    assert state.latest_rate_limits.plan_type == AccountPlanType.PRO
    assert state.token_info_and_rate_limits() == (None, state.latest_rate_limits)


def test_session_state_rate_limits_carry_credit_plan_across_buckets() -> None:
    """Rust source contract: missing credits and plan are inherited from previous snapshot."""

    state = SessionState.new()
    state.set_rate_limits(
        RateLimitSnapshot(
            limit_id="codex",
            limit_name="codex",
            primary=RateLimitWindow(used_percent=10.0, window_minutes=60, resets_at=100),
            credits=CreditsSnapshot(has_credits=True, unlimited=False, balance="50"),
            plan_type=AccountPlanType.PLUS,
        )
    )

    state.set_rate_limits(
        RateLimitSnapshot(
            limit_id="codex_other",
            primary=RateLimitWindow(used_percent=30.0, window_minutes=120, resets_at=200),
        )
    )

    assert state.latest_rate_limits is not None
    assert state.latest_rate_limits.limit_id == "codex_other"
    assert state.latest_rate_limits.limit_name is None
    assert state.latest_rate_limits.primary.used_percent == 30.0
    assert state.latest_rate_limits.primary.window_minutes == 120
    assert state.latest_rate_limits.credits == CreditsSnapshot(True, False, "50")
    assert state.latest_rate_limits.plan_type == AccountPlanType.PLUS


def test_session_state_server_reasoning_flag_is_bool_only() -> None:
    """Rust source contract: server reasoning flag is stored as session state."""

    state = SessionState.new()

    assert state.server_reasoning_included() is False
    state.set_server_reasoning_included(True)
    assert state.server_reasoning_included() is True


def test_session_state_mcp_dependency_prompted_records_names_and_returns_copy() -> None:
    """Rust source contract: ``record_mcp_dependency_prompted`` extends a HashSet."""

    state = SessionState.new()

    state.record_mcp_dependency_prompted(("filesystem", "git", "filesystem"))
    prompted = state.mcp_dependency_prompted()
    prompted.add("mutated-copy")

    assert state.mcp_dependency_prompted() == {"filesystem", "git"}


def test_session_state_startup_prewarm_take_clears_value() -> None:
    """Rust source contract: ``take_session_startup_prewarm`` takes the optional handle."""

    state = SessionState.new()
    handle = object()

    assert state.take_session_startup_prewarm() is None
    state.set_session_startup_prewarm(handle)
    assert state.take_session_startup_prewarm() is handle
    assert state.take_session_startup_prewarm() is None


def test_session_state_connector_selection_merges_returns_copy_and_clears() -> None:
    """Rust source contract: connector selection is a session HashSet."""

    state = SessionState.new()

    merged = state.merge_connector_selection(("connector-a", "connector-b"))
    merged.add("mutated-copy")
    state.merge_connector_selection(("connector-b", "connector-c"))

    assert state.get_connector_selection() == {"connector-a", "connector-b", "connector-c"}
    state.clear_connector_selection()
    assert state.get_connector_selection() == set()


def test_session_state_pending_session_start_sources_are_fifo() -> None:
    """Rust source contract: pending session-start sources use VecDeque push_back/pop_front."""

    state = SessionState.new()

    assert state.take_pending_session_start_source() is None
    state.queue_pending_session_start_source("first")
    state.queue_pending_session_start_source("second")

    assert state.take_pending_session_start_source() == "first"
    assert state.take_pending_session_start_source() == "second"
    assert state.take_pending_session_start_source() is None


def test_session_state_record_granted_permissions_merges_profiles() -> None:
    """Rust source contract: ``SessionState::record_granted_permissions`` merges session grants."""

    state = SessionState.new()
    network = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
    file_system = AdditionalPermissionProfile(
        file_system=FileSystemPermissions.from_read_write_roots(None, (Path("C:/work/project"),))
    )

    state.record_granted_permissions(network)
    state.record_granted_permissions(file_system)

    granted = state.granted_permissions()
    assert granted is not None
    assert granted.network == NetworkPermissions(enabled=True)
    assert granted.file_system == file_system.file_system
