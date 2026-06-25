from __future__ import annotations

import asyncio

from pycodex.tui.app.session_lifecycle import (
    AgentPickerItemPlan,
    SessionLifecyclePlan,
    attach_live_thread_for_selection,
    can_fallback_from_include_turns_error,
    closed_state_for_thread_read_error,
    is_terminal_thread_read_error,
    open_agent_picker,
    refresh_agent_picker_thread_liveness,
    resume_target_session,
    select_agent_thread,
    start_fresh_session_with_summary_hint,
)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_terminal_thread_read_error_detection_matches_not_loaded_errors() -> None:
    err = RuntimeError(
        "thread/read failed during TUI session lookup: thread/read failed: thread not loaded: thr_123"
    )

    assert is_terminal_thread_read_error(err)


def test_terminal_thread_read_error_detection_ignores_transient_failures() -> None:
    err = RuntimeError(
        "thread/read failed during TUI session lookup: thread/read transport error: broken pipe"
    )

    assert not is_terminal_thread_read_error(err)


def test_closed_state_for_thread_read_error_preserves_live_state_without_cache_on_transient_error() -> None:
    err = RuntimeError(
        "thread/read failed during TUI session lookup: thread/read transport error: broken pipe"
    )

    assert not closed_state_for_thread_read_error(err, None)
    assert closed_state_for_thread_read_error(err, True)


def test_closed_state_for_thread_read_error_marks_terminal_uncached_threads_closed() -> None:
    err = RuntimeError(
        "thread/read failed during TUI session lookup: thread/read failed: thread not loaded: thr_123"
    )

    assert closed_state_for_thread_read_error(err, None)


def test_include_turns_fallback_detection_handles_unmaterialized_and_ephemeral_threads() -> None:
    unmaterialized = RuntimeError(
        "thread/read failed during TUI session lookup: thread/read failed: thread thr_123 is not materialized yet; includeTurns is unavailable before first user message"
    )
    ephemeral = RuntimeError(
        "thread/read failed during TUI session lookup: thread/read failed: ephemeral threads do not support includeTurns"
    )
    transient = RuntimeError("thread/read transport error: broken pipe")

    assert can_fallback_from_include_turns_error(unmaterialized)
    assert can_fallback_from_include_turns_error(ephemeral)
    assert not can_fallback_from_include_turns_error(transient)


def test_agent_picker_and_liveness_are_semantic_plans() -> None:
    entries = [{"thread_id": "t1", "agent_nickname": "Builder", "agent_role": "coder", "is_closed": False}]
    picker = run(open_agent_picker(entries, active_thread_id="t1", primary_thread_id="p"))
    assert picker.action == "show_agent_picker"
    assert picker.items == (AgentPickerItemPlan("t1", "Builder (coder)", "t1", is_current=True),)

    terminal = RuntimeError("thread/read failed: thread not loaded: t2")
    removed = run(refresh_agent_picker_thread_liveness("t2", read_error=terminal, has_replay_channel=False))
    assert removed.action == "remove_agent_picker_thread"

    transient = RuntimeError("broken pipe")
    upsert = run(refresh_agent_picker_thread_liveness("t3", {"is_closed": True}, read_error=transient))
    assert upsert.action == "upsert_agent_picker_thread"
    assert ("is_closed", True) in upsert.updates


def test_attach_select_start_and_resume_are_semantic_lifecycle_plans() -> None:
    attached = run(attach_live_thread_for_selection("t1", resume_result={"session": "s"}))
    assert attached.action == "attach_live_thread"
    assert attached.live_attached is True

    unavailable = run(attach_live_thread_for_selection("t2", resume_error=RuntimeError("no"), read_result={"turns": []}))
    assert unavailable.action == "attach_live_thread_unavailable"
    assert unavailable.live_attached is False

    selected = run(select_agent_thread("t1", active_thread_id="t0", attach_plan=attached))
    assert selected.action == "select_agent_thread"
    assert ("replace_chat_widget", True) in selected.updates

    fresh_failed = run(start_fresh_session_with_summary_hint(start_error="offline"))
    assert fresh_failed.messages == ("Failed to start a fresh session through the app server: offline",)
    assert fresh_failed.schedule_frame

    resumed = run(resume_target_session({"thread_id": "t9"}, summary="resume hint"))
    assert resumed.action == "resume_target_session"
    assert resumed.messages == ("resume hint",)

    same = run(resume_target_session("t9", same_thread=True))
    assert same.action == "resume_same_thread_ignored"
    assert same.schedule_frame
