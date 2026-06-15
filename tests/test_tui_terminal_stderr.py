from pycodex.tui.tui.terminal_stderr import (
    StderrState,
    TerminalStderrGuard,
    finish,
    pause,
    preserves_stderr_when_already_redirected,
    resume,
    restore_locked,
    stderr_targets_stdout_terminal,
    suppress_locked,
    suppresses_stderr_only_while_terminal_is_owned,
    write_stderr,
)


def test_suppresses_stderr_only_while_terminal_is_owned_matches_rust() -> None:
    # Rust: tui/terminal_stderr.rs suppresses_stderr_only_while_terminal_is_owned
    assert suppresses_stderr_only_while_terminal_is_owned()


def test_preserves_stderr_when_already_redirected_matches_rust() -> None:
    # Rust: preserves_stderr_when_already_redirected
    assert preserves_stderr_when_already_redirected()


def test_install_non_macos_or_redirected_is_inactive_noop() -> None:
    state = StderrState()

    guard = TerminalStderrGuard.install(state=state, platform="linux")
    redirected = TerminalStderrGuard.install(
        state=state,
        stdout_is_terminal=True,
        stderr_is_terminal=False,
        same_device=False,
        platform="macos",
    )

    assert not guard.active
    assert not redirected.active
    assert not state.owner_active
    assert not state.saved_stderr


def test_install_suppression_rejects_existing_owner() -> None:
    state = StderrState()
    TerminalStderrGuard.install_suppression(state=state)

    try:
        TerminalStderrGuard.install_suppression(state=state)
    except FileExistsError as exc:
        assert "already active" in str(exc)
    else:
        raise AssertionError("expected FileExistsError")


def test_pause_resume_finish_state_transitions_are_idempotent() -> None:
    state = StderrState()
    TerminalStderrGuard.install_suppression(state=state)

    assert state.owner_active
    assert state.saved_stderr

    pause(state)
    pause(state)
    assert state.owner_active
    assert not state.saved_stderr

    resume(state)
    resume(state)
    assert state.owner_active
    assert state.saved_stderr

    finish(state)
    finish(state)
    assert not state.owner_active
    assert not state.saved_stderr


def test_pause_resume_without_owner_are_noops_and_keep_stderr_visible() -> None:
    # Rust pause/resume return Ok(()) and do nothing when no guard owns stderr.
    state = StderrState()

    pause(state)
    write_stderr("visible before owner\n", state)
    resume(state)
    write_stderr("still visible\n", state)

    assert not state.owner_active
    assert not state.saved_stderr
    assert state.captured_output == ["visible before owner\n", "still visible\n"]
    assert state.hidden_output == []


def test_suppress_and_restore_locked_are_idempotent() -> None:
    state = StderrState()

    suppress_locked(state)
    suppress_locked(state)
    assert state.saved_stderr

    restore_locked(state)
    restore_locked(state)
    assert not state.saved_stderr


def test_stderr_target_detection_requires_two_terminals_same_device() -> None:
    assert stderr_targets_stdout_terminal(True, True, True)
    assert not stderr_targets_stdout_terminal(False, True, True)
    assert not stderr_targets_stdout_terminal(True, False, True)
    assert not stderr_targets_stdout_terminal(True, True, False)


def test_guard_drop_finishes_active_suppression_once() -> None:
    state = StderrState()
    guard = TerminalStderrGuard.install_suppression(state=state)
    write_stderr("hidden", state)

    guard.drop()
    guard.drop()
    write_stderr("visible", state)

    assert not state.owner_active
    assert not state.saved_stderr
    assert state.hidden_output == ["hidden"]
    assert state.captured_output == ["visible"]


def test_context_manager_drop_restores_visible_stderr_after_scope() -> None:
    # Rust Drop for TerminalStderrGuard calls finish once when active.
    state = StderrState()

    with TerminalStderrGuard.install_suppression(state=state):
        write_stderr("hidden in scope\n", state)

    write_stderr("visible after scope\n", state)

    assert not state.owner_active
    assert not state.saved_stderr
    assert state.hidden_output == ["hidden in scope\n"]
    assert state.captured_output == ["visible after scope\n"]
