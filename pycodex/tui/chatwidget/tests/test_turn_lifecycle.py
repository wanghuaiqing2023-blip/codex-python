from pycodex.tui.chatwidget.turn_lifecycle import SleepInhibitor, TurnLifecycleState


def test_start_and_finish_update_running_state():
    state = TurnLifecycleState.new(prevent_idle_sleep=False)

    state.start("now")

    assert state.agent_turn_running is True
    assert state.goal_status_active_turn_started_at == "now"
    assert state.sleep_inhibitor.is_turn_running() is True

    state.finish()

    assert state.agent_turn_running is False
    assert state.goal_status_active_turn_started_at is None
    assert state.sleep_inhibitor.is_turn_running() is False


def test_restore_running_sets_timestamp_only_when_running():
    state = TurnLifecycleState.new(prevent_idle_sleep=True)

    state.restore_running(True, "t1")
    assert state.agent_turn_running is True
    assert state.goal_status_active_turn_started_at == "t1"
    assert state.sleep_inhibitor.is_turn_running() is True

    state.restore_running(False, "t2")
    assert state.agent_turn_running is False
    assert state.goal_status_active_turn_started_at is None
    assert state.sleep_inhibitor.is_turn_running() is False


def test_reset_thread_finishes_and_clears_thread_scoped_state():
    state = TurnLifecycleState.new(False)
    state.start("now")
    state.last_turn_id = "turn"
    state.mark_budget_limited("budget")

    state.reset_thread()

    assert state.agent_turn_running is False
    assert state.goal_status_active_turn_started_at is None
    assert state.last_turn_id is None
    assert state.budget_limited_turn_ids == set()
    assert state.sleep_inhibitor.is_turn_running() is False


def test_set_prevent_idle_sleep_recreates_inhibitor_and_preserves_running_flag():
    state = TurnLifecycleState.new(False)
    state.start("now")
    old_inhibitor = state.sleep_inhibitor

    state.set_prevent_idle_sleep(True)

    assert state.sleep_inhibitor is not old_inhibitor
    assert state.sleep_inhibitor.prevent_idle_sleep is True
    assert state.sleep_inhibitor.is_turn_running() is True


def test_budget_limited_turn_ids_are_consumed():
    state = TurnLifecycleState.new(prevent_idle_sleep=False)

    state.mark_budget_limited("turn-1")

    assert state.take_budget_limited("turn-1") is True
    assert state.take_budget_limited("turn-1") is False
