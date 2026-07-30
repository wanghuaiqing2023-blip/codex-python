"""Filesystem wait helpers from ``core_test_support::fs_wait``."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path


async def wait_for_path_exists(path: str | Path, timeout: float) -> Path:
    target = Path(path)
    deadline = time.monotonic() + timeout
    while not target.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out waiting for {target!r}")
        await asyncio.sleep(0.02)
    return target


async def wait_for_matching_file(
    root: str | Path,
    timeout: float,
    predicate: Callable[[Path], bool],
) -> Path:
    directory = await wait_for_path_exists(root, timeout)
    deadline = time.monotonic() + timeout
    while True:
        for candidate in directory.rglob("*"):
            if candidate.is_file() and predicate(candidate):
                return candidate
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out waiting for matching file in {directory!r}")
        await asyncio.sleep(0.02)


__all__ = ["wait_for_matching_file", "wait_for_path_exists"]
