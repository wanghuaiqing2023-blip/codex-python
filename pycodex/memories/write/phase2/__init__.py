"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from pycodex.protocol import AgentStatus, BaseInstructions, ContentItem, ModelInfo, Op, RateLimitSnapshot, RateLimitWindow, ReasoningEffort, ReasoningSummary, ResponseItem, TokenUsage, TruncationPolicyConfig, UserInput
from typing import Any, Callable, Iterable

@dataclass(frozen=True)
class PhaseTwoClaim:
    token: str
    watermark: int


async def run(context: MemoryStartupContext, config: Any) -> str:
    """Dependency-light projection of Rust ``src/phase2.rs::run`` orchestration."""
    context.start_timer(MEMORY_PHASE_TWO_E2E_MS)
    db = context.state_db()
    if db is None:
        return 'skipped_state_db_unavailable'
    root = memory_root(_config_codex_home(config))
    memories_config = getattr(config, 'memories', None)
    max_raw_memories = int(getattr(memories_config, 'max_raw_memories_for_consolidation', DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION))
    max_unused_days = int(getattr(memories_config, 'max_unused_days', 0))
    claim = await phase_two_claim(context, db)
    if not isinstance(claim, PhaseTwoClaim):
        reason = str(claim)
        context.counter(MEMORY_PHASE_TWO_JOBS, 1, (('status', reason),))
        return reason
    try:
        await prepare_memory_workspace(root)
    except Exception:
        await phase_two_mark_failed(context, db, claim, 'failed_prepare_workspace')
        return 'failed_prepare_workspace'
    agent_config = phase_two_agent_config(config)
    if agent_config is None:
        await phase_two_mark_failed(context, db, claim, 'failed_sandbox_policy')
        return 'failed_sandbox_policy'
    try:
        raw_memories = list(await _maybe_await(_memories_store(db).get_phase2_input_selection(max_raw_memories, max_unused_days)))
    except Exception:
        await phase_two_mark_failed(context, db, claim, 'failed_load_stage1_outputs')
        return 'failed_load_stage1_outputs'
    raw_memory_count = len(raw_memories)
    new_watermark = get_watermark(claim.watermark, raw_memories)
    try:
        await sync_phase2_workspace_inputs(root, raw_memories)
    except Exception:
        await phase_two_mark_failed(context, db, claim, 'failed_sync_workspace_inputs')
        return 'failed_sync_workspace_inputs'
    try:
        workspace_diff = await memory_workspace_diff(root)
    except Exception:
        await phase_two_mark_failed(context, db, claim, 'failed_workspace_status')
        return 'failed_workspace_status'
    if not workspace_diff.has_changes():
        await phase_two_mark_succeeded(context, db, claim, new_watermark, raw_memories, 'succeeded_no_workspace_changes')
        return 'succeeded_no_workspace_changes'
    try:
        await write_workspace_diff(root, workspace_diff)
    except Exception:
        await phase_two_mark_failed(context, db, claim, 'failed_workspace_diff_file')
        return 'failed_workspace_diff_file'
    try:
        agent = await _maybe_await(context.spawn_consolidation_agent(agent_config, phase_two_agent_prompt(root)))
    except Exception:
        await phase_two_mark_failed(context, db, claim, 'failed_spawn_agent')
        return 'failed_spawn_agent'
    status = await phase_two_handle_agent_completion(context, claim, new_watermark, raw_memories, root, agent)
    emit_metrics(context, raw_memory_count)
    return status.type


async def sync_phase2_workspace_inputs(root: str | Path, raw_memories: Iterable[Stage1Output]) -> None:
    memories = list(raw_memories)
    raw_memory_count = len(memories)
    await sync_rollout_summaries_from_memories(root, memories, raw_memory_count)
    await rebuild_raw_memories_file_from_memories(root, memories, raw_memory_count)
    await prune_old_extension_resources(root)


def get_watermark(claimed_watermark: int, latest_memories: Iterable[Stage1Output]) -> int:
    newest = max((_as_utc(memory.source_updated_at).timestamp() for memory in latest_memories), default=claimed_watermark)
    return max(int(claimed_watermark), int(newest))


def is_final_agent_status(status: AgentStatus | str | Any) -> bool:
    if isinstance(status, AgentStatus):
        status_type = status.type
    elif isinstance(status, str):
        status_type = status
    else:
        status_type = str(getattr(status, 'type', status))
    return status_type not in {'pending_init', 'running', 'interrupted'}


def emit_metrics(context: MemoryStartupContext, input_count: int) -> None:
    if input_count > 0:
        context.counter(MEMORY_PHASE_TWO_INPUT, int(input_count), ())
    context.counter(MEMORY_PHASE_TWO_JOBS, 1, (('status', 'agent_spawned'),))


def emit_token_usage_metrics(context: MemoryStartupContext, token_usage: TokenUsage) -> None:
    context.histogram(MEMORY_PHASE_TWO_TOKEN_USAGE, max(token_usage.total_tokens, 0), (('token_type', 'total'),))
    context.histogram(MEMORY_PHASE_TWO_TOKEN_USAGE, max(token_usage.input_tokens, 0), (('token_type', 'input'),))
    context.histogram(MEMORY_PHASE_TWO_TOKEN_USAGE, token_usage.cached_input(), (('token_type', 'cached_input'),))
    context.histogram(MEMORY_PHASE_TWO_TOKEN_USAGE, max(token_usage.output_tokens, 0), (('token_type', 'output'),))
    context.histogram(MEMORY_PHASE_TWO_TOKEN_USAGE, max(token_usage.reasoning_output_tokens, 0), (('token_type', 'reasoning_output'),))


def _memories_store(state_db: Any) -> Any:
    memories = getattr(state_db, 'memories', None)
    if callable(memories):
        return memories()
    if memories is not None:
        return memories
    return state_db


from pycodex.config.types import DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION
from pycodex.memories.write import memory_root
from pycodex.memories.write.extensions.prune import prune_old_extension_resources
from pycodex.memories.write.metrics import MEMORY_PHASE_TWO_E2E_MS
from pycodex.memories.write.metrics import MEMORY_PHASE_TWO_INPUT
from pycodex.memories.write.metrics import MEMORY_PHASE_TWO_JOBS
from pycodex.memories.write.metrics import MEMORY_PHASE_TWO_TOKEN_USAGE
from pycodex.memories.write.phase2.agent import get_config as phase_two_agent_config
from pycodex.memories.write.phase2.agent import get_prompt as phase_two_agent_prompt
from pycodex.memories.write.phase2.agent import handle as phase_two_handle_agent_completion
from pycodex.memories.write.phase2.job import claim as phase_two_claim
from pycodex.memories.write.phase2.job import failed as phase_two_mark_failed
from pycodex.memories.write.phase2.job import succeed as phase_two_mark_succeeded
from pycodex.memories.write.runtime import MemoryStartupContext
from pycodex.memories.write.runtime import _config_codex_home
from pycodex.memories.write.runtime import _maybe_await
from pycodex.memories.write.storage import _as_utc
from pycodex.memories.write.storage import rebuild_raw_memories_file_from_memories
from pycodex.memories.write.storage import sync_rollout_summaries_from_memories
from pycodex.memories.write.workspace import memory_workspace_diff
from pycodex.memories.write.workspace import prepare_memory_workspace
from pycodex.memories.write.workspace import write_workspace_diff
from pycodex.state import Stage1Output
