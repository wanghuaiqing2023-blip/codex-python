from pycodex.tui.app_backtrack import (
    BacktrackSelection,
    BacktrackRollbackCompletion,
    BACKTRACK_ROLLBACK_ALREADY_IN_PROGRESS,
    BacktrackPrimePlan,
    BacktrackCloseOverlayPlan,
    BacktrackOverlaySyncPlan,
    BacktrackEscKeyPlan,
    BacktrackOverlayEventPlan,
    BacktrackPreviewPlan,
    BacktrackRollbackPlan,
    BacktrackState,
    NO_PREVIOUS_MESSAGE_TO_EDIT,
    PendingBacktrackRollback,
    USIZE_MAX,
    agent_cell,
    agent_group_count,
    agent_group_count_ignores_context_compacted_marker,
    agent_group_positions_iter,
    apply_backtrack_rollback_state,
    backtrack_selection,
    backtrack_target_requires_user_message,
    backtrack_unavailable_info_message_snapshot,
    begin_overlay_backtrack_preview_state,
    confirm_backtrack_from_main_state,
    close_transcript_overlay_state,
    sync_overlay_after_transcript_trim_state,
    has_backtrack_target,
    handle_backtrack_rollback_failed_state,
    handle_backtrack_rollback_succeeded_state,
    handle_backtrack_esc_key_state,
    handle_backtrack_overlay_event_state,
    info_cell,
    apply_backtrack_selection_index,
    nth_user_position,
    next_backtrack_selection_index,
    next_forward_backtrack_selection_index,
    open_backtrack_preview_state,
    prime_backtrack_state,
    reset_backtrack_state,
    session_cell,
    trim_drop_last_n_user_turns_allows_overflow,
    trim_drop_last_n_user_turns_applies_rollback_semantics,
    trim_transcript_cells_drop_last_n_user_turns,
    trim_transcript_cells_to_nth_user,
    trim_transcript_for_first_user_drops_user_and_newer_cells,
    trim_transcript_for_later_user_keeps_prior_history,
    trim_transcript_preserves_cells_before_selected_user,
    user_cell,
    user_count,
    user_positions_iter,
)


def test_backtrack_state_defaults_match_rust():
    state = BacktrackState()
    assert state.primed is False
    assert state.base_id is None
    assert state.nth_user_message == USIZE_MAX
    assert state.overlay_preview_active is False
    assert state.pending_rollback is None


def test_selection_and_pending_rollback_carry_payloads():
    selection = BacktrackSelection(1, prefill="retry", text_elements=["t"], remote_image_urls=["https://example.test/a.png"])
    pending = PendingBacktrackRollback(selection, thread_id="thread-1")
    assert pending.selection.prefill == "retry"
    assert pending.thread_id == "thread-1"


def test_user_positions_restart_after_latest_session_cell():
    cells = [user_cell("old"), session_cell(), agent_cell("intro"), user_cell("first"), agent_cell("after"), user_cell("second")]
    assert list(user_positions_iter(cells)) == [3, 5]
    assert user_count(cells) == 2
    assert nth_user_position(cells, 1) == 5
    assert nth_user_position(cells, 2) is None


def test_trim_transcript_for_first_user_drops_user_and_newer_cells():
    cells = [user_cell("first user"), agent_cell("assistant")]
    assert trim_transcript_cells_to_nth_user(cells, 0) is True
    assert cells == []
    assert trim_transcript_for_first_user_drops_user_and_newer_cells() is True


def test_trim_transcript_preserves_cells_before_selected_user():
    cells = [agent_cell("intro"), user_cell("first"), agent_cell("after", stream_continuation=True)]
    assert trim_transcript_cells_to_nth_user(cells, 0) is True
    assert [cell.message for cell in cells] == ["intro"]
    assert trim_transcript_preserves_cells_before_selected_user() is True


def test_trim_transcript_for_later_user_keeps_prior_history():
    cells = [agent_cell("intro"), user_cell("first"), agent_cell("between", stream_continuation=True), user_cell("second"), agent_cell("tail", stream_continuation=True)]
    assert trim_transcript_cells_to_nth_user(cells, 1) is True
    assert [cell.message for cell in cells] == ["intro", "first", "between"]
    assert trim_transcript_for_later_user_keeps_prior_history() is True


def test_trim_drop_last_n_user_turns_applies_rollback_semantics():
    cells = [user_cell("first"), agent_cell("after first"), user_cell("second"), agent_cell("after second")]
    assert trim_transcript_cells_drop_last_n_user_turns(cells, 1) is True
    assert [cell.message for cell in cells] == ["first", "after first"]
    assert trim_drop_last_n_user_turns_applies_rollback_semantics() is True


