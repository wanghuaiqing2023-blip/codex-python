import asyncio

from pycodex.tui.app import (
    App,
    AppExitInfo,
    AppRunControl,
    AutoReviewMode,
    ExitReason,
    RuntimePermissionProfileOverride,
    active_turn_steer_race,
    collab_receiver_thread_ids,
    default_exec_approval_decisions,
    errors_for_cwd,
    managed_filesystem_sandbox_is_restricted,
    rollout_path_is_resumable,
    session_summary,
)


def test_app_root_helpers_match_rust_module_contracts(tmp_path):
    # Rust: codex-tui::app root helpers.
    rollout_path = tmp_path / "turns.jsonl"
    rollout_path.write_text("{}\n", encoding="utf-8")
    assert collab_receiver_thread_ids([{"thread_id": "a"}, {"id": "b"}, {}]) == {"a", "b"}
    assert default_exec_approval_decisions()["approved"] == "approved"
    assert AutoReviewMode("workspace").permission_profile() == "workspace-write"
    assert managed_filesystem_sandbox_is_restricted({"sandbox_mode": "read-only"})
    assert not managed_filesystem_sandbox_is_restricted({"sandbox_mode": "danger-full-access"})
    assert rollout_path_is_resumable(rollout_path)
    assert not rollout_path_is_resumable(tmp_path / "missing.jsonl")
    assert not rollout_path_is_resumable(tmp_path)
    assert errors_for_cwd(tmp_path) == []


def test_app_root_dtos_and_runtime_state():
    # Rust: AppExitInfo::fatal, RuntimePermissionProfileOverride::from_config, session summary.
    fatal = AppExitInfo.fatal("boom")
    assert fatal.reason is ExitReason.Fatal
    assert fatal.message == "boom"

    override = RuntimePermissionProfileOverride.from_config(
        {"permission_profile": "workspace", "sandbox_mode": "workspace-write", "approval_policy": "on-request"}
    )
    assert override.sandbox_mode == "workspace-write"

    summary = session_summary({"thread_id": "tid", "title": "Title", "cwd": "/tmp", "rollout_path": "r.jsonl"})
    assert summary.thread_id == "tid"
    assert summary.title == "Title"


def test_app_event_loop_facade_handles_exit_and_render():
    # Rust: App::handle_tui_event and render frame boundary.
    app = App(chat_widget={"kind": "chat"})
    assert asyncio.run(app.handle_tui_event({"type": "draw"})) is AppRunControl.Continue
    assert asyncio.run(app.handle_tui_event({"type": "quit"})) is AppRunControl.Exit
    assert asyncio.run(app.run()).reason is ExitReason.UserRequested
    app.show_shutdown_feedback()
    assert app.shutdown_feedback_visible
    assert app.render_chat_widget_frame()["frame"] == 1


def test_active_turn_steer_race_classification():
    assert active_turn_steer_race(None, "t").name == "NotFound"
    assert active_turn_steer_race({"id": "x"}, "t").name == "NotFound"
    assert active_turn_steer_race({"id": "t", "steerable": False}, "t").name == "NotSteerable"
    assert active_turn_steer_race({"id": "t", "steerable": True}, "t").name == "Accepted"
