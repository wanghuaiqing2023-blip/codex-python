from __future__ import annotations

import asyncio
import os
from pathlib import Path
import signal
import sys
import urllib.request

from .managed_install import ExecutableIdentity
from .managed_install import executable_identity
from .managed_install import resolved_managed_codex_bin


INITIAL_UPDATE_DELAY = 5 * 60.0
RESTART_RETRY_INTERVAL = 0.05
UPDATE_INTERVAL = 60 * 60.0
INSTALL_URL = "https://chatgpt.com/codex/install.sh"


async def run() -> None:
    if os.name == "nt":
        raise RuntimeError("pid-managed updater loop is unsupported on this platform")

    terminate = asyncio.Event()
    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGTERM, terminate.set)
    except (NotImplementedError, RuntimeError):
        pass
    running_identity = await executable_identity(Path(sys.executable).resolve())
    if await _sleep_or_terminate(INITIAL_UPDATE_DELAY, terminate):
        return
    while not terminate.is_set():
        try:
            await update_once(running_identity, terminate)
        except Exception:
            pass
        if await _sleep_or_terminate(UPDATE_INTERVAL, terminate):
            return


async def update_once(
    running_updater_identity: ExecutableIdentity,
    terminate: asyncio.Event,
) -> None:
    from . import Daemon
    from . import RestartIfRunningOutcome

    await install_latest_standalone()
    daemon = Daemon.from_environment()
    managed = await resolved_managed_codex_bin(daemon.managed_codex_bin)
    managed_identity = await executable_identity(managed)
    restart_mode, refresh_mode = update_modes_for_identities(
        running_updater_identity,
        managed_identity,
    )

    while not terminate.is_set():
        outcome = await daemon.try_restart_if_running(
            restart_mode,
            refresh_mode,
            managed,
        )
        if outcome is not RestartIfRunningOutcome.BUSY:
            return
        if await _sleep_or_terminate(RESTART_RETRY_INTERVAL, terminate):
            return


def update_modes_for_identities(
    running_updater_identity: ExecutableIdentity,
    managed_identity: ExecutableIdentity,
) -> tuple[object, object]:
    from . import RestartMode
    from . import UpdaterRefreshMode

    if running_updater_identity == managed_identity:
        return RestartMode.IF_VERSION_CHANGED, UpdaterRefreshMode.NONE
    return (
        RestartMode.ALWAYS,
        UpdaterRefreshMode.REEXEC_IF_MANAGED_BINARY_CHANGED,
    )


def reexec_managed_updater(managed_codex_bin: Path) -> None:
    if os.name == "nt":
        raise RuntimeError("pid-managed updater loop is unsupported on this platform")
    os.execv(
        str(managed_codex_bin),
        [
            str(managed_codex_bin),
            "app-server",
            "daemon",
            "pid-update-loop",
        ],
    )


async def install_latest_standalone() -> None:
    if os.name == "nt":
        raise RuntimeError("pid-managed updater loop is unsupported on this platform")

    def fetch() -> bytes:
        with urllib.request.urlopen(INSTALL_URL, timeout=30) as response:
            return response.read()

    script = await asyncio.to_thread(fetch)
    process = await asyncio.create_subprocess_exec(
        "/bin/sh",
        "-s",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate(script)
    del stdout
    if process.returncode != 0:
        raise RuntimeError(
            f"standalone Codex updater exited with status {process.returncode}"
        )


async def _sleep_or_terminate(duration: float, terminate: asyncio.Event) -> bool:
    try:
        await asyncio.wait_for(terminate.wait(), timeout=duration)
    except TimeoutError:
        return False
    return True


__all__ = [
    "install_latest_standalone",
    "reexec_managed_updater",
    "run",
    "update_modes_for_identities",
    "update_once",
]
