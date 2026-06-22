"""Rust-derived tests for codex-utils-pty/src/pty.rs."""

from __future__ import annotations

import asyncio
import errno
import os
import sys
import types
from pathlib import Path

import pytest

import pycodex.utils.pty as pty
from pycodex.utils.pty import (
    TerminalSize,
    conpty_supported,
    spawn_process,
    spawn_process_with_inherited_fds,
    spawn_pty_process,
)


def test_conpty_supported_non_windows_true(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: codex-utils-pty/src/pty.rs::conpty_supported
    # Contract: non-Windows builds always report true.
    monkeypatch.setattr(pty.os, "name", "posix", raising=False)

    assert conpty_supported() is True


def test_conpty_supported_windows_uses_version_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: codex-utils-pty/src/pty.rs::conpty_supported
    # Contract: Windows delegates to the ConPTY support probe. The Python
    # dependency-light facade models that as a Windows 10+ version gate.
    class Version:
        def __init__(self, major: int) -> None:
            self.major = major

    monkeypatch.setattr(pty.os, "name", "nt", raising=False)
    monkeypatch.setattr(pty.sys, "getwindowsversion", lambda: Version(10), raising=False)
    assert conpty_supported() is True

    monkeypatch.setattr(pty.sys, "getwindowsversion", lambda: Version(6), raising=False)
    assert conpty_supported() is False


def test_spawn_pty_process_rejects_missing_program_with_rust_message() -> None:
    # Rust: codex-utils-pty/src/pty.rs::spawn_process_with_inherited_fds
    # Contract: an empty program fails before backend selection with
    # "missing program for PTY spawn".
    async def run() -> None:
        with pytest.raises(ValueError, match="missing program for PTY spawn"):
            await spawn_pty_process("", [], Path.cwd(), {})

    asyncio.run(run())


def test_spawn_process_delegates_to_inherited_fd_entry_with_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust: codex-utils-pty/src/pty.rs::spawn_process
    # Contract: spawn_process(...) is a thin facade over
    # spawn_process_with_inherited_fds(..., &[]), preserving all other
    # arguments and the requested TerminalSize.
    calls: list[dict[str, object]] = []
    cwd = Path.cwd()
    size = TerminalSize(rows=33, cols=120)

    async def fake_spawn_with_fds(program, args, cwd_arg, env, arg0=None, size=TerminalSize(), inherited_fds=()):
        calls.append(
            {
                "program": program,
                "args": tuple(args),
                "cwd": cwd_arg,
                "env": dict(env),
                "arg0": arg0,
                "size": size,
                "inherited_fds": tuple(inherited_fds),
            }
        )
        return "spawned"

    monkeypatch.setattr(pty, "spawn_process_with_inherited_fds", fake_spawn_with_fds)

    result = asyncio.run(
        spawn_process(
            "python",
            ["-q"],
            cwd,
            {"PTY_ONLY": "1"},
            arg0="py",
            size=size,
        )
    )

    assert result == "spawned"
    assert calls == [
        {
            "program": "python",
            "args": ("-q",),
            "cwd": cwd,
            "env": {"PTY_ONLY": "1"},
            "arg0": "py",
            "size": size,
            "inherited_fds": (),
        }
    ]


def test_spawn_pty_process_is_crate_root_alias_for_spawn_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust crates/modules: codex-utils-pty/src/lib.rs and src/pty.rs
    # Contract: lib.rs re-exports pty::spawn_process as spawn_pty_process, so
    # the public compatibility name follows the Rust spawn_process facade.
    calls: list[dict[str, object]] = []
    cwd = Path.cwd()
    size = TerminalSize(rows=40, cols=100)

    async def fake_spawn_process(program, args, cwd_arg, env, arg0=None, size=TerminalSize()):
        calls.append(
            {
                "program": program,
                "args": tuple(args),
                "cwd": cwd_arg,
                "env": dict(env),
                "arg0": arg0,
                "size": size,
            }
        )
        return "spawned"

    monkeypatch.setattr(pty, "spawn_process", fake_spawn_process)

    result = asyncio.run(
        spawn_pty_process(
            "python",
            ["-i"],
            cwd,
            {"PTY_ALIAS": "1"},
            arg0="py",
            size=size,
        )
    )

    assert result == "spawned"
    assert calls == [
        {
            "program": "python",
            "args": ("-i",),
            "cwd": cwd,
            "env": {"PTY_ALIAS": "1"},
            "arg0": "py",
            "size": size,
        }
    ]


def test_spawn_with_inherited_fds_rejects_missing_program_before_unix_fd_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust: codex-utils-pty/src/pty.rs::spawn_process_with_inherited_fds
    # Contract: the empty-program check precedes the cfg(unix)
    # inherited-fd dispatch, so even with inherited_fds the error is
    # "missing program for PTY spawn".
    cwd = str(Path.cwd())
    monkeypatch.setattr(pty.os, "name", "posix", raising=False)

    async def run() -> None:
        with pytest.raises(ValueError, match="missing program for PTY spawn"):
            await spawn_process_with_inherited_fds(
                "",
                [],
                cwd,
                {},
                inherited_fds=[3],
            )

    asyncio.run(run())


def test_pty_inherited_fds_are_ignored_on_non_unix(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: codex-utils-pty/src/pty.rs::spawn_process_with_inherited_fds
    # Contract: cfg(not(unix)) ignores inherited_fds and proceeds through the
    # normal portable PTY backend.
    calls: list[tuple[str, tuple[int, ...]]] = []

    async def fake_spawn(program, args, cwd, env, arg0=None, size=TerminalSize()):
        calls.append((program, tuple(args)))
        return "spawned"

    monkeypatch.setattr(pty.os, "name", "nt", raising=False)
    monkeypatch.setattr(pty, "_spawn_pty_process_portable", fake_spawn)

    result = asyncio.run(
        spawn_process_with_inherited_fds(
            "python",
            ["-q"],
            Path.cwd(),
            {},
            inherited_fds=[123, 456],
        )
    )

    assert result == "spawned"
    assert calls == [("python", ("-q",))]


def test_pty_inherited_fds_are_ignored_on_non_windows_non_unix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust: codex-utils-pty/src/pty.rs::spawn_process_with_inherited_fds
    # Contract: the inherited-fd preserving branch is gated by cfg(unix), not
    # by "not Windows"; every cfg(not(unix)) target ignores inherited_fds.
    calls: list[tuple[str, tuple[int, ...]]] = []

    async def fake_spawn(program, args, cwd, env, arg0=None, size=TerminalSize()):
        calls.append((program, tuple(args)))
        return "spawned"

    cwd = str(Path.cwd())
    monkeypatch.setattr(pty.os, "name", "java", raising=False)
    monkeypatch.setattr(pty, "_spawn_pty_process_portable", fake_spawn)

    result = asyncio.run(
        spawn_process_with_inherited_fds(
            "python",
            ["-q"],
            cwd,
            {},
            inherited_fds=[123, 456],
        )
    )

    assert result == "spawned"
    assert calls == [("python", ("-q",))]


def test_portable_pty_arg0_becomes_command_builder_program(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust: codex-utils-pty/src/pty.rs::spawn_process_portable
    # Contract: the portable PTY branch calls
    # CommandBuilder::new(arg0.as_ref().unwrap_or(&program.to_string())).
    # Unlike the Unix pipe/preserving-fd branches, arg0 is therefore the
    # command-builder program name, not a separate argv[0] override.
    calls: list[dict[str, object]] = []
    cwd = Path.cwd()

    async def fake_spawn(
        program,
        args,
        cwd_arg,
        env,
        arg0,
        *,
        stdin_enabled,
        inherited_fds=(),
        missing_program_message="missing program for pipe spawn",
    ):
        calls.append(
            {
                "program": program,
                "args": tuple(args),
                "cwd": cwd_arg,
                "env": dict(env),
                "arg0": arg0,
                "stdin_enabled": stdin_enabled,
                "inherited_fds": tuple(inherited_fds),
                "missing_program_message": missing_program_message,
            }
        )
        return "spawned"

    monkeypatch.setattr(pty, "_spawn_process", fake_spawn)

    result = asyncio.run(
        pty._spawn_pty_process_portable(
            "python",
            ["-q"],
            cwd,
            {"PTY_ARG0": "1"},
            arg0="python-alias",
            size=TerminalSize(rows=27, cols=90),
        )
    )

    assert result == "spawned"
    assert calls == [
        {
            "program": "python-alias",
            "args": ("-q",),
            "cwd": cwd,
            "env": {"PTY_ARG0": "1"},
            "arg0": None,
            "stdin_enabled": True,
            "inherited_fds": (),
            "missing_program_message": "missing program for PTY spawn",
        }
    ]


def test_pty_child_terminator_kills_cached_process_group_before_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust: codex-utils-pty/src/pty.rs::PtyChildTerminator::kill
    # Contract: on Unix, a cached process_group_id is killed first, and the
    # direct child killer is still invoked afterward.
    calls: list[tuple[str, int | None]] = []
    monkeypatch.setattr(pty.os, "name", "posix", raising=False)
    monkeypatch.setattr(
        pty.process_group,
        "kill_process_group",
        lambda pgid: calls.append(("pgid", pgid)),
    )

    terminator = pty._PtyChildTerminator(
        lambda: calls.append(("child", None)),
        process_group_id=4321,
    )

    terminator.kill()

    assert calls == [("pgid", 4321), ("child", None)]


def test_pty_child_terminator_not_found_child_returns_process_group_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust: codex-utils-pty/src/pty.rs::PtyChildTerminator::kill
    # Contract: when the direct child killer reports NotFound, the cached
    # process-group kill result becomes the return result.
    monkeypatch.setattr(pty.os, "name", "posix", raising=False)
    monkeypatch.setattr(pty.process_group, "kill_process_group", lambda pgid: None)

    terminator = pty._PtyChildTerminator(
        lambda: (_ for _ in ()).throw(ProcessLookupError()),
        process_group_id=4321,
    )

    terminator.kill()

    pg_error = OSError(errno.EPERM, "synthetic")
    monkeypatch.setattr(
        pty.process_group,
        "kill_process_group",
        lambda pgid: (_ for _ in ()).throw(pg_error),
    )
    terminator = pty._PtyChildTerminator(
        lambda: (_ for _ in ()).throw(ProcessLookupError()),
        process_group_id=4321,
    )

    with pytest.raises(OSError) as exc:
        terminator.kill()
    assert exc.value is pg_error


def test_pty_child_terminator_child_error_is_ignored_after_group_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust: codex-utils-pty/src/pty.rs::PtyChildTerminator::kill
    # Contract: process_group_kill_result.or(Err(child_err)) returns Ok when
    # the cached process-group kill succeeded, even if direct child kill fails.
    monkeypatch.setattr(pty.os, "name", "posix", raising=False)
    monkeypatch.setattr(pty.process_group, "kill_process_group", lambda pgid: None)

    terminator = pty._PtyChildTerminator(
        lambda: (_ for _ in ()).throw(OSError(errno.EIO, "child")),
        process_group_id=4321,
    )

    terminator.kill()


def test_pty_child_terminator_without_process_group_uses_direct_child_killer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust: codex-utils-pty/src/pty.rs::PtyChildTerminator::kill
    # Contract: without a cached process_group_id, kill delegates directly to
    # the portable-pty child killer and propagates its result.
    calls: list[str] = []
    monkeypatch.setattr(pty.os, "name", "posix", raising=False)
    monkeypatch.setattr(
        pty.process_group,
        "kill_process_group",
        lambda pgid: pytest.fail("process group should not be killed"),
    )

    pty._PtyChildTerminator(lambda: calls.append("child")).kill()

    assert calls == ["child"]


def test_pty_inherited_fds_on_unix_delegate_to_native_preserving_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust: codex-utils-pty/src/pty.rs::spawn_process_preserving_fds
    # Contract: on Unix, non-empty inherited_fds dispatch to the native
    # openpty/pre_exec branch instead of the portable PTY backend.
    calls: list[dict[str, object]] = []
    cwd = Path.cwd()
    size = TerminalSize(rows=41, cols=111)

    async def fake_preserving(program, args, cwd_arg, env, arg0=None, size=TerminalSize(), inherited_fds=()):
        calls.append(
            {
                "program": program,
                "args": tuple(args),
                "cwd": cwd_arg,
                "env": dict(env),
                "arg0": arg0,
                "size": size,
                "inherited_fds": tuple(inherited_fds),
            }
        )
        return "spawned"

    monkeypatch.setattr(pty.os, "name", "posix", raising=False)
    monkeypatch.setattr(pty, "_spawn_pty_process_preserving_fds", fake_preserving)

    result = asyncio.run(
        spawn_process_with_inherited_fds(
            "python",
            ["-q"],
            cwd,
            {"PTY_FD": "1"},
            arg0="py",
            size=size,
            inherited_fds=[3, 4],
        )
    )

    assert result == "spawned"
    assert calls == [
        {
            "program": "python",
            "args": ("-q",),
            "cwd": cwd,
            "env": {"PTY_FD": "1"},
            "arg0": "py",
            "size": size,
            "inherited_fds": (3, 4),
        }
    ]


def test_open_unix_pty_sets_cloexec_and_initial_size(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: codex-utils-pty/src/pty.rs::open_unix_pty
    # Contract: openpty returns master/slave fds, sets FD_CLOEXEC on both, and
    # applies the requested initial terminal size.
    calls: list[tuple[str, int, TerminalSize | None]] = []
    size = TerminalSize(rows=31, cols=101)

    monkeypatch.setattr(pty.os, "openpty", lambda: (10, 11), raising=False)
    monkeypatch.setattr(pty, "_set_cloexec", lambda fd: calls.append(("cloexec", fd, None)))
    monkeypatch.setattr(pty, "_resize_raw_pty", lambda fd, size_arg: calls.append(("resize", fd, size_arg)))

    assert pty._open_unix_pty(size) == (10, 11)
    assert calls == [
        ("cloexec", 10, None),
        ("cloexec", 11, None),
        ("resize", 10, size),
    ]


def test_open_unix_pty_error_message_matches_rust_context(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: codex-utils-pty/src/pty.rs::open_unix_pty
    # Contract: openpty failures are reported with "failed to openpty".
    monkeypatch.setattr(
        pty.os,
        "openpty",
        lambda: (_ for _ in ()).throw(OSError(errno.ENOSYS, "missing")),
        raising=False,
    )

    with pytest.raises(OSError, match="failed to openpty"):
        pty._open_unix_pty(TerminalSize())


def test_close_inherited_fds_except_preserves_stdio_requested_and_cloexec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust: codex-utils-pty/src/pty.rs::close_inherited_fds_except
    # Contract: /dev/fd entries <= 2, explicitly preserved fds, and CLOEXEC
    # fds are left alone; other non-CLOEXEC descriptors are closed.
    fake_fcntl = types.SimpleNamespace(F_GETFD=1, F_SETFD=2, FD_CLOEXEC=0x1)
    flags = {
        3: 0,
        4: fake_fcntl.FD_CLOEXEC,
        5: 0,
        7: 0,
    }
    closed: list[int] = []

    def fake_fcntl_call(fd: int, cmd: int, value: int | None = None) -> int:
        assert cmd == fake_fcntl.F_GETFD
        if fd == 7:
            raise OSError(errno.EBADF, "bad fd")
        return flags[fd]

    fake_fcntl.fcntl = fake_fcntl_call
    monkeypatch.setitem(sys.modules, "fcntl", fake_fcntl)
    monkeypatch.setattr(pty.os, "listdir", lambda path: ["0", "1", "2", "3", "4", "5", "7", "x"])
    monkeypatch.setattr(pty.os, "close", lambda fd: closed.append(fd))

    pty._close_inherited_fds_except([5])

    assert closed == [3]


def test_preserving_fds_spawn_installs_raw_pid_terminator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust: codex-utils-pty/src/pty.rs::RawPidTerminator
    # Contract: the Unix inherited-fd preserving branch installs a raw-PID
    # process-group terminator, so termination kills the spawned child's PGID
    # directly instead of using the portable-pty child killer path.
    class FakeHandle:
        def __init__(self, fd: int) -> None:
            self.fd = fd
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        pid = 7654
        returncode = None

        async def wait(self) -> int:
            self.returncode = 0
            return 0

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess()

    async def fake_read_pty_fd(master_fd, queue):
        return None

    killed: list[int] = []
    closed: list[int] = []

    monkeypatch.setattr(pty, "_open_unix_pty", lambda size: (10, 11))
    monkeypatch.setattr(pty.os, "dup", lambda fd: fd + 100)
    monkeypatch.setattr(pty.os, "fdopen", lambda fd, mode, buffering=0: FakeHandle(fd))
    monkeypatch.setattr(pty.os, "close", lambda fd: closed.append(fd))
    monkeypatch.setattr(pty.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(pty, "_read_pty_fd", fake_read_pty_fd)
    monkeypatch.setattr(pty, "_wait_process", lambda process: process.wait())
    monkeypatch.setattr(pty.process_group, "kill_process_group", lambda pgid: killed.append(pgid))

    async def run() -> None:
        spawned = await pty._spawn_pty_process_preserving_fds(
            "python",
            ["-q"],
            Path.cwd(),
            {"PTY_RAW_PID": "1"},
            inherited_fds=[3],
        )

        spawned.session.request_terminate()
        assert killed == [7654]
        assert closed == []

        await spawned.exit_rx
        await asyncio.sleep(0)
        assert closed == [10]

    asyncio.run(run())