def test_trim_drop_last_n_user_turns_allows_overflow_and_ignores_zero():
    cells = [agent_cell("intro"), user_cell("first"), agent_cell("after")]
    assert trim_transcript_cells_drop_last_n_user_turns(cells, 0) is False
    assert trim_transcript_cells_drop_last_n_user_turns(cells, 999) is True
    assert [cell.message for cell in cells] == ["intro"]
    assert trim_drop_last_n_user_turns_allows_overflow() is True


def test_agent_group_count_ignores_context_compacted_marker_and_stream_continuations():
    cells = [agent_cell("first"), info_cell("Context compacted"), agent_cell("continued", stream_continuation=True), agent_cell("second")]
    assert list(agent_group_positions_iter(cells)) == [0, 3]
    assert agent_group_count(cells) == 2
    assert agent_group_count_ignores_context_compacted_marker() is True


def test_backtrack_target_requires_user_message():
    assert has_backtrack_target([agent_cell("assistant"), info_cell("Context compacted")]) is False
    assert has_backtrack_target([agent_cell("assistant"), user_cell("hello")]) is True
    assert backtrack_target_requires_user_message() is True


def test_backtrack_unavailable_info_message_snapshot_text():
    assert backtrack_unavailable_info_message_snapshot() == NO_PREVIOUS_MESSAGE_TO_EDIT


def test_reset_backtrack_state_resets_rust_state_fields():
    state = BacktrackState(
        primed=True,
        base_id="thread-1",
        nth_user_message=2,
        overlay_preview_active=True,
        pending_rollback=PendingBacktrackRollback(BacktrackSelection(1), thread_id="thread-1"),
    )

    reset_backtrack_state(state)

    assert state.primed is False
    assert state.base_id is None
    assert state.nth_user_message == USIZE_MAX
    assert state.overlay_preview_active is True
    assert state.pending_rollback is not None


def test_backtrack_selection_matches_thread_and_copies_user_payloads():
    cells = [
        agent_cell("intro"),
        user_cell("first", text_elements=["a"], local_image_paths=["/tmp/a.png"]),
        user_cell("second", remote_image_urls=["https://example.test/b.png"]),
    ]
    state = BacktrackState(primed=True, base_id="thread-1", nth_user_message=1)

    selection = backtrack_selection(state, "thread-1", cells)

    assert selection == BacktrackSelection(
        nth_user_message=1,
        prefill="second",
        text_elements=[],
        local_image_paths=[],
        remote_image_urls=["https://example.test/b.png"],
    )
    assert backtrack_selection(state, "other-thread", cells) is None


def test_backtrack_selection_returns_empty_selection_when_user_index_is_stale():
    state = BacktrackState(primed=True, base_id="thread-1", nth_user_message=99)

    selection = backtrack_selection(state, "thread-1", [agent_cell("intro")])

    assert selection == BacktrackSelection(nth_user_message=99)


def test_apply_backtrack_rollback_state_plans_pending_rollback_and_composer_payload():
    cells = [user_cell("first"), agent_cell("after first"), user_cell("second")]
    state = BacktrackState()
    selection = BacktrackSelection(
        nth_user_message=1,
        prefill="second",
        text_elements=["token"],
        local_image_paths=["/tmp/a.png"],
        remote_image_urls=["https://example.test/a.png"],
    )

    plan = apply_backtrack_rollback_state(state, selection, cells, thread_id="thread-1")

    assert plan == BacktrackRollbackPlan(
        num_turns=1,
        pending_rollback=PendingBacktrackRollback(selection, thread_id="thread-1"),
        remote_image_urls=["https://example.test/a.png"],
        composer_prefill="second",
        text_elements=["token"],
        local_image_paths=["/tmp/a.png"],
    )
    assert plan.should_submit_rollback is True
    assert plan.should_set_composer_text is True
    assert state.pending_rollback == plan.pending_rollback


def test_apply_backtrack_rollback_state_ignores_empty_or_zero_turn_cases():
    state = BacktrackState()
    selection = BacktrackSelection(nth_user_message=0)

    assert apply_backtrack_rollback_state(state, selection, [], thread_id="thread-1") is None
    assert apply_backtrack_rollback_state(state, BacktrackSelection(2), [user_cell("one")], "thread-1") is None
    assert state.pending_rollback is None


