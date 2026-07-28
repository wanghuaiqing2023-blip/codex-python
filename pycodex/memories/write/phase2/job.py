"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from pycodex.state import Phase2JobClaimOutcome, Phase2JobClaimed, Stage1StartupClaimParams
from typing import Any, Callable, Iterable

async def claim(context: MemoryStartupContext, state_db: Any | None=None) -> PhaseTwoClaim | str:
    db = state_db if state_db is not None else context.state_db()
    if db is None:
        return 'failed_claim'
    try:
        outcome = await _maybe_await(_memories_store(db).try_claim_global_phase2_job(context.thread_id, STAGE_TWO_JOB_LEASE_SECONDS))
    except Exception:
        return 'failed_claim'
    if isinstance(outcome, Phase2JobClaimed) or _has_attrs(outcome, 'ownership_token', 'input_watermark'):
        context.counter(MEMORY_PHASE_TWO_JOBS, 1, (('status', 'claimed'),))
        return PhaseTwoClaim(token=str(getattr(outcome, 'ownership_token')), watermark=int(getattr(outcome, 'input_watermark')))
    if outcome is Phase2JobClaimOutcome.SKIPPED_RETRY_UNAVAILABLE or str(outcome).endswith('skipped_retry_unavailable'):
        return 'skipped_retry_unavailable'
    if outcome is Phase2JobClaimOutcome.SKIPPED_COOLDOWN or str(outcome).endswith('skipped_cooldown'):
        return 'skipped_cooldown'
    if outcome is Phase2JobClaimOutcome.SKIPPED_RUNNING or str(outcome).endswith('skipped_running'):
        return 'skipped_running'
    return 'failed_claim'


async def failed(context: MemoryStartupContext, state_db: Any, claim: PhaseTwoClaim, reason: str) -> None:
    context.counter(MEMORY_PHASE_TWO_JOBS, 1, (('status', reason),))
    store = _memories_store(state_db)
    try:
        ok = await _maybe_await(store.mark_global_phase2_job_failed(claim.token, reason, STAGE_TWO_JOB_RETRY_DELAY_SECONDS))
    except Exception:
        ok = False
    if bool(ok):
        return
    fallback = getattr(store, 'mark_global_phase2_job_failed_if_unowned', None)
    if callable(fallback):
        try:
            await _maybe_await(fallback(claim.token, reason, STAGE_TWO_JOB_RETRY_DELAY_SECONDS))
        except Exception:
            return


async def succeed(context: MemoryStartupContext, state_db: Any, claim: PhaseTwoClaim, completion_watermark: int, selected_outputs: Iterable[Any], reason: str) -> bool:
    context.counter(MEMORY_PHASE_TWO_JOBS, 1, (('status', reason),))
    try:
        return bool(await _maybe_await(_memories_store(state_db).mark_global_phase2_job_succeeded(claim.token, int(completion_watermark), list(selected_outputs))))
    except Exception:
        return False


def _has_attrs(value: Any, *names: str) -> bool:
    return all((hasattr(value, name) for name in names))


from pycodex.memories.write.metrics import MEMORY_PHASE_TWO_JOBS
from pycodex.memories.write.phase2 import PhaseTwoClaim
from pycodex.memories.write.phase2 import _memories_store
from pycodex.memories.write.runtime import MemoryStartupContext
from pycodex.memories.write.runtime import _maybe_await
from pycodex.memories.write.stage_two import JOB_LEASE_SECONDS as STAGE_TWO_JOB_LEASE_SECONDS
from pycodex.memories.write.stage_two import JOB_RETRY_DELAY_SECONDS as STAGE_TWO_JOB_RETRY_DELAY_SECONDS
