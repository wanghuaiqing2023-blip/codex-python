"""Rust-derived tests for codex-exec-server/src/local_process.rs."""

from __future__ import annotations

import asyncio
import os
import sys
import textwrap

import pycodex.exec_server as exec_server
from pycodex.app_server.error_code import INVALID_PARAMS_ERROR_CODE, INVALID_REQUEST_ERROR_CODE
from pycodex.exec_server import (
    ByteChunk,
    ExecEnvPolicy,
    ExecOutputStream,
    ExecParams,
    ExecProcessEvent,
    ExecResponse,
    LocalProcess,
    ProcessId,
    ProcessOutputChunk,
    ReadParams,
    ReadResponse,
    TerminateParams,
    TerminateResponse,
    WriteParams,
    WriteResponse,
    WriteStatus,
    _LocalPipeChildProcess,
    _local_process_maybe_mark_closed,
    child_env,
    shell_environment_policy,
)
from pycodex.protocol import ShellEnvironmentPolicy, ShellEnvironmentPolicyInherit
from pycodex.protocol.shell_environment import WINDOWS_DEFAULT_PATHEXT


def _exec_params(env: dict[str, str]) -> ExecParams:
    return ExecParams(
        process_id=ProcessId.new("env-test"),
        argv=["true"],
        cwd="/tmp",
        env_policy=None,
        env=env,
        tty=False,
    )


def test_child_env_defaults_to_exact_env():
    # Rust: codex-exec-server/src/local_process.rs
    # Test: child_env_defaults_to_exact_env
    # Contract: absent env_policy, child_env returns exactly params.env.
    params = _exec_params({"ONLY_THIS": "1"})

    assert child_env(params) == {"ONLY_THIS": "1"}


def test_child_env_applies_policy_then_overlay():
    # Rust: codex-exec-server/src/local_process.rs
    # Test: child_env_applies_policy_then_overlay
    # Contract: shell_environment::create_env runs first, then params.env
    # overlays policy-set values.
    params = _exec_params({"OVERLAY": "overlay", "POLICY_SET": "overlay-wins"})
    params = ExecParams(
        process_id=params.process_id,
        argv=params.argv,
        cwd=params.cwd,
        env=params.env,
        tty=params.tty,
        env_policy=ExecEnvPolicy(
            inherit=ShellEnvironmentPolicyInherit.NONE,
            ignore_default_excludes=True,
            exclude=[],
            set={"POLICY_SET": "policy"},
            include_only=[],
        ),
    )

    expected = {"OVERLAY": "overlay", "POLICY_SET": "overlay-wins"}
    if sys.platform == "win32":
        expected["PATHEXT"] = WINDOWS_DEFAULT_PATHEXT

    assert child_env(params) == expected


def test_shell_environment_policy_projection_matches_rust_fields():
    # Rust: local_process.rs::shell_environment_policy
    # Contract: ExecEnvPolicy projects to ShellEnvironmentPolicy with
    # case-insensitive pattern strings and use_profile=false.
    policy = shell_environment_policy(
        ExecEnvPolicy(
            inherit=ShellEnvironmentPolicyInherit.CORE,
            ignore_default_excludes=False,
            exclude=["*KEY*"],
            set={"A": "B"},
            include_only=["PATH"],
        )
    )

    assert policy == ShellEnvironmentPolicy(
        inherit=ShellEnvironmentPolicyInherit.CORE,
        ignore_default_excludes=False,
        exclude=("*KEY*",),
        set_values={"A": "B"},
        include_only=("PATH",),
        use_profile=False,
    )


def test_start_process_rejects_empty_argv_before_tracking_process():
    # Rust: local_process.rs::LocalProcess::start_process
    # Contract: empty argv returns invalid_params and does not insert a process
    # entry.
    backend = LocalProcess.new(None)
    params = ExecParams(
        process_id=ProcessId.new("empty"),
        argv=[],
        cwd="/tmp",
        env={},
        tty=False,
    )

    result = asyncio.run(backend.exec(params))

    assert result.code == INVALID_PARAMS_ERROR_CODE
    assert result.message == "argv must not be empty"
    assert backend.processes == {}