def test_apply_backtrack_rollback_state_reports_pending_guard_without_mutating():
    existing = PendingBacktrackRollback(BacktrackSelection(0), thread_id="thread-1")
    state = BacktrackState(pending_rollback=existing)

    plan = apply_backtrack_rollback_state(
        state,
        BacktrackSelection(0, prefill="retry"),
        [user_cell("one")],
        thread_id="thread-1",
    )

    assert plan == BacktrackRollbackPlan(error_message=BACKTRACK_ROLLBACK_ALREADY_IN_PROGRESS)
    assert plan.should_submit_rollback is False
    assert plan.should_set_composer_text is False
    assert state.pending_rollback is existing


def test_handle_backtrack_rollback_succeeded_finishes_pending_matching_thread():
    cells = [user_cell("first"), agent_cell("after first"), user_cell("second"), agent_cell("tail")]
    selection = BacktrackSelection(nth_user_message=1)
    state = BacktrackState(
        pending_rollback=PendingBacktrackRollback(selection, thread_id="thread-1")
    )

    completion = handle_backtrack_rollback_succeeded_state(
        state,
        cells,
        active_thread_id="thread-1",
        num_turns=1,
    )

    assert completion == BacktrackRollbackCompletion(changed=True, user_count_after_trim=1)
    assert [cell.message for cell in cells] == ["first", "after first"]
    assert state.pending_rollback is None


def test_handle_backtrack_rollback_succeeded_ignores_stale_thread_pending():
    cells = [user_cell("first"), agent_cell("tail")]
    state = BacktrackState(
        pending_rollback=PendingBacktrackRollback(BacktrackSelection(0), thread_id="old-thread")
    )

    completion = handle_backtrack_rollback_succeeded_state(
        state,
        cells,
        active_thread_id="new-thread",
        num_turns=1,
    )

    assert completion == BacktrackRollbackCompletion(ignored_for_thread_mismatch=True)
    assert [cell.message for cell in cells] == ["first", "tail"]
    assert state.pending_rollback is None


def test_handle_backtrack_rollback_succeeded_without_pending_applies_thread_rollback():
    cells = [user_cell("first"), agent_cell("after first"), user_cell("second"), agent_cell("tail")]
    state = BacktrackState()

    completion = handle_backtrack_rollback_succeeded_state(
        state,
        cells,
        active_thread_id="thread-1",
        num_turns=1,
    )

    assert completion == BacktrackRollbackCompletion(
        changed=True,
        apply_thread_rollback_turns=1,
        user_count_after_trim=1,
    )
    assert [cell.message for cell in cells] == ["first", "after first"]


def test_handle_backtrack_rollback_failed_clears_pending_guard():
    state = BacktrackState(
        pending_rollback=PendingBacktrackRollback(BacktrackSelection(0), thread_id="thread-1")
    )

    handle_backtrack_rollback_failed_state(state)

    assert state.pending_rollback is None


def test_backtrack_selection_index_steps_older_like_rust():
    assert next_backtrack_selection_index(USIZE_MAX, 3) == 2
    assert next_backtrack_selection_index(2, 3) == 1
    assert next_backtrack_selection_index(1, 3) == 0
    assert next_backtrack_selection_index(0, 3) == 0
    assert next_backtrack_selection_index(99, 3) == 2
    assert next_backtrack_selection_index(USIZE_MAX, 0) == USIZE_MAX


def test_forward_backtrack_selection_index_steps_newer_like_rust():
    assert next_forward_backtrack_selection_index(USIZE_MAX, 3) == 2
    assert next_forward_backtrack_selection_index(0, 3) == 1
    assert next_forward_backtrack_selection_index(1, 3) == 2
    assert next_forward_backtrack_selection_index(2, 3) == 2
    assert next_forward_backtrack_selection_index(99, 3) == 2
    assert next_forward_backtrack_selection_index(USIZE_MAX, 0) == USIZE_MAX


def test_apply_backtrack_selection_index_sets_state_and_returns_highlight_cell():
    state = BacktrackState()
    cells = [agent_cell("intro"), user_cell("first"), agent_cell("between"), user_cell("second")]

    highlight = apply_backtrack_selection_index(state, cells, 1)

    assert highlight == 3
    assert state.nth_user_message == 1

    highlight = apply_backtrack_selection_index(state, cells, 99)

    assert highlight is None
    assert state.nth_user_message == USIZE_MAX


def test_confirm_backtrack_from_main_returns_selection_and_resets_state():
    cells = [user_cell("first"), user_cell("second")]
    state = BacktrackState(
        primed=True,
        base_id="thread-1",
        nth_user_message=1,
        overlay_preview_active=True,
        pending_rollback=PendingBacktrackRollback(BacktrackSelection(0), thread_id="thread-1"),
    )

    selection = confirm_backtrack_from_main_state(state, "thread-1", cells)

    assert selection == BacktrackSelection(nth_user_message=1, prefill="second")
    assert state.primed is False
    assert state.base_id is None
    assert state.nth_user_message == USIZE_MAX
    assert state.overlay_preview_active is True
    assert state.pending_rollback is not None


