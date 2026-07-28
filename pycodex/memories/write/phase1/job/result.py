"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from typing import Any, Callable, Iterable

async def failed(context: MemoryStartupContext, thread_id: Any, ownership_token: str, reason: str) -> None:
    state_db = context.state_db()
    if state_db is None:
        return
    try:
        await _maybe_await(_memories_store(state_db).mark_stage1_job_failed(thread_id, ownership_token, reason, STAGE_ONE_JOB_RETRY_DELAY_SECONDS))
    except Exception:
        return


async def no_output(context: MemoryStartupContext, thread_id: Any, ownership_token: str) -> str:
    state_db = context.state_db()
    if state_db is None:
        return 'failed'
    try:
        ok = await _maybe_await(_memories_store(state_db).mark_stage1_job_succeeded_no_output(thread_id, ownership_token))
    except Exception:
        ok = False
    return 'succeeded_no_output' if bool(ok) else 'failed'


async def success(context: MemoryStartupContext, thread_id: Any, ownership_token: str, source_updated_at: int, raw_memory: str, rollout_summary: str, rollout_slug: str | None) -> str:
    state_db = context.state_db()
    if state_db is None:
        return 'failed'
    try:
        ok = await _maybe_await(_memories_store(state_db).mark_stage1_job_succeeded(thread_id, ownership_token, int(source_updated_at), raw_memory, rollout_summary, rollout_slug))
    except Exception:
        ok = False
    return 'succeeded_with_output' if bool(ok) else 'failed'


from pycodex.memories.write.phase2 import _memories_store
from pycodex.memories.write.runtime import MemoryStartupContext
from pycodex.memories.write.runtime import _maybe_await
from pycodex.memories.write.stage_one import JOB_RETRY_DELAY_SECONDS as STAGE_ONE_JOB_RETRY_DELAY_SECONDS
