"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pycodex.protocol import AgentStatus, BaseInstructions, ContentItem, ModelInfo, Op, RateLimitSnapshot, RateLimitWindow, ReasoningEffort, ReasoningSummary, ResponseItem, TokenUsage, TruncationPolicyConfig, UserInput
from pycodex.state import Phase2JobClaimOutcome, Phase2JobClaimed, Stage1StartupClaimParams
from typing import Any, Callable, Iterable

@dataclass(frozen=True)
class StageOneOutput:
    """Phase-1 model output payload from Rust ``src/phase1.rs``."""
    raw_memory: str
    rollout_summary: str
    rollout_slug: str | None


@dataclass(frozen=True)
class PhaseOneJobResult:
    outcome: str
    token_usage: TokenUsage | None = None


@dataclass(frozen=True)
class PhaseOneStats:
    claimed: int
    succeeded_with_output: int
    succeeded_no_output: int
    failed: int
    total_token_usage: TokenUsage | None = None


def output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "rollout_summary": {"type": "string"},
            "rollout_slug": {"type": ["string", "null"]},
            "raw_memory": {"type": "string"},
        },
        "required": ["rollout_summary", "rollout_slug", "raw_memory"],
        "additionalProperties": False,
    }


def aggregate_stats(outcomes: Iterable[PhaseOneJobResult]) -> PhaseOneStats:
    results = list(outcomes)
    succeeded_with_output = sum((1 for result in results if result.outcome == 'succeeded_with_output'))
    succeeded_no_output = sum((1 for result in results if result.outcome == 'succeeded_no_output'))
    failed = sum((1 for result in results if result.outcome == 'failed'))
    total_usage = TokenUsage()
    has_usage = False
    for result in results:
        if result.token_usage is not None:
            total_usage = total_usage.add(result.token_usage)
            has_usage = True
    return PhaseOneStats(claimed=len(results), succeeded_with_output=succeeded_with_output, succeeded_no_output=succeeded_no_output, failed=failed, total_token_usage=total_usage if has_usage else None)


def emit_metrics(context: StageOneRequestContext, counts: PhaseOneStats) -> None:
    if counts.claimed > 0:
        context.counter(MEMORY_PHASE_ONE_JOBS, counts.claimed, (('status', 'claimed'),))
    if counts.succeeded_with_output > 0:
        context.counter(MEMORY_PHASE_ONE_JOBS, counts.succeeded_with_output, (('status', 'succeeded'),))
        context.counter(MEMORY_PHASE_ONE_OUTPUT, counts.succeeded_with_output, ())
    if counts.succeeded_no_output > 0:
        context.counter(MEMORY_PHASE_ONE_JOBS, counts.succeeded_no_output, (('status', 'succeeded_no_output'),))
    if counts.failed > 0:
        context.counter(MEMORY_PHASE_ONE_JOBS, counts.failed, (('status', 'failed'),))
    token_usage = counts.total_token_usage
    if token_usage is not None:
        context.histogram(MEMORY_PHASE_ONE_TOKEN_USAGE, max(token_usage.total_tokens, 0), (('token_type', 'total'),))
        context.histogram(MEMORY_PHASE_ONE_TOKEN_USAGE, max(token_usage.input_tokens, 0), (('token_type', 'input'),))
        context.histogram(MEMORY_PHASE_ONE_TOKEN_USAGE, token_usage.cached_input(), (('token_type', 'cached_input'),))
        context.histogram(MEMORY_PHASE_ONE_TOKEN_USAGE, max(token_usage.output_tokens, 0), (('token_type', 'output'),))
        context.histogram(MEMORY_PHASE_ONE_TOKEN_USAGE, max(token_usage.reasoning_output_tokens, 0), (('token_type', 'reasoning_output'),))


