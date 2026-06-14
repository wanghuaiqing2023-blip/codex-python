"""Protect inline viewport from unmanaged stderr writes.

Rust counterpart: ``codex-rs/tui/src/tui/terminal_stderr.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="tui::terminal_stderr",
    source="codex/codex-rs/tui/src/tui/terminal_stderr.rs",
    status="complete_slice",
)


@dataclass
class StderrState:
    owner_active: bool = False
    saved_stderr: bool = False
    captured_output: list[str] = field(default_factory=list)
    hidden_output: list[str] = field(default_factory=list)


STDERR_STATE = StderrState()


def lock_state(state: StderrState | None = None) -> StderrState:
    return STDERR_STATE if state is None else state


def stderr_targets_stdout_terminal(
    stdout_is_terminal: bool = True,
    stderr_is_terminal: bool = True,
    same_device: bool = True,
) -> bool:
    return bool(stdout_is_terminal and stderr_is_terminal and same_device)


def suppress_locked(state: StderrState) -> None:
    if state.saved_stderr:
        return
    state.saved_stderr = True


def restore_locked(state: StderrState) -> None:
    if not state.saved_stderr:
        return
    state.saved_stderr = False


@dataclass
class TerminalStderrGuard:
    active: bool = False
    state: StderrState = field(default_factory=lock_state)

    @classmethod
    def install(
        cls,
        *,
        state: StderrState | None = None,
        stdout_is_terminal: bool = True,
        stderr_is_terminal: bool = True,
        same_device: bool = True,
        platform: str = "macos",
    ) -> "TerminalStderrGuard":
        target_state = lock_state(state)
        if platform == "macos" and stderr_targets_stdout_terminal(
            stdout_is_terminal,
            stderr_is_terminal,
            same_device,
        ):
            return cls.install_suppression(state=target_state)
        return cls(active=False, state=target_state)

    @classmethod
    def install_suppression(
        cls,
        *,
        state: StderrState | None = None,
    ) -> "TerminalStderrGuard":
        target_state = lock_state(state)
        if target_state.owner_active:
            raise FileExistsError("terminal stderr suppression is already active")
        suppress_locked(target_state)
        target_state.owner_active = True
        return cls(active=True, state=target_state)

    def drop(self) -> None:
        if self.active:
            finish(self.state)
            self.active = False

    def __enter__(self) -> "TerminalStderrGuard":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.drop()


def drop(guard: TerminalStderrGuard) -> None:
    guard.drop()


def pause(state: StderrState | None = None) -> None:
    target_state = lock_state(state)
    if target_state.owner_active:
        restore_locked(target_state)


def resume(state: StderrState | None = None) -> None:
    target_state = lock_state(state)
    if target_state.owner_active:
        suppress_locked(target_state)


def finish(state: StderrState | None = None) -> None:
    target_state = lock_state(state)
    if target_state.owner_active:
        restore_locked(target_state)
        target_state.owner_active = False


@dataclass
class CapturedStderr:
    state: StderrState

    @classmethod
    def start(cls, state: StderrState | None = None) -> "CapturedStderr":
        return cls(lock_state(state))


def write_stderr(message: str, state: StderrState | None = None) -> None:
    target_state = lock_state(state)
    if target_state.saved_stderr:
        target_state.hidden_output.append(message)
    else:
        target_state.captured_output.append(message)


def suppresses_stderr_only_while_terminal_is_owned() -> bool:
    state = StderrState()
    CapturedStderr.start(state)
    guard = TerminalStderrGuard.install_suppression(state=state)
    write_stderr("hidden while active\n", state)
    pause(state)
    write_stderr("visible while paused\n", state)
    resume(state)
    write_stderr("hidden after resume\n", state)
    finish(state)
    write_stderr("visible after finish\n", state)
    guard.drop()

    return (
        "".join(state.captured_output)
        == "visible while paused\nvisible after finish\n"
        and "".join(state.hidden_output)
        == "hidden while active\nhidden after resume\n"
    )


def preserves_stderr_when_already_redirected() -> bool:
    state = StderrState()
    CapturedStderr.start(state)
    guard = TerminalStderrGuard.install(
        state=state,
        stdout_is_terminal=True,
        stderr_is_terminal=False,
        same_device=False,
        platform="macos",
    )
    write_stderr("visible while redirected\n", state)
    guard.drop()
    return "".join(state.captured_output) == "visible while redirected\n"


__all__ = [
    "CapturedStderr",
    "RUST_MODULE",
    "STDERR_STATE",
    "StderrState",
    "TerminalStderrGuard",
    "drop",
    "finish",
    "lock_state",
    "pause",
    "preserves_stderr_when_already_redirected",
    "restore_locked",
    "resume",
    "stderr_targets_stdout_terminal",
    "suppress_locked",
    "suppresses_stderr_only_while_terminal_is_owned",
    "write_stderr",
]
