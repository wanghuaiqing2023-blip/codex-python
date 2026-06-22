"""Rust-derived tests for codex-utils-pty/src/lib.rs."""

from __future__ import annotations

import pycodex.utils.pty as pty


def test_lib_rs_public_facade_reexports_and_aliases() -> None:
    # Rust crate/module: codex-utils-pty/src/lib.rs
    # Contract: crate root re-exports the public pipe/process/PTY facade and
    # preserves backwards-compatible aliases for ProcessHandle/SpawnedProcess.
    assert pty.DEFAULT_OUTPUT_BYTES_CAP == 1024 * 1024

    assert pty.ExecCommandSession is pty.ProcessHandle
    assert pty.SpawnedPty is pty.SpawnedProcess
    assert pty.spawn_pipe_process is pty.__dict__["spawn_pipe_process"]
    assert pty.spawn_pipe_process_no_stdin is pty.__dict__["spawn_pipe_process_no_stdin"]
    assert pty.spawn_from_driver is pty.__dict__["spawn_from_driver"]
    assert pty.spawn_pty_process is pty.__dict__["spawn_pty_process"]
    assert pty.conpty_supported is pty.__dict__["conpty_supported"]


def test_lib_rs_all_exports_public_facade_names() -> None:
    # Rust crate/module: codex-utils-pty/src/lib.rs
    # Contract: the crate root is the public import surface for downstream
    # crates, so Python keeps the same names in the package-level export list.
    expected = {
        "DEFAULT_OUTPUT_BYTES_CAP",
        "ExecCommandSession",
        "ProcessDriver",
        "ProcessHandle",
        "SpawnedProcess",
        "SpawnedPty",
        "TerminalSize",
        "combine_output_receivers",
        "conpty_supported",
        "process_group",
        "spawn_from_driver",
        "spawn_pipe_process",
        "spawn_pipe_process_no_stdin",
        "spawn_pipe_process_no_stdin_with_inherited_fds",
        "spawn_pty_process",
    }

    assert expected <= set(pty.__all__)