def test_confirm_backtrack_from_main_resets_state_even_without_matching_thread():
    state = BacktrackState(primed=True, base_id="thread-1", nth_user_message=0)

    selection = confirm_backtrack_from_main_state(state, "other-thread", [user_cell("first")])

    assert selection is None
    assert state.primed is False
    assert state.base_id is None
    assert state.nth_user_message == USIZE_MAX


def test_prime_backtrack_state_sets_base_and_reports_hint_target():
    state = BacktrackState(nth_user_message=1)

    plan = prime_backtrack_state(state, "thread-1", [agent_cell("intro"), user_cell("first")])

    assert plan == BacktrackPrimePlan(show_hint=True)
    assert state.primed is True
    assert state.base_id == "thread-1"
    assert state.nth_user_message == USIZE_MAX


def test_prime_backtrack_state_does_not_request_hint_without_user_target():
    state = BacktrackState()

    plan = prime_backtrack_state(state, "thread-1", [agent_cell("intro")])

    assert plan == BacktrackPrimePlan(show_hint=False)
    assert state.primed is True
    assert state.base_id == "thread-1"
    assert state.nth_user_message == USIZE_MAX


def test_close_transcript_overlay_state_resets_backtrack_preview_state():
    state = BacktrackState(
        primed=True,
        base_id="thread-1",
        nth_user_message=1,
        overlay_preview_active=True,
    )

    plan = close_transcript_overlay_state(state, has_deferred_history_lines=True)

    assert plan == BacktrackCloseOverlayPlan(
        should_flush_deferred_history=True,
        reset_backtrack=True,
    )
    assert state.overlay_preview_active is False
    assert state.primed is False
    assert state.base_id is None
    assert state.nth_user_message == USIZE_MAX


def test_close_transcript_overlay_state_preserves_non_preview_backtrack_fields():
    state = BacktrackState(primed=True, base_id="thread-1", nth_user_message=1)

    plan = close_transcript_overlay_state(state, has_deferred_history_lines=False)

    assert plan == BacktrackCloseOverlayPlan(
        should_flush_deferred_history=False,
        reset_backtrack=False,
    )
    assert state.overlay_preview_active is False
    assert state.primed is True
    assert state.base_id == "thread-1"
    assert state.nth_user_message == 1


def test_sync_overlay_after_transcript_trim_clamps_preview_selection():
    state = BacktrackState(overlay_preview_active=True, nth_user_message=5)
    cells = [user_cell("first"), agent_cell("after first"), user_cell("second")]

    plan = sync_overlay_after_transcript_trim_state(state, cells, overlay_open=True)

    assert plan == BacktrackOverlaySyncPlan(
        replace_overlay_cells=True,
        clear_deferred_history_lines=True,
        highlighted_cell_index=2,
    )
    assert state.nth_user_message == 1


def test_sync_overlay_after_transcript_trim_clears_selection_when_no_users_remain():
    state = BacktrackState(overlay_preview_active=True, nth_user_message=0)

    plan = sync_overlay_after_transcript_trim_state(state, [agent_cell("intro")], overlay_open=False)

    assert plan == BacktrackOverlaySyncPlan(
        replace_overlay_cells=False,
        clear_deferred_history_lines=True,
        highlighted_cell_index=None,
    )
    assert state.nth_user_message == USIZE_MAX


def test_sync_overlay_after_transcript_trim_without_preview_only_reports_side_effects():
    state = BacktrackState(overlay_preview_active=False, nth_user_message=1)

    plan = sync_overlay_after_transcript_trim_state(state, [user_cell("first")], overlay_open=True)

    assert plan == BacktrackOverlaySyncPlan(
        replace_overlay_cells=True,
        clear_deferred_history_lines=True,
        highlighted_cell_index=None,
    )
    assert state.nth_user_message == 1


def test_handle_backtrack_esc_key_ignores_non_empty_composer():
    state = BacktrackState()

    plan = handle_backtrack_esc_key_state(
        state,
        composer_is_empty=False,
        overlay_open=False,
        thread_id="thread-1",
        transcript_cells=[user_cell("first")],
    )

    assert plan == BacktrackEscKeyPlan(action="noop")
    assert state.primed is False


