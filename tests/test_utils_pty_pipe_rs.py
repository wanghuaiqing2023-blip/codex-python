"""Rust-derived tests for codex-utils-pty/src/pipe.rs."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import pytest

import pycodex.utils.pty as pty
from pycodex.utils.pty import (
    SpawnedProcess,
    spawn_pipe_process,
    spawn_pipe_process_no_stdin,
    spawn_pipe_process_no_stdin_with_inherited_fds,
)


async def _collect_queue(queue: asyncio.Queue[bytes]) -> bytes:
    chunks: list[bytes] = []
    while True:
        try:
            chunk = await asyncio.wait_for(queue.get(), timeout=0.05)
        except TimeoutError:
            break
        chunks.append(chunk)
    return b"".join(chunks)


async def _wait_and_collect(spawned: SpawnedProcess, timeout: float = 5.0) -> tuple[int, bytes, bytes]:
    code = await asyncio.wait_for(spawned.exit_rx, timeout=timeout)
    stdout = await _collect_queue(spawned.stdout_rx)
    stderr = await _collect_queue(spawned.stderr_rx)
    return code, stdout, stderr


def _python_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(extra or {})
    for key in ("SystemRoot", "WINDIR", "PATH"):
        if key in os.environ:
            env.setdefault(key, os.environ[key])
    return env


def test_pipe_spawn_rejects_missing_program() -> None:
    # Rust: codex-utils-pty/src/pipe.rs::spawn_process_with_stdin_mode
    # Contract: an empty program fails before command construction with the
    # message "missing program for pipe spawn".
    async def run() -> None:
        with pytest.raises(ValueError, match="missing program for pipe spawn"):
            await spawn_pipe_process("", [], Path.cwd(), {})

    asyncio.run(run())


def test_pipe_process_round_trips_stdin() -> None:
    # Rust test: pipe_process_round_trips_stdin
    # Contract: spawn_process uses piped stdin and forwards writer_sender bytes
    # to the child process.
    async def run() -> tuple[int, bytes, bytes]:
        spawned = await spawn_pipe_process(
            sys.executable,
            ["-u", "-c", "import sys; print(sys.stdin.readline().strip())"],
            Path.cwd(),
            _python_env(),
        )
        writer = spawned.session.writer_sender()
        await writer.send(b"roundtrip\n")
        spawned.session.close_stdin()
        return await _wait_and_collect(spawned)

    code, stdout, stderr = asyncio.run(run())

    assert code == 0
    assert b"roundtrip" in stdout
    assert stderr == b""


def test_pipe_no_stdin_uses_null_stdin() -> None:
    # Rust: codex-utils-pty/src/pipe.rs::spawn_process_no_stdin
    # Contract: no-stdin pipe spawning connects child stdin to null, so reads
    # complete immediately with EOF.
    async def run() -> tuple[int, bytes, bytes]:
        spawned = await spawn_pipe_process_no_stdin(
            sys.executable,
            ["-u", "-c", "import sys; data=sys.stdin.read(); print('stdin-len=' + str(len(data)))"],
            Path.cwd(),
            _python_env(),
        )
        return await _wait_and_collect(spawned)

    code, stdout, stderr = asyncio.run(run())

    assert code == 0
    assert stdout.strip() == b"stdin-len=0"
    assert stderr == b""


def test_pipe_spawn_env_clear_uses_only_supplied_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: codex-utils-pty/src/pipe.rs::spawn_process_with_stdin_mode
    # Contract: Command::env_clear is applied before inserting the supplied
    # env map, so unrelated parent environment variables do not leak.
    monkeypatch.setenv("PYCODEX_PIPE_SHOULD_NOT_LEAK", "leaked")

    script = (
        "import os; "
        "print(os.getenv('PYCODEX_PIPE_ONLY')); "
        "print(os.getenv('PYCODEX_PIPE_SHOULD_NOT_LEAK'))"
    )

    async def run() -> tuple[int, bytes, bytes]:
        spawned = await spawn_pipe_process_no_stdin(
            sys.executable,
            ["-u", "-c", script],
            Path.cwd(),
            _python_env({"PYCODEX_PIPE_ONLY": "present"}),
        )
        return await _wait_and_collect(spawned)

    code, stdout, stderr = asyncio.run(run())

    assert code == 0
    assert stdout.splitlines() == [b"present", b"None"]
    assert stderr == b""


def test_pipe_process_exposes_split_stdout_and_stderr() -> None:
    # Rust test: pipe_process_can_expose_split_stdout_and_stderr
    # Contract: pipe spawning returns separate stdout and stderr receivers.
    script = "import sys; print('split-out'); print('split-err', file=sys.stderr)"

    async def run() -> tuple[int, bytes, bytes]:
        spawned = await spawn_pipe_process_no_stdin(
            sys.executable,
            ["-u", "-c", script],
            Path.cwd(),
            _python_env(),
        )
        return await _wait_and_collect(spawned)

    code, stdout, stderr = asyncio.run(run())

    assert code == 0
    assert stdout == (b"split-out\r\n" if os.name == "nt" else b"split-out\n")
    assert stderr == (b"split-err\r\n" if os.name == "nt" else b"split-err\n")


@pytest.mark.skipif(os.name == "nt", reason="Unix inherited fd preservation is cfg(unix) in Rust")
def test_pipe_spawn_no_stdin_can_preserve_inherited_fds() -> None:
    # Rust test: pipe_spawn_no_stdin_can_preserve_inherited_fds
    # Contract: on Unix, spawn_process_no_stdin_with_inherited_fds preserves
    # selected file descriptors across exec while keeping stdin closed.
    read_fd, write_fd = os.pipe()
    try:
        async def run() -> int:
            spawned = await spawn_pipe_process_no_stdin_with_inherited_fds(
                sys.executable,
                [
                    "-u",
                    "-c",
                    "import os; os.write(int(os.environ['PRESERVED_FD']), b'__pipe_preserved__')",
                ],
                Path.cwd(),
                _python_env({"PRESERVED_FD": str(write_fd)}),
                inherited_fds=[write_fd],
            )
            return await asyncio.wait_for(spawned.exit_rx, timeout=5.0)

        code = asyncio.run(run())
        os.close(write_fd)
        write_fd = -1
        output = os.read(read_fd, 1024)
    finally:
        os.close(read_fd)
        if write_fd != -1:
            os.close(write_fd)

    assert code == 0
    assert output == b"__pipe_preserved__"


def test_pipe_linux_preexec_detaches_then_sets_parent_death_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: codex-utils-pty/src/pipe.rs::spawn_process_with_stdin_mode
    # Contract: Linux pipe spawning installs a pre_exec hook that detaches from
    # the parent TTY before setting the parent-death signal with the captured
    # parent pid.
    captured: dict[str, Any] = {}
    calls: list[tuple[str, int | None]] = []

    class FakeStream:
        async def read(self, _limit: int) -> bytes:
            return b""

    class FakeProcess:
        pid = 777
        returncode: int | None = None
        stdin = None
        stdout = FakeStream()
        stderr = FakeStream()

        async def wait(self) -> int:
            self.returncode = 0
            return 0

        def kill(self) -> None:
            self.returncode = -9

    async def fake_create_subprocess_exec(*argv: str, **kwargs: Any) -> FakeProcess:
        captured["argv"] = argv
        captured.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(pty.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(pty.os, "name", "posix")
    monkeypatch.setattr(pty.sys, "platform", "linux")
    monkeypatch.setattr(pty.os, "getpid", lambda: 1234)
    monkeypatch.setattr(pty, "Path", lambda value: value)
    monkeypatch.setattr(pty.process_group, "detach_from_tty", lambda: calls.append(("detach", None)))
    monkeypatch.setattr(
        pty.process_group,
        "set_parent_death_signal",
        lambda parent_pid: calls.append(("pdeath", int(parent_pid))),
    )

    async def run() -> SpawnedProcess:
        spawned = await spawn_pipe_process_no_stdin_with_inherited_fds(
            "python",
            ["-c", "pass"],
            ".",
            {},
            inherited_fds=[9],
        )
        await spawned.exit_rx
        return spawned

    spawned = asyncio.run(run())

    assert spawned.session.exit_code() == 0
    assert captured["argv"] == ("python", "-c", "pass")
    assert captured["stdin"] is pty.asyncio.subprocess.DEVNULL
    assert captured["pass_fds"] == (9,)
    assert captured["preexec_fn"] is not None

    captured["preexec_fn"]()

    assert calls == [("detach", None), ("pdeath", 1234)]
