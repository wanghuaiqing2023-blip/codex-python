"""Rust-derived tests for codex-utils-pty/src/process_group.rs."""

from __future__ import annotations

import errno
import signal

import pytest

import pycodex.utils.pty as pty
from pycodex.utils.pty import process_group

SIGKILL = getattr(signal, "SIGKILL", 9)
SIGTERM = getattr(signal, "SIGTERM", 15)


def _os_error(code: int) -> OSError:
    return OSError(code, "synthetic")


def test_detach_from_tty_falls_back_to_set_process_group_on_eperm(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: codex-utils-pty/src/process_group.rs::detach_from_tty
    # Contract: Unix setsid EPERM falls back to set_process_group; other errors
    # are returned to the caller.
    calls: list[str] = []

    def setsid() -> None:
        raise _os_error(errno.EPERM)

    monkeypatch.setattr(pty.os, "name", "posix", raising=False)
    monkeypatch.setattr(pty.os, "setsid", setsid, raising=False)
    monkeypatch.setattr(process_group, "set_process_group", lambda: calls.append("setpgid"))

    process_group.detach_from_tty()

    assert calls == ["setpgid"]


def test_detach_from_tty_propagates_non_eperm_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: codex-utils-pty/src/process_group.rs::detach_from_tty
    # Contract: Unix setsid failures other than EPERM are returned unchanged.
    monkeypatch.setattr(pty.os, "name", "posix", raising=False)
    monkeypatch.setattr(pty.os, "setsid", lambda: (_ for _ in ()).throw(_os_error(errno.EIO)), raising=False)

    with pytest.raises(OSError) as exc:
        process_group.detach_from_tty()

    assert exc.value.errno == errno.EIO


def test_kill_process_group_by_pid_resolves_pgid_and_sends_sigkill(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: codex-utils-pty/src/process_group.rs::kill_process_group_by_pid
    # Contract: Unix resolves the process group for pid and sends SIGKILL to
    # that group rather than the single pid.
    calls: list[tuple[int, int]] = []

    monkeypatch.setattr(pty.os, "name", "posix", raising=False)
    monkeypatch.setattr(pty.os, "getpgid", lambda pid: 4321, raising=False)
    monkeypatch.setattr(pty.os, "killpg", lambda pgid, sig: calls.append((pgid, sig)), raising=False)

    process_group.kill_process_group_by_pid(1234)

    assert calls == [(4321, SIGKILL)]


@pytest.mark.parametrize("source", ["getpgid", "killpg"])
def test_kill_process_group_by_pid_ignores_missing_process_group(
    monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    # Rust: codex-utils-pty/src/process_group.rs::kill_process_group_by_pid
    # Contract: ESRCH/NotFound while resolving or killing a process group is a
    # best-effort success.
    monkeypatch.setattr(pty.os, "name", "posix", raising=False)

    if source == "getpgid":
        monkeypatch.setattr(
            pty.os,
            "getpgid",
            lambda pid: (_ for _ in ()).throw(ProcessLookupError()),
            raising=False,
        )
        monkeypatch.setattr(
            pty.os,
            "killpg",
            lambda pgid, sig: pytest.fail("killpg should not run"),
            raising=False,
        )
    else:
        monkeypatch.setattr(pty.os, "getpgid", lambda pid: 4321, raising=False)
        monkeypatch.setattr(
            pty.os,
            "killpg",
            lambda pgid, sig: (_ for _ in ()).throw(_os_error(errno.ESRCH)),
            raising=False,
        )

    process_group.kill_process_group_by_pid(1234)


def test_kill_process_group_by_pid_propagates_unexpected_os_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust: codex-utils-pty/src/process_group.rs::kill_process_group_by_pid
    # Contract: non-ESRCH OS errors are returned to the caller.
    monkeypatch.setattr(pty.os, "name", "posix", raising=False)
    monkeypatch.setattr(pty.os, "getpgid", lambda pid: 4321, raising=False)
    monkeypatch.setattr(
        pty.os,
        "killpg",
        lambda pgid, sig: (_ for _ in ()).throw(_os_error(errno.EPERM)),
        raising=False,
    )

    with pytest.raises(OSError) as exc:
        process_group.kill_process_group_by_pid(1234)

    assert exc.value.errno == errno.EPERM


def test_terminate_process_group_reports_delivered_missing_and_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust: codex-utils-pty/src/process_group.rs::terminate_process_group
    # Contract: SIGTERM returns true when delivered, false when the group is
    # gone, and propagates other OS errors.
    calls: list[tuple[int, int]] = []

    monkeypatch.setattr(pty.os, "name", "posix", raising=False)
    monkeypatch.setattr(pty.os, "killpg", lambda pgid, sig: calls.append((pgid, sig)), raising=False)
    assert process_group.terminate_process_group(2222) is True
    assert calls == [(2222, SIGTERM)]

    monkeypatch.setattr(
        pty.os,
        "killpg",
        lambda pgid, sig: (_ for _ in ()).throw(ProcessLookupError()),
        raising=False,
    )
    assert process_group.terminate_process_group(2222) is False

    monkeypatch.setattr(
        pty.os,
        "killpg",
        lambda pgid, sig: (_ for _ in ()).throw(_os_error(errno.EACCES)),
        raising=False,
    )
    with pytest.raises(OSError) as exc:
        process_group.terminate_process_group(2222)
    assert exc.value.errno == errno.EACCES


def test_non_unix_process_group_helpers_are_noops(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: codex-utils-pty/src/process_group.rs non-unix cfg variants
    # Contract: process group helpers are no-ops on non-Unix platforms, and
    # terminate_process_group reports false.
    monkeypatch.setattr(pty.os, "name", "nt", raising=False)
    monkeypatch.setattr(pty.os, "killpg", lambda pgid, sig: pytest.fail("killpg should not run"), raising=False)
    monkeypatch.setattr(pty.os, "setpgid", lambda pid, pgid: pytest.fail("setpgid should not run"), raising=False)

    process_group.detach_from_tty()
    process_group.set_process_group()
    process_group.kill_process_group_by_pid(1234)
    process_group.kill_process_group(1234)
    process_group.kill_child_process_group(type("Child", (), {"pid": 1234})())
    assert process_group.terminate_process_group(1234) is False


def test_set_parent_death_signal_is_noop_off_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: codex-utils-pty/src/process_group.rs::set_parent_death_signal
    # Contract: cfg(not(target_os = "linux")) is a no-op.
    monkeypatch.setattr(pty.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(pty.ctypes, "CDLL", lambda *args, **kwargs: pytest.fail("prctl should not load"))

    process_group.set_parent_death_signal(1234)


def test_set_parent_death_signal_reports_prctl_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: codex-utils-pty/src/process_group.rs::set_parent_death_signal
    # Contract: Linux prctl(PR_SET_PDEATHSIG, SIGTERM) failure returns the OS
    # error before checking the parent pid race.
    class FakePrctl:
        argtypes = None
        restype = None

        def __call__(self, *args):
            return -1

    class FakeLibc:
        prctl = FakePrctl()

    monkeypatch.setattr(pty.sys, "platform", "linux", raising=False)
    monkeypatch.setattr(pty.ctypes, "CDLL", lambda *args, **kwargs: FakeLibc())
    monkeypatch.setattr(pty.ctypes, "get_errno", lambda: errno.EPERM)

    with pytest.raises(OSError) as exc:
        process_group.set_parent_death_signal(1234)

    assert exc.value.errno == errno.EPERM


def test_set_parent_death_signal_race_sends_sigterm(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: codex-utils-pty/src/process_group.rs::set_parent_death_signal
    # Contract: after successful prctl, if getppid() no longer matches the
    # captured parent_pid, the child raises/sends SIGTERM to itself.
    class FakePrctl:
        argtypes = None
        restype = None

        def __call__(self, *args):
            return 0

    class FakeLibc:
        prctl = FakePrctl()

    kills: list[tuple[int, int]] = []
    monkeypatch.setattr(pty.sys, "platform", "linux", raising=False)
    monkeypatch.setattr(pty.ctypes, "CDLL", lambda *args, **kwargs: FakeLibc())
    monkeypatch.setattr(pty.os, "getppid", lambda: 9999)
    monkeypatch.setattr(pty.os, "getpid", lambda: 4444)
    monkeypatch.setattr(pty.os, "kill", lambda pid, sig: kills.append((pid, sig)))

    process_group.set_parent_death_signal(1234)

    assert kills == [(4444, SIGTERM)]
