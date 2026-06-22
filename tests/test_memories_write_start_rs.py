from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from pycodex.memories.write import (
    memory_startup_skip_reason,
    memory_root,
    start_memories_startup_task,
)


class Features:
    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    def enabled(self, feature: str) -> bool:
        return self._enabled and feature in {"MemoryTool", "memory_tool"}


class Source:
    def __init__(self, non_root: bool = False) -> None:
        self._non_root = non_root

    def is_non_root_agent(self) -> bool:
        return self._non_root


class Thread:
    def __init__(self, state_db=None) -> None:
        self._state_db = state_db

    def state_db(self):
        return self._state_db


def config(tmp_path: Path, *, ephemeral: bool = False, memory_tool: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        codex_home=tmp_path,
        ephemeral=ephemeral,
        features=Features(memory_tool),
    )


def test_memory_startup_skip_reason_matches_start_rs_gates(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/start.rs::start_memories_startup_task
    # Contract: startup is skipped for ephemeral config, disabled MemoryTool, non-root agent source, or unavailable state DB.
    assert memory_startup_skip_reason(config(tmp_path, ephemeral=True), Source(), True) == "skipped_ephemeral"
    assert memory_startup_skip_reason(config(tmp_path, memory_tool=False), Source(), True) == "skipped_feature_disabled"
    assert memory_startup_skip_reason(config(tmp_path), Source(non_root=True), True) == "skipped_non_root_agent"
    assert memory_startup_skip_reason(config(tmp_path), Source(), False) == "skipped_state_db_unavailable"
    assert memory_startup_skip_reason(config(tmp_path), Source(), True) is None


def test_start_memories_startup_task_creates_root_seeds_and_runs_phases(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/start.rs + src/startup_tests.rs::memories_startup_creates_memory_root
    # Contract: eligible startup creates the memory root, seeds extension instructions, prunes, checks rate limits, then runs phase1 and phase2.
    calls: list[str] = []
    cfg = config(tmp_path)

    async def prune(context, _config) -> None:
        calls.append("prune")
        assert memory_root(tmp_path).is_dir()
        assert (memory_root(tmp_path) / "extensions" / "ad_hoc" / "instructions.md").is_file()
        assert context.state_db() == {"db": "ok"}

    def rate_limits_ok(_auth_manager, _config) -> bool:
        calls.append("rate_limits")
        return True

    async def phase1(context, _config) -> None:
        calls.append("phase1")
        assert context.thread_id == "thread-1"

    def phase2(_context, _config) -> None:
        calls.append("phase2")

    result = asyncio.run(
        start_memories_startup_task(
            "thread-manager",
            "auth-manager",
            "thread-1",
            Thread({"db": "ok"}),
            cfg,
            Source(),
            phase1_prune=prune,
            rate_limits_ok_fn=rate_limits_ok,
            phase1_run=phase1,
            phase2_run=phase2,
        )
    )

    assert result.status == "completed"
    assert result.memory_root == memory_root(tmp_path)
    assert calls == ["prune", "rate_limits", "phase1", "phase2"]


def test_start_memories_startup_task_rate_limit_skip_after_prune(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/start.rs::start_memories_startup_task
    # Contract: phase1 pruning runs before the rate-limit gate; a failed gate records skipped_rate_limit and prevents phase runs.
    calls: list[str] = []

    def prune(_context, _config) -> None:
        calls.append("prune")

    def rate_limits_ok(_auth_manager, _config) -> bool:
        calls.append("rate_limits")
        return False

    def phase1(_context, _config) -> None:
        calls.append("phase1")

    def phase2(_context, _config) -> None:
        calls.append("phase2")

    result = asyncio.run(
        start_memories_startup_task(
            "thread-manager",
            "auth-manager",
            "thread-1",
            Thread({"db": "ok"}),
            config(tmp_path),
            Source(),
            phase1_prune=prune,
            rate_limits_ok_fn=rate_limits_ok,
            phase1_run=phase1,
            phase2_run=phase2,
        )
    )

    assert result.status == "skipped_rate_limit"
    assert calls == ["prune", "rate_limits"]
    assert result.context is not None
    assert result.context.counters == [("memory_startup", 1, (("status", "skipped_rate_limit"),))]
