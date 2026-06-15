import asyncio

from pycodex.tui.app.side import (
    SIDE_ALREADY_OPEN_MESSAGE,
    SIDE_BOUNDARY_PROMPT,
    SIDE_MAIN_THREAD_UNAVAILABLE_MESSAGE,
    SIDE_NO_STARTED_CONVERSATION_MESSAGE,
    SIDE_RENAME_BLOCK_MESSAGE,
    SideActionPlan,
    SideParentStatus,
    SideParentStatusChange,
    SideThreadState,
    SideUiState,
    active_side_parent_thread_id,
    discard_side_thread,
    handle_start_side,
    apply_side_parent_status_change,
    clear_side_parent_action_status,
    install_side_thread_snapshot,
    restore_side_user_message,
    set_side_parent_status,
    side_boundary_prompt_item,
    side_developer_instructions,
    side_start_block_message,
    side_start_error_message,
    side_thread_to_discard_after_switch,
    sync_side_thread_ui,
)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()



def test_side_boundary_prompt_marks_inherited_history_reference_only():
    """Rust codex-tui app::side::side_boundary_prompt_marks_inherited_history_reference_only."""

    item = side_boundary_prompt_item()
    assert item["role"] == "user"
    text = item["content"][0]["text"]
    assert "Side conversation boundary." in text
    assert "Everything before this boundary is inherited history" in text
    assert "It is not your current task." in text
    assert "Only messages submitted after this boundary are active" in text
    assert "Do not continue, execute, or complete" in text
    assert "separate from the main thread" in text
    assert "External tools may be available according to this thread's current" in text
    assert "Any tool calls or outputs visible before this boundary happened" in text
    assert "Do not modify files" in text


def test_side_start_error_message_explains_missing_first_prompt():
    """Rust codex-tui app::side::side_start_error_message_explains_missing_first_prompt."""

    err = "thread/fork failed: no rollout found for thread id 019da1a1-bed9-7a43-88a2-b49d43915021"
    assert side_start_error_message(err) == SIDE_NO_STARTED_CONVERSATION_MESSAGE
    assert side_start_error_message("includeTurns is unavailable before first user message") == SIDE_NO_STARTED_CONVERSATION_MESSAGE


def test_side_start_error_message_uses_generic_start_wording():
    """Rust codex-tui app::side::side_start_error_message_uses_generic_start_wording."""

    assert side_start_error_message("transport disconnected") == "Failed to start side conversation: transport disconnected"


def test_side_developer_instructions_appends_existing_policy():
    """Rust codex-tui app::side::side_developer_instructions_appends_existing_policy."""

    instructions = side_developer_instructions("Existing developer policy.")
    assert "Existing developer policy." in instructions
    assert "You are in a side conversation, not the main thread." in instructions
    assert side_developer_instructions("   ").startswith("You are in a side conversation")


def test_side_parent_status_labels_actionability_and_request_mapping():
    assert SideParentStatus.NeedsInput.label(True) == "main needs input"
    assert SideParentStatus.NeedsInput.label(False) == "parent needs input"
    assert SideParentStatus.NeedsApproval.is_actionable() is True
    assert SideParentStatus.Failed.is_actionable() is False
    assert SideParentStatus.for_request("ToolRequestUserInput") is SideParentStatus.NeedsInput
    assert SideParentStatus.for_request("CommandExecutionRequestApproval") is SideParentStatus.NeedsApproval
    assert SideParentStatus.for_request("DynamicToolCall") is None


def test_side_parent_status_change_for_notifications():
    assert SideParentStatusChange.for_notification("TurnStarted") == SideParentStatusChange.Clear()
    assert SideParentStatusChange.for_notification({"TurnCompleted": {"turn": {"status": "Completed"}}}) == SideParentStatusChange.Set(SideParentStatus.Finished)
    assert SideParentStatusChange.for_notification({"TurnCompleted": {"turn": {"status": "Interrupted"}}}) == SideParentStatusChange.Set(SideParentStatus.Interrupted)
    assert SideParentStatusChange.for_notification({"TurnCompleted": {"turn": {"status": "Failed"}}}) == SideParentStatusChange.Set(SideParentStatus.Failed)
    assert SideParentStatusChange.for_notification({"TurnCompleted": {"turn": {"status": "InProgress"}}}) is None
    assert SideParentStatusChange.for_notification("ThreadClosed") == SideParentStatusChange.Set(SideParentStatus.Closed)
    assert SideParentStatusChange.for_notification("ItemStarted") == SideParentStatusChange.ClearActionable()
    assert SideParentStatusChange.for_notification("ServerRequestResolved") == SideParentStatusChange.ClearActionable()