def test_start_process_rejects_duplicate_process_ids():
    # Rust: local_process.rs::LocalProcess::start_process and handler test
    # duplicate_process_ids_allow_only_one_successful_start
    # Contract: any existing process entry blocks starting the same process id.
    backend = LocalProcess.new(None)
    backend.insert_running_process_for_tests("proc-1")
    params = ExecParams(
        process_id=ProcessId.new("proc-1"),
        argv=["true"],
        cwd="/tmp",
        env={},
        tty=False,
    )

    result = asyncio.run(backend.exec(params))

    assert result.code == INVALID_REQUEST_ERROR_CODE
    assert result.message == "process proc-1 already exists"


def test_start_process_spawn_failure_removes_starting_entry():
    # Rust: local_process.rs::LocalProcess::start_process
    # Contract: spawn failure removes the temporary Starting entry and maps the
    # spawn error to internal_error.
    async def fail_spawn(_params, _env):
        raise OSError("spawn failed")

    backend = LocalProcess(None, spawn_process=fail_spawn)
    params = _exec_params({})
    params = ExecParams(
        process_id=ProcessId.new("spawn-fail"),
        argv=params.argv,
        cwd=params.cwd,
        env=params.env,
        tty=False,
    )

    result = asyncio.run(backend.exec(params))

    assert result.code == -32603
    assert result.message == "spawn failed"
    assert backend.processes == {}


def test_start_process_success_inserts_running_process_with_env_overlay():
    # Rust: local_process.rs::LocalProcess::start_process
    # Contract: successful spawn creates a running entry configured from params
    # and receives child_env output.
    calls = []

    async def spawn(params, env):
        calls.append((params.process_id, env))
        return None

    backend = LocalProcess(None, spawn_process=spawn)
    params = ExecParams(
        process_id=ProcessId.new("spawn-ok"),
        argv=["cmd"],
        cwd="/tmp",
        env={"OVERLAY": "request"},
        tty=True,
        pipe_stdin=True,
        env_policy=ExecEnvPolicy(
            inherit=ShellEnvironmentPolicyInherit.NONE,
            ignore_default_excludes=True,
            set={"OVERLAY": "policy"},
        ),
    )

    result = asyncio.run(backend.exec(params))

    assert result == ExecResponse(process_id=ProcessId.new("spawn-ok"))
    expected_env = {"OVERLAY": "request"}
    if sys.platform == "win32":
        expected_env["PATHEXT"] = WINDOWS_DEFAULT_PATHEXT
    assert calls == [(ProcessId.new("spawn-ok"), expected_env)]
    process = backend.processes[ProcessId.new("spawn-ok")]
    assert process.tty is True
    assert process.pipe_stdin is True


def test_start_process_spawns_real_pipe_process_and_collects_output(tmp_path):
    # Rust: local_process.rs::LocalProcess::start_process, stream_output,
    # watch_exit, and maybe_emit_closed.
    # Contract: non-TTY pipe process execution captures stdout/stderr chunks,
    # records exit, and reports closed after both output streams finish.
    script = textwrap.dedent(
        """
        import os
        import sys
        sys.stdout.buffer.write(("out:" + os.environ["PYCODEX_LOCAL_PROCESS_TEST"]).encode())
        sys.stdout.buffer.flush()
        sys.stderr.buffer.write(b"err:stream")
        sys.stderr.buffer.flush()
        raise SystemExit(7)
        """
    )

    async def run():
        backend = LocalProcess.new(None)
        env = os.environ.copy()
        env["PYCODEX_LOCAL_PROCESS_TEST"] = "real-env"
        process_id = ProcessId.new("real-proc")
        start = await backend.exec(
            ExecParams(
                process_id=process_id,
                argv=[sys.executable, "-u", "-c", script],
                cwd=str(tmp_path),
                env=env,
                tty=False,
                pipe_stdin=False,
            )
        )
        assert start == ExecResponse(process_id=process_id)
        chunks: list[ProcessOutputChunk] = []
        response = await _read_until_closed(backend, process_id, chunks)
        await backend.shutdown()
        return response, chunks

    response, chunks = asyncio.run(run())

    by_stream = {chunk.stream: chunk.chunk.into_inner() for chunk in chunks}
    assert by_stream[ExecOutputStream.STDOUT] == b"out:real-env"
    assert by_stream[ExecOutputStream.STDERR] == b"err:stream"
    assert response.exited is True
    assert response.exit_code == 7
    assert response.closed is True