def test_handle_backtrack_esc_key_primes_when_unprimed():
    state = BacktrackState()

    plan = handle_backtrack_esc_key_state(
        state,
        composer_is_empty=True,
        overlay_open=False,
        thread_id="thread-1",
        transcript_cells=[user_cell("first")],
    )

    assert plan == BacktrackEscKeyPlan(
        action="prime",
        prime=BacktrackPrimePlan(show_hint=True),
    )
    assert state.primed is True
    assert state.base_id == "thread-1"


def test_handle_backtrack_esc_key_requests_open_or_step_when_primed():
    state = BacktrackState(primed=True, base_id="thread-1")

    assert handle_backtrack_esc_key_state(
        state,
        composer_is_empty=True,
        overlay_open=False,
        thread_id="thread-1",
        transcript_cells=[user_cell("first")],
    ) == BacktrackEscKeyPlan(action="open_preview")

    state.overlay_preview_active = True
    assert handle_backtrack_esc_key_state(
        state,
        composer_is_empty=True,
        overlay_open=True,
        thread_id="thread-1",
        transcript_cells=[user_cell("first")],
    ) == BacktrackEscKeyPlan(action="step_backtrack")


def test_handle_backtrack_overlay_event_routes_preview_navigation():
    state = BacktrackState(overlay_preview_active=True, base_id="thread-1")

    assert handle_backtrack_overlay_event_state(state, event_code="esc") == BacktrackOverlayEventPlan(action="step_backtrack")
    assert handle_backtrack_overlay_event_state(state, event_code="left", event_kind="repeat") == BacktrackOverlayEventPlan(action="step_backtrack")
    assert handle_backtrack_overlay_event_state(state, event_code="right") == BacktrackOverlayEventPlan(action="step_forward")
    assert handle_backtrack_overlay_event_state(state, event_code="enter") == BacktrackOverlayEventPlan(action="confirm")
    assert handle_backtrack_overlay_event_state(state, event_code="down") == BacktrackOverlayEventPlan(action="forward")


def test_handle_backtrack_overlay_event_forwards_when_preview_unarmed():
    state = BacktrackState(overlay_preview_active=True, base_id=None)

    assert handle_backtrack_overlay_event_state(state, event_code="esc") == BacktrackOverlayEventPlan(action="forward")
    assert handle_backtrack_overlay_event_state(state, event_code="right") == BacktrackOverlayEventPlan(action="forward")


def test_handle_backtrack_overlay_event_begins_preview_only_on_esc_outside_preview():
    state = BacktrackState(overlay_preview_active=False)

    assert handle_backtrack_overlay_event_state(state, event_code="esc") == BacktrackOverlayEventPlan(action="begin_preview")
    assert handle_backtrack_overlay_event_state(state, event_code="enter") == BacktrackOverlayEventPlan(action="forward")
    assert handle_backtrack_overlay_event_state(state, event_code="esc", event_kind="release") == BacktrackOverlayEventPlan(action="forward")


def test_open_backtrack_preview_state_handles_missing_target_with_info_plan():
    state = BacktrackState(primed=True, base_id="thread-1", nth_user_message=0, overlay_preview_active=True)
    plan = open_backtrack_preview_state(state, [agent_cell("assistant only")])

    assert isinstance(plan, BacktrackPreviewPlan)
    assert plan.action == "no_target"
    assert plan.info_message == NO_PREVIOUS_MESSAGE_TO_EDIT
    assert plan.schedule_frame is True
    assert state == BacktrackState()


def test_open_backtrack_preview_state_opens_preview_and_selects_latest_user():
    state = BacktrackState()
    cells = [user_cell("first"), agent_cell("answer"), user_cell("second")]
    plan = open_backtrack_preview_state(state, cells)

    assert plan.action == "open_preview"
    assert plan.clear_hint is True
    assert plan.schedule_frame is True
    assert plan.highlighted_cell_index == 2
    assert state.overlay_preview_active is True
    assert state.nth_user_message == 1


def test_begin_overlay_backtrack_preview_state_selects_latest_user_or_closes_empty_overlay():
    state = BacktrackState()
    missing = begin_overlay_backtrack_preview_state(state, "thread-1", [agent_cell("assistant only")])
    assert missing.action == "no_target_close_overlay"
    assert missing.info_message == NO_PREVIOUS_MESSAGE_TO_EDIT
    assert missing.schedule_frame is True

    cells = [user_cell("first"), agent_cell("answer"), user_cell("second")]
    plan = begin_overlay_backtrack_preview_state(state, "thread-1", cells)
    assert plan.action == "begin_preview"
    assert plan.schedule_frame is True
    assert plan.highlighted_cell_index == 2
    assert state.primed is True
    assert state.base_id == "thread-1"
    assert state.overlay_preview_active is True
    assert state.nth_user_message == 1
