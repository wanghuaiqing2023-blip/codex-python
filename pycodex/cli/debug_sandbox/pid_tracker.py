"""Rust-aligned implementation for codex-cli debug_sandbox::pid_tracker."""



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



@dataclass(frozen=True)
class PidTracker:
    """Lightweight counterpart for Rust's macOS debug sandbox PidTracker."""

    root_pid: int
    list_children: Callable[[int], Sequence[int]] | None = None
    is_alive: Callable[[int], bool] | None = None

    @classmethod
    def new(
        cls,
        root_pid: int,
        *,
        list_children: Callable[[int], Sequence[int]] | None = None,
        is_alive: Callable[[int], bool] | None = None,
    ) -> "PidTracker | None":
        if root_pid <= 0:
            return None
        return cls(root_pid, list_children=list_children, is_alive=is_alive)

    async def stop(self) -> set[int]:
        return track_descendants(
            self.root_pid,
            list_children=self.list_children,
            is_alive=self.is_alive,
        )

def pid_is_alive(pid: int) -> bool:
    """Mirror Rust pid_is_alive: invalid pids are dead; EPERM still means alive."""

    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True

def list_child_pids(
    parent: int,
    *,
    platform: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> list[int]:
    """Best-effort Python boundary for Rust's macOS proc_listchildpids wrapper."""

    if parent <= 0:
        return []
    platform_name = platform or sys.platform
    if platform_name != "darwin":
        return []

    run = runner if runner is not None else subprocess.run
    try:
        result = run(
            ["pgrep", "-P", str(parent)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return []

    if getattr(result, "returncode", 1) not in (0, 1):
        return []

    pids: list[int] = []
    for line in str(getattr(result, "stdout", "")).splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid > 0:
            pids.append(pid)
    return pids

def track_descendants(
    root_pid: int,
    *,
    list_children: Callable[[int], Sequence[int]] | None = None,
    is_alive: Callable[[int], bool] | None = None,
) -> set[int]:
    """Collect root and recursively discovered child pids for the debug sandbox."""

    if root_pid <= 0:
        return set()

    child_lister = list_children if list_children is not None else list_child_pids
    alive = is_alive if is_alive is not None else pid_is_alive

    seen: set[int] = {root_pid}
    stack = [root_pid]
    while stack:
        parent = stack.pop()
        if parent != root_pid and not alive(parent):
            continue
        for child_pid in child_lister(parent):
            if child_pid <= 0 or child_pid in seen:
                continue
            seen.add(child_pid)
            stack.append(child_pid)
    return seen

