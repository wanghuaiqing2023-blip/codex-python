"""Platform-gated zsh-fork fixtures derived from ``zsh_fork.rs``."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable


@dataclass(frozen=True)
class ZshForkRuntime:
    zsh_path: Path
    workspace: Path


def restrictive_workspace_write_profile() -> dict[str, object]:
    return {
        "sandbox_mode": "workspace-write",
        "writable_roots": (),
        "network_access": False,
    }


def zsh_fork_runtime(test_name: str) -> ZshForkRuntime | None:
    if os.name == "nt":
        return None
    zsh = shutil.which("zsh")
    if zsh is None:
        return None
    workspace = Path(tempfile.mkdtemp(prefix=f"pycodex-zsh-fork-{test_name}-"))
    return ZshForkRuntime(Path(zsh), workspace)


async def build_zsh_fork_test(
    test_name: str,
    callback: Callable[[ZshForkRuntime], Awaitable[Any]],
) -> Any | None:
    runtime = zsh_fork_runtime(test_name)
    if runtime is None:
        return None
    return await callback(runtime)


__all__ = [
    "ZshForkRuntime",
    "build_zsh_fork_test",
    "restrictive_workspace_write_profile",
    "zsh_fork_runtime",
]