async def run(context: MemoryStartupContext, config: Any, *, job_runner: Callable[[MemoryStartupContext, Any, Any, StageOneRequestContext], Any] | None=None) -> PhaseOneStats | None:
    memories_config = getattr(config, 'memories')
    model_name = getattr(memories_config, 'extract_model', None) or STAGE_ONE_MODEL
    stage_one_context = await _maybe_await(context.stage_one_request_context(config, model_name, STAGE_ONE_REASONING_EFFORT))
    stage_one_context.start_timer(MEMORY_PHASE_ONE_E2E_MS)
    claimed_candidates = await claim_startup_jobs(context, memories_config)
    if claimed_candidates is None:
        return None
    if not claimed_candidates:
        stage_one_context.counter(MEMORY_PHASE_ONE_JOBS, 1, (('status', 'skipped_no_candidates'),))
        return PhaseOneStats(0, 0, 0, 0, None)
    runner = job_runner or getattr(config, 'phase_one_job_runner', None) or phase_one_job_run
    outcomes = [await _maybe_await(runner(context, config, claim, stage_one_context)) for claim in claimed_candidates]
    stats = aggregate_stats(outcomes)
    emit_metrics(stage_one_context, stats)
    return stats


async def claim_startup_jobs(context: MemoryStartupContext, memories_config: Any) -> list[Any] | None:
    state_db = context.state_db()
    if state_db is None:
        return None
    allowed_sources = tuple(str(source) for source in INTERACTIVE_SESSION_SOURCES)
    params = Stage1StartupClaimParams(scan_limit=STAGE_ONE_THREAD_SCAN_LIMIT, max_claimed=int(getattr(memories_config, 'max_rollouts_per_startup')), max_age_days=int(getattr(memories_config, 'max_rollout_age_days')), min_rollout_idle_hours=int(getattr(memories_config, 'min_rollout_idle_hours')), allowed_sources=allowed_sources, lease_seconds=STAGE_ONE_JOB_LEASE_SECONDS)
    try:
        return list(await _maybe_await(_memories_store(state_db).claim_stage1_jobs_for_startup(context.thread_id, params)))
    except Exception:
        return None


async def prune(context: MemoryStartupContext, config: Any) -> None:
    state_db = context.state_db()
    if state_db is None:
        return
    try:
        await _maybe_await(
            _memories_store(state_db).prune_stage1_outputs_for_retention(
                int(config.memories.max_unused_days),
                STAGE_ONE_PRUNE_BATCH_SIZE,
            )
        )
    except Exception:
        return


def _thread_state_db(thread: Any) -> Any:
    state_db = getattr(thread, 'state_db', None)
    if callable(state_db):
        return state_db()
    return state_db


def _claim_field(claim: Any, name: str) -> Any:
    if isinstance(claim, dict):
        return claim[name]
    return getattr(claim, name)


def _claim_thread(claim: Any) -> Any:
    return _claim_field(claim, 'thread')


def _claim_thread_field(thread: Any, name: str) -> Any:
    if isinstance(thread, dict):
        return thread[name]
    return getattr(thread, name)


def _claim_thread_updated_at_timestamp(value: Any) -> int:
    if isinstance(value, datetime):
        return int(_as_utc(value).timestamp())
    timestamp = getattr(value, 'timestamp', None)
    if callable(timestamp):
        return int(timestamp())
    return int(value)


from pycodex.memories.write.metrics import MEMORY_PHASE_ONE_E2E_MS
from pycodex.memories.write.metrics import MEMORY_PHASE_ONE_JOBS
from pycodex.memories.write.metrics import MEMORY_PHASE_ONE_OUTPUT
from pycodex.memories.write.metrics import MEMORY_PHASE_ONE_TOKEN_USAGE
from pycodex.memories.write.phase1.job import run as phase_one_job_run
from pycodex.memories.write.phase2 import _memories_store
from pycodex.memories.write.runtime import MemoryStartupContext
from pycodex.memories.write.runtime import StageOneRequestContext
from pycodex.memories.write.runtime import _maybe_await
from pycodex.memories.write.stage_one import JOB_LEASE_SECONDS as STAGE_ONE_JOB_LEASE_SECONDS
from pycodex.memories.write.stage_one import MODEL as STAGE_ONE_MODEL
from pycodex.memories.write.stage_one import PRUNE_BATCH_SIZE as STAGE_ONE_PRUNE_BATCH_SIZE
from pycodex.memories.write.stage_one import REASONING_EFFORT as STAGE_ONE_REASONING_EFFORT
from pycodex.memories.write.stage_one import THREAD_SCAN_LIMIT as STAGE_ONE_THREAD_SCAN_LIMIT
from pycodex.memories.write.storage import _as_utc
from pycodex.rollout import INTERACTIVE_SESSION_SOURCES