def test_start_process_tty_process_uses_pty_stream_and_accepts_stdin(tmp_path):
    # Rust: local_process.rs::LocalProcess::start_process and stream_output.
    # Contract: tty=true uses spawn_pty_process with TerminalSize::default(),
    # accepts stdin through the session writer, and maps both process output
    # receivers to ExecOutputStream::Pty.
    script = textwrap.dedent(
        """
        import sys
        data = sys.stdin.buffer.read(4)
        sys.stdout.buffer.write(b"pty-out:" + data)
        sys.stdout.buffer.flush()
        sys.stderr.buffer.write(b":pty-err")
        sys.stderr.buffer.flush()
        raise SystemExit(3)
        """
    )

    async def run():
        backend = LocalProcess.new(None)
        process_id = ProcessId.new("pty-proc")
        start = await backend.exec(
            ExecParams(
                process_id=process_id,
                argv=[sys.executable, "-u", "-c", script],
                cwd=str(tmp_path),
                env=os.environ.copy(),
                tty=True,
                pipe_stdin=False,
            )
        )
        if os.name == "nt":
            return start, None, None, []
        assert start == ExecResponse(process_id=process_id)
        write = await backend.exec_write(WriteParams(process_id=process_id, chunk=ByteChunk(b"abcd")))
        chunks: list[ProcessOutputChunk] = []
        response = await _read_until_closed(backend, process_id, chunks)
        await backend.shutdown()
        return start, write, response, chunks

    start, write, response, chunks = asyncio.run(run())

    if os.name == "nt":
        assert start.code == -32603
        assert start.message == "codex-exec-server LocalProcess PTY runtime is not ported"
        return

    assert write == WriteResponse(status=WriteStatus.ACCEPTED)
    assert response.exit_code == 3
    assert response.closed is True
    assert chunks
    assert {chunk.stream for chunk in chunks} == {ExecOutputStream.PTY}
    combined = b"".join(chunk.chunk.into_inner() for chunk in chunks)
    assert b"pty-out:abcd" in combined
    assert b":pty-err" in combined


def test_exec_write_writes_to_real_pipe_process_stdin(tmp_path):
    # Rust: local_process.rs::LocalProcess::exec_write delegates accepted
    # writes to the spawned session writer.
    script = textwrap.dedent(
        """
        import sys
        data = sys.stdin.buffer.read(4)
        sys.stdout.buffer.write(b"got:" + data)
        sys.stdout.buffer.flush()
        """
    )

    async def run():
        backend = LocalProcess.new(None)
        process_id = ProcessId.new("stdin-proc")
        env = os.environ.copy()
        start = await backend.exec(
            ExecParams(
                process_id=process_id,
                argv=[sys.executable, "-u", "-c", script],
                cwd=str(tmp_path),
                env=env,
                tty=False,
                pipe_stdin=True,
            )
        )
        assert start == ExecResponse(process_id=process_id)
        write = await backend.exec_write(WriteParams(process_id=process_id, chunk=ByteChunk(b"abcd")))
        chunks: list[ProcessOutputChunk] = []
        response = await _read_until_closed(backend, process_id, chunks)
        await backend.shutdown()
        return write, response, chunks

    write, response, chunks = asyncio.run(run())

    assert write == WriteResponse(status=WriteStatus.ACCEPTED)
    assert response.exit_code == 0
    assert response.closed is True
    assert [chunk.chunk.into_inner() for chunk in chunks if chunk.stream == ExecOutputStream.STDOUT] == [
        b"got:abcd"
    ]