def test_side_thread_ui_sync_and_parent_status_transitions():
    state = SideUiState(primary_thread_id="main", active_thread_id="side")
    state.side_threads["side"] = SideThreadState.new("main")

    sync_side_thread_ui(state)
    assert state.rename_block_message == SIDE_RENAME_BLOCK_MESSAGE
    assert state.side_conversation_active is True
    assert state.interrupted_turn_notice_mode == "Suppress"
    assert state.side_context_label == "Side from main thread | Ctrl+C to return"
    assert active_side_parent_thread_id(state) == "main"

    assert set_side_parent_status(state, "main", SideParentStatus.NeedsApproval) is True
    assert "main needs approval" in state.side_context_label
    assert clear_side_parent_action_status(state, "main") is True
    assert "needs approval" not in state.side_context_label
    assert apply_side_parent_status_change(state, "main", SideParentStatusChange.Set(SideParentStatus.Finished)) is True
    assert "main finished" in state.side_context_label
    assert apply_side_parent_status_change(state, "main", SideParentStatusChange.Clear()) is True
    assert "main finished" not in state.side_context_label


def test_side_thread_ui_clears_when_active_thread_is_not_side():
    state = SideUiState(primary_thread_id="main", active_thread_id="main")
    state.side_threads["side"] = SideThreadState.new("main")
    state.side_context_label = "old"
    state.side_conversation_active = True
    state.rename_block_message = SIDE_RENAME_BLOCK_MESSAGE
    state.interrupted_turn_notice_mode = "Suppress"

    sync_side_thread_ui(state)

    assert state.side_context_label is None
    assert state.side_conversation_active is False
    assert state.rename_block_message is None
    assert state.interrupted_turn_notice_mode == "Default"


def test_side_start_block_and_discard_selection_helpers():
    assert side_start_block_message(None, {}) == SIDE_MAIN_THREAD_UNAVAILABLE_MESSAGE
    assert side_start_block_message("main", {"side": object()}) == SIDE_ALREADY_OPEN_MESSAGE
    assert side_start_block_message("main", {}) is None
    assert side_thread_to_discard_after_switch("side", {"side": object()}, "main") == "side"
    assert side_thread_to_discard_after_switch("side", {"side": object()}, "side") is None
    assert side_thread_to_discard_after_switch("main", {"side": object()}, "other") is None


def test_restore_message_and_install_side_snapshot_semantics():
    state = SideUiState()
    restore_side_user_message(state, None)
    restore_side_user_message(state, "hello")
    assert state.restored_user_messages == ["hello"]

    session, turns = install_side_thread_snapshot({"thread_id": "side", "forked_from_id": "main"}, ["turn"])
    assert session == {"thread_id": "side", "forked_from_id": None}
    assert turns == []


def test_handle_start_side_success_and_failure_plans():
    state = SideUiState(primary_thread_id="main", active_thread_id="main")
    plan = run(
        handle_start_side(state, "main", user_message="question", fork_result={"thread_id": "side"}, active_after_select="side")
    )

    assert plan.action == "start_side"
    assert plan.thread_id == "side"
    assert ("thread_inject_items", SIDE_BOUNDARY_PROMPT) in plan.updates
    assert ("submit_user_message_as_plain_user_turn", "question") in plan.updates
    assert state.side_threads["side"].parent_thread_id == "main"

    blocked_state = SideUiState(primary_thread_id=None)
    blocked = run(handle_start_side(blocked_state, "main", user_message="restore"))
    assert blocked == SideActionPlan(
        action="start_side_blocked",
        parent_thread_id="main",
        messages=(SIDE_MAIN_THREAD_UNAVAILABLE_MESSAGE,),
        restored_user_message="restore",
    )
    assert blocked_state.restored_user_messages == ["restore"]

    failed_state = SideUiState(primary_thread_id="main")
    failed = run(handle_start_side(failed_state, "main", fork_error="transport"))
    assert failed.action == "start_side_fork_failed"
    assert failed.messages == ("Failed to start side conversation: transport",)


def test_discard_side_thread_success_and_error_plans():
    ok = run(discard_side_thread("side"))
    assert ok.action == "discard_side_thread"
    assert ("discard_thread_local_state", "side") in ok.updates

    interrupt = run(discard_side_thread("side", interrupt_error="busy"))
    assert interrupt.action == "discard_side_thread_interrupt_failed"
    assert interrupt.messages == ("Failed to close side conversation side; it is still open: busy",)

    unsubscribe = run(discard_side_thread("side", unsubscribe_error="closed"))
    assert unsubscribe.action == "discard_side_thread_unsubscribe_failed"
    assert unsubscribe.messages == ("Failed to close side conversation side; it is still open: closed",)
