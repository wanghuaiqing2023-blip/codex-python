"""Rust-aligned implementation for codex-cli debug_sandbox::windows_stdio_bridge."""



from __future__ import annotations

import json

import os

import re

import subprocess

import threading

import time

from collections.abc import Callable, Iterable, Mapping, Sequence

from dataclasses import dataclass

from enum import Enum

from pathlib import Path

import sys

from pycodex.core.spawn import CODEX_SANDBOX_ENV_VAR, CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR



from pycodex.cli.debug_sandbox import DebugSandboxWindowsSessionControlResult, DebugSandboxWindowsSessionPlan, DebugSandboxWindowsSessionRunResult, run_debug_sandbox_windows_session_control_flow



STDIN_FORWARD_CHUNK_SIZE = 8 * 1024

@dataclass(frozen=True)
class DebugSandboxWindowsSessionIoBridgeResult:
    """Observed Windows session stdio bridge behavior."""

    stdin_chunks: tuple[bytes, ...]
    stdout: bytes
    stderr: bytes
    control: DebugSandboxWindowsSessionControlResult
    actions: tuple[str, ...]

@dataclass(frozen=True)
class DebugSandboxWindowsSpawnBridgeResult:
    """Combined Windows session spawn plus stdio bridge result."""

    run: DebugSandboxWindowsSessionRunResult
    io: DebugSandboxWindowsSessionIoBridgeResult | None

def _binary_stream(stream: object) -> object:
    return getattr(stream, "buffer", stream)

def _write_forwarded_bytes(stream: object, data: bytes) -> None:
    destination = _binary_stream(stream)
    try:
        destination.write(data)
    except TypeError:
        destination.write(data.decode("utf-8", errors="replace"))
    flush = getattr(destination, "flush", None)
    if callable(flush):
        flush()

def _forward_output(source: object | None, destination: object) -> None:
    if source is None:
        return
    try:
        while True:
            chunk = source.read(64 * 1024)
            if not chunk:
                return
            _write_forwarded_bytes(destination, bytes(chunk))
    except (BrokenPipeError, OSError, ValueError):
        return

def _forward_input(source: object, process_stdin: object) -> None:
    input_stream = _binary_stream(source)
    try:
        while True:
            chunk = input_stream.read(STDIN_FORWARD_CHUNK_SIZE)
            if not chunk:
                return
            payload = chunk.encode("utf-8") if isinstance(chunk, str) else bytes(chunk)
            process_stdin.write(payload)
            process_stdin.flush()
    except (BrokenPipeError, OSError, ValueError):
        return
    finally:
        try:
            process_stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass

def spawn_input_forwarder(
    source: object,
    process_stdin: object,
    *,
    name: str = "pycodex-sandbox-stdin",
) -> threading.Thread:
    """Spawn the dedicated stdin forwarding thread owned by this module."""

    thread = threading.Thread(
        target=_forward_input,
        args=(source, process_stdin),
        name=name,
        daemon=True,
    )
    thread.start()
    return thread

def spawn_output_forwarder(
    source: object | None,
    destination: object,
    *,
    name: str,
) -> threading.Thread:
    """Spawn one dedicated output forwarding thread owned by this module."""

    thread = threading.Thread(
        target=_forward_output,
        args=(source, destination),
        name=name,
        daemon=True,
    )
    thread.start()
    return thread

def run_debug_sandbox_windows_session_io_bridge(
    plan: DebugSandboxWindowsSessionPlan,
    *,
    stdin: bytes = b"",
    stdout_chunks: Sequence[bytes] = (),
    stderr_chunks: Sequence[bytes] = (),
    exit_code: int | None,
    ctrl_c: bool = False,
    write_stdin: Callable[[bytes], None] | None = None,
    close_stdin: Callable[[], None] | None = None,
    request_terminate: Callable[[], None] | None = None,
) -> DebugSandboxWindowsSessionIoBridgeResult:
    """Bridge finite stdio data through Rust-equivalent Windows session hooks."""

    stdin_chunks = tuple(windows_stdin_forward_chunks(stdin))
    actions: list[str] = []
    for chunk in stdin_chunks:
        if write_stdin is not None:
            write_stdin(chunk)
        actions.append("write_stdin")

    if close_stdin is not None:
        close_stdin()
    actions.append("close_stdin")

    if ctrl_c:
        if request_terminate is not None:
            request_terminate()
        actions.append("request_terminate")

    control = run_debug_sandbox_windows_session_control_flow(
        plan,
        exit_code=exit_code,
        ctrl_c=ctrl_c,
        stdin_eof=True,
    )
    return DebugSandboxWindowsSessionIoBridgeResult(
        stdin_chunks=stdin_chunks,
        stdout=windows_output_forward_bytes(list(stdout_chunks)),
        stderr=windows_output_forward_bytes(list(stderr_chunks)),
        control=control,
        actions=tuple(actions),
    )

def run_debug_sandbox_windows_session_with_stdio_bridge(
    plan: DebugSandboxWindowsSessionPlan,
    *,
    spawner: Callable[[DebugSandboxWindowsSessionPlan], object],
    write_stdin: Callable[[bytes], None] | None = None,
    close_stdin: Callable[[], None] | None = None,
    request_terminate: Callable[[], None] | None = None,
) -> DebugSandboxWindowsSpawnBridgeResult:
    """Spawn a Windows session and bridge finite stdio through injected hooks."""

    try:
        spawned = spawner(plan)
    except Exception as exc:
        return DebugSandboxWindowsSpawnBridgeResult(
            run=DebugSandboxWindowsSessionRunResult(
                mode=plan.mode,
                exit_code=1,
                output_drain_timeout_seconds=plan.output_drain_timeout_seconds,
                error_message=f"windows sandbox failed: {exc}",
            ),
            io=None,
        )

    exit_code = getattr(spawned, "exit_code", None)
    io = run_debug_sandbox_windows_session_io_bridge(
        plan,
        stdin=getattr(spawned, "stdin", b""),
        stdout_chunks=tuple(getattr(spawned, "stdout_chunks", ())),
        stderr_chunks=tuple(getattr(spawned, "stderr_chunks", ())),
        exit_code=exit_code,
        ctrl_c=bool(getattr(spawned, "ctrl_c", False)),
        write_stdin=write_stdin,
        close_stdin=close_stdin,
        request_terminate=request_terminate,
    )
    return DebugSandboxWindowsSpawnBridgeResult(
        run=DebugSandboxWindowsSessionRunResult(
            mode=plan.mode,
            exit_code=io.control.exit_code,
            output_drain_timeout_seconds=plan.output_drain_timeout_seconds,
            error_message=None,
        ),
        io=io,
    )

def windows_stdin_forward_chunks(data: bytes) -> list[bytes]:
    """Return Windows sandbox stdin forwarder chunks for ``data``."""

    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    return [
        data[index : index + STDIN_FORWARD_CHUNK_SIZE]
        for index in range(0, len(data), STDIN_FORWARD_CHUNK_SIZE)
    ]

def windows_output_forward_bytes(chunks: list[bytes]) -> bytes:
    """Return bytes written by the Windows sandbox output forwarder."""

    output = bytearray()
    for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise TypeError("chunks must contain bytes")
        output.extend(chunk)
    return bytes(output)

