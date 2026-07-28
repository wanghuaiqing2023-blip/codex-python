"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from pycodex.protocol import ReasoningEffort

MODEL = "gpt-5.4"
REASONING_EFFORT = ReasoningEffort.MEDIUM
JOB_LEASE_SECONDS = 3_600
JOB_RETRY_DELAY_SECONDS = 3_600
JOB_HEARTBEAT_SECONDS = 90