def test_local_process_start_returns_exec_process_facade_with_events(tmp_path):
    # Rust: local_process.rs impl ExecBackend for LocalProcess and impl
    # ExecProcess for LocalExecProcess.
    # Contract: start returns a process handle that supports retained reads,
    # stdin writes, wake/event subscriptions, and termination delegation.
    script = textwrap.dedent(
        """
        import sys
        data = sys.stdin.buffer.read(4)
        sys.stdout.buffer.write(b"facade:" + data)
        sys.stdout.buffer.flush()
        """
    )

    async def run():
        backend = LocalProcess.new(None)
        process_id = ProcessId.new("facade-proc")
        started = await backend.start(
            ExecParams(
                process_id=process_id,
                argv=[sys.executable, "-u", "-c", script],
                cwd=str(tmp_path),
                env=os.environ.copy(),
                tty=False,
                pipe_stdin=True,
            )
        )
        process = started.process
        events = process.subscribe_events()
        wake = process.subscribe_wake()
        write = await process.write(b"abcd")
        response = await process.read(after_seq=None, max_bytes=None, wait_ms=1000)
        chunks = list(response.chunks)
        while not response.closed:
            response = await process.read(after_seq=max(0, response.next_seq - 1), max_bytes=None, wait_ms=1000)
            chunks.extend(response.chunks)
        event_values = [
            await asyncio.wait_for(events.recv(), timeout=1),
            await asyncio.wait_for(events.recv(), timeout=1),
            await asyncio.wait_for(events.recv(), timeout=1),
        ]
        latest_seq = await asyncio.wait_for(wake.get(), timeout=1)
        await process.terminate()
        await backend.shutdown()
        return process.process_id(), write, response, chunks, event_values, latest_seq

    process_id, write, response, chunks, events, latest_seq = asyncio.run(run())

    assert process_id == ProcessId.new("facade-proc")
    assert write == WriteResponse(status=WriteStatus.ACCEPTED)
    assert chunks == [
        ProcessOutputChunk(seq=1, stream=ExecOutputStream.STDOUT, chunk=ByteChunk(b"facade:abcd"))
    ]
    assert response.exit_code == 0
    assert response.closed is True
    assert events == [
        ExecProcessEvent.output(
            ProcessOutputChunk(seq=1, stream=ExecOutputStream.STDOUT, chunk=ByteChunk(b"facade:abcd"))
        ),
        ExecProcessEvent.exited(seq=2, exit_code=0),
        ExecProcessEvent.closed(seq=3),
    ]
    assert latest_seq == 3


def test_exec_read_reports_unknown_and_starting_processes():
    # Rust: local_process.rs::LocalProcess::exec_read
    # Contract: unknown process ids and starting entries return invalid_request
    # errors with Rust message shape.
    backend = LocalProcess.new(None)
    backend.insert_starting_process_for_tests("starting")

    async def run():
        unknown = await backend.exec_read(ReadParams(process_id=ProcessId.new("missing")))
        starting = await backend.exec_read(ReadParams(process_id=ProcessId.new("starting")))
        return unknown, starting

    unknown, starting = asyncio.run(run())

    assert unknown.code == INVALID_REQUEST_ERROR_CODE
    assert unknown.message == "unknown process id missing"
    assert starting.code == INVALID_REQUEST_ERROR_CODE
    assert starting.message == "process id starting is starting"


def test_exec_read_filters_after_seq_and_respects_max_bytes():
    # Rust: local_process.rs::LocalProcess::exec_read
    # Contract: retained chunks with seq > after_seq are returned in order;
    # maxBytes stops after the current chunk once the limit is met and never
    # omits the first available chunk.
    backend = LocalProcess.new(None)
    process = backend.insert_running_process_for_tests("proc")
    process.record_output(ExecOutputStream.STDOUT, b"aaa")
    process.record_output(ExecOutputStream.STDERR, b"bbbb")
    process.record_output(ExecOutputStream.STDOUT, b"cc")

    response = asyncio.run(
        backend.exec_read(ReadParams(process_id=ProcessId.new("proc"), after_seq=1, max_bytes=4))
    )
    first_oversized = asyncio.run(
        backend.exec_read(ReadParams(process_id=ProcessId.new("proc"), after_seq=1, max_bytes=2))
    )

    assert response == ReadResponse(
        chunks=[ProcessOutputChunk(seq=2, stream=ExecOutputStream.STDERR, chunk=ByteChunk(b"bbbb"))],
        next_seq=3,
        exited=False,
        exit_code=None,
        closed=False,
        failure=None,
    )
    assert first_oversized.chunks == [
        ProcessOutputChunk(seq=2, stream=ExecOutputStream.STDERR, chunk=ByteChunk(b"bbbb"))
    ]


