"""Windows integration tests derived from codex-utils-pty/src/win."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from pycodex.utils.pty.process import TerminalSize
from pycodex.utils.pty.pty import conpty_supported, spawn_process
from pycodex.utils.pty.win.conpty import RawConPty
from pycodex.utils.pty.win.procthreadattr import ProcThreadAttributeList
from pycodex.utils.pty.win.psuedocon import PsuedoCon


@pytest.mark.skipif(os.name != "nt", reason="Rust win modules are cfg(windows)")
def test_windows_conpty_runtime_chain_round_trips_output() -> None:
    # Rust owners:
    # - pty.rs::platform_native_pty_system
    # - win/conpty.rs::{ConPtySystem, RawConPty}
    # - win/psuedocon.rs::PsuedoCon::spawn_command
    # - win/procthreadattr.rs::ProcThreadAttributeList
    assert conpty_supported()
    assert RawConPty.__module__.endswith(".win.conpty")
    assert PsuedoCon.__module__.endswith(".win.psuedocon")
    assert ProcThreadAttributeList.__module__.endswith(".win.procthreadattr")

    async def run() -> tuple[int, bytes]:
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"COMSPEC", "PATH", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP", "WINDIR"}
        }
        spawned = await spawn_process(
            sys.executable,
            ["-u", "-c", "print('conpty-chain-ok')"],
            Path.cwd(),
            env,
            size=TerminalSize(rows=24, cols=100),
        )
        code = await asyncio.wait_for(spawned.exit_rx, timeout=10.0)
        chunks: list[bytes] = []
        while True:
            try:
                chunks.append(await asyncio.wait_for(spawned.stdout_rx.get(), timeout=0.25))
            except TimeoutError:
                break
        return code, b"".join(chunks)

    code, output = asyncio.run(run())
    assert code == 0
    assert b"conpty-chain-ok" in output
