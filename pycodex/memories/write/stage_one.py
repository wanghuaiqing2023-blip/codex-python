"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from pathlib import Path
from pycodex.protocol import ReasoningEffort

MODEL = "gpt-5.4-mini"
REASONING_EFFORT = ReasoningEffort.LOW
CONCURRENCY_LIMIT = 8
JOB_LEASE_SECONDS = 3_600
JOB_RETRY_DELAY_SECONDS = 3_600
THREAD_SCAN_LIMIT = 5_000
PRUNE_BATCH_SIZE = 200
DEFAULT_ROLLOUT_TOKEN_LIMIT = 150_000
CONTEXT_WINDOW_PERCENT = 70
PROMPT = (
    Path(__file__).resolve().parents[3]
    / "codex"
    / "codex-rs"
    / "memories"
    / "write"
    / "templates"
    / "memories"
    / "stage_one_system.md"
).read_text(encoding="utf-8")