def test_exec_read_reports_exit_terminal_event_without_chunks():
    # Rust: local_process.rs::LocalProcess::exec_read
    # Contract: exit increments next_seq, sets exited/exit_code, and produces a
    # terminal response even when there are no output chunks after after_seq.
    backend = LocalProcess.new(None)
    process = backend.insert_running_process_for_tests("proc")
    process.record_output(ExecOutputStream.STDOUT, b"hello")
    process.record_exit(0)

    response = asyncio.run(
        backend.exec_read(ReadParams(process_id=ProcessId.new("proc"), after_seq=1))
    )

    assert response == ReadResponse(
        chunks=[],
        next_seq=3,
        exited=True,
        exit_code=0,
        closed=False,
        failure=None,
    )


def test_exec_read_reports_closed_state_and_retains_late_output_shape():
    # Rust test: exited_process_retains_late_output_past_retention
    # Contract: output recorded after exit is still returned with its retained
    # seq and the exit code remains visible; closed is reported separately.
    backend = LocalProcess.new(None)
    process = backend.insert_running_process_for_tests("proc")
    process.record_exit(0)
    process.record_output(ExecOutputStream.STDOUT, b"late output after retention\n")
    late = asyncio.run(
        backend.exec_read(ReadParams(process_id=ProcessId.new("proc"), after_seq=1))
    )
    process.mark_closed()
    closed = asyncio.run(
        backend.exec_read(ReadParams(process_id=ProcessId.new("proc"), after_seq=2))
    )

    assert late.chunks == [
        ProcessOutputChunk(
            seq=2,
            stream=ExecOutputStream.STDOUT,
            chunk=ByteChunk(b"late output after retention\n"),
        )
    ]
    assert late.exit_code == 0
    assert late.closed is False
    assert closed.closed is True
    assert closed.exit_code == 0


def test_closed_process_is_evicted_after_retention(monkeypatch):
    # Rust test: closed_process_is_evicted_after_retention
    # Contract: once a process has exited and all output streams have closed,
    # it remains readable briefly and is then removed from the process map.
    monkeypatch.setattr(exec_server, "LOCAL_PROCESS_EXITED_PROCESS_RETENTION_SECONDS", 0.01)
    backend = LocalProcess.new(None)
    process_id = ProcessId.new("proc-closed-eviction")
    process = backend.insert_running_process_for_tests(process_id)
    process.open_streams = 0
    process.record_exit(0)

    async def run() -> None:
        await _local_process_maybe_mark_closed(backend, process_id, process)
        assert process_id in backend.processes
        for _ in range(20):
            if process_id not in backend.processes:
                return
            await asyncio.sleep(0.01)
        raise AssertionError("closed process should be evicted")

    asyncio.run(run())


def test_exec_write_reports_unknown_starting_and_closed_stdin_states():
    # Rust: local_process.rs::LocalProcess::exec_write
    # Contract: writes to unknown/starting processes and running processes
    # without tty/pipe stdin return status values instead of errors.
    backend = LocalProcess.new(None)
    backend.insert_starting_process_for_tests("starting")
    backend.insert_running_process_for_tests("closed-stdin")

    async def run():
        missing = await backend.exec_write(
            WriteParams(process_id=ProcessId.new("missing"), chunk=ByteChunk(b"x"))
        )
        starting = await backend.exec_write(
            WriteParams(process_id=ProcessId.new("starting"), chunk=ByteChunk(b"x"))
        )
        closed = await backend.exec_write(
            WriteParams(process_id=ProcessId.new("closed-stdin"), chunk=ByteChunk(b"x"))
        )
        return missing, starting, closed

    missing, starting, closed = asyncio.run(run())

    assert missing == WriteResponse(status=WriteStatus.UNKNOWN_PROCESS)
    assert starting == WriteResponse(status=WriteStatus.STARTING)
    assert closed == WriteResponse(status=WriteStatus.STDIN_CLOSED)


def test_exec_write_accepts_tty_or_pipe_stdin_and_records_chunk():
    # Rust: local_process.rs::LocalProcess::exec_write
    # Contract: running processes with tty or pipe_stdin accept stdin bytes and
    # return WriteStatus::Accepted.
    backend = LocalProcess.new(None)
    tty_process = backend.insert_running_process_for_tests("tty")
    tty_process.tty = True
    pipe_process = backend.insert_running_process_for_tests("pipe")
    pipe_process.pipe_stdin = True

    async def run():
        tty = await backend.exec_write(WriteParams(process_id=ProcessId.new("tty"), chunk=ByteChunk(b"a")))
        pipe = await backend.exec_write(WriteParams(process_id=ProcessId.new("pipe"), chunk=ByteChunk(b"b")))
        return tty, pipe

    tty, pipe = asyncio.run(run())

    assert tty == WriteResponse(status=WriteStatus.ACCEPTED)
    assert pipe == WriteResponse(status=WriteStatus.ACCEPTED)
    assert tty_process.written_chunks == [b"a"]
    assert pipe_process.written_chunks == [b"b"]


def test_exec_write_maps_writer_failure_to_internal_error():
    # Rust: local_process.rs::LocalProcess::exec_write
    # Contract: writer send failure maps to internal_error with the Rust
    # message prefix.
    backend = LocalProcess.new(None)
    process = backend.insert_running_process_for_tests("proc")
    process.pipe_stdin = True
    process.writer_open = False

    result = asyncio.run(
        backend.exec_write(WriteParams(process_id=ProcessId.new("proc"), chunk=ByteChunk(b"x")))
    )

    assert result.code == -32603
    assert result.message == "failed to write to process stdin"


def test_terminate_process_reports_running_state_and_marks_termination():
    # Rust: local_process.rs::LocalProcess::terminate_process
    # Contract: unknown/starting/exited processes return running=false; running
    # processes are terminated and report running=true.
    backend = LocalProcess.new(None)
    backend.insert_starting_process_for_tests("starting")
    exited = backend.insert_running_process_for_tests("exited")
    exited.record_exit(0)
    running = backend.insert_running_process_for_tests("running")

    async def run():
        missing = await backend.terminate_process(TerminateParams(process_id=ProcessId.new("missing")))
        starting = await backend.terminate_process(TerminateParams(process_id=ProcessId.new("starting")))
        exited_result = await backend.terminate_process(TerminateParams(process_id=ProcessId.new("exited")))
        running_result = await backend.terminate_process(TerminateParams(process_id=ProcessId.new("running")))
        return missing, starting, exited_result, running_result

    missing, starting, exited_result, running_result = asyncio.run(run())

    assert missing == TerminateResponse(running=False)
    assert starting == TerminateResponse(running=False)
    assert exited_result == TerminateResponse(running=False)
    assert running_result == TerminateResponse(running=True)
    assert running.terminate_called is True
    assert exited.terminate_called is False


def test_local_pipe_child_process_terminates_process_group_on_posix(monkeypatch):
    # Rust: codex-utils-pty/src/pipe.rs::PipeChildTerminator and
    # codex-utils-pty/src/process_group.rs::kill_process_group.
    # Contract used by local_process.rs: terminating a spawned pipe-backed
    # session targets the child process group on POSIX; non-POSIX falls back to
    # terminating the direct child process.
    class Child:
        pid = 1234

        def __init__(self):
            self.terminated = False
            self.killed = False

        async def wait(self):
            return 0

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

    child = Child()
    process = _LocalPipeChildProcess(child)

    if os.name == "posix":
        calls = []
        monkeypatch.setattr(os, "killpg", lambda pid, signal_number: calls.append((pid, signal_number)))

        process.terminate()
        process.kill()

        assert calls == [(1234, 15), (1234, 9)]
        assert child.terminated is False
        assert child.killed is False
    else:
        process.terminate()
        process.kill()

        assert child.terminated is True
        assert child.killed is True


async def _read_until_closed(
    backend: LocalProcess,
    process_id: ProcessId,
    chunks: list[ProcessOutputChunk],
) -> ReadResponse:
    after_seq = None
    for _ in range(20):
        response = await backend.exec_read(
            ReadParams(process_id=process_id, after_seq=after_seq, wait_ms=1000)
        )
        chunks.extend(response.chunks)
        if response.closed:
            return response
        after_seq = max(0, response.next_seq - 1)
    raise AssertionError("process did not close")
