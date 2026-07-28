"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from pathlib import Path
from pycodex.protocol import AgentStatus, BaseInstructions, ContentItem, ModelInfo, Op, RateLimitSnapshot, RateLimitWindow, ReasoningEffort, ReasoningSummary, ResponseItem, TokenUsage, TruncationPolicyConfig, UserInput
from typing import Any, Callable, Iterable
import copy
import re
from pycodex.memories.write.workspace import reset_memory_workspace_baseline

PHASE_TWO_DISABLED_FEATURES = ('SpawnCsv', 'Collab', 'MemoryTool', 'Apps', 'Plugins', 'SkillMcpDependencyInstall')


def get_config(config: Any) -> Any | None:
    root = memory_root(_config_codex_home(config))
    agent_config = copy.deepcopy(config)
    _set_field(agent_config, 'cwd', root)
    _set_field(agent_config, 'ephemeral', True)
    memories = _get_or_create_namespace(agent_config, 'memories')
    _set_field(memories, 'generate_memories', False)
    _set_field(memories, 'use_memories', False)
    _set_field(agent_config, 'include_apps_instructions', False)
    _set_field(agent_config, 'mcp_servers', {})
    permissions = _get_or_create_namespace(agent_config, 'permissions')
    _set_field(permissions, 'approval_policy', 'never')
    sandbox_policy = {'type': 'workspace_write', 'writable_roots': [root], 'network_access': False, 'exclude_tmpdir_env_var': True, 'exclude_slash_tmp': True}
    setter = getattr(permissions, 'set_legacy_sandbox_policy', None)
    if callable(setter):
        try:
            result = setter(sandbox_policy, root)
        except Exception:
            return None
        if result is False:
            return None
    _set_field(permissions, 'sandbox_policy', sandbox_policy)
    _disable_features(getattr(agent_config, 'features', None), PHASE_TWO_DISABLED_FEATURES)
    consolidation_model = getattr(memories, 'consolidation_model', None) or STAGE_TWO_MODEL
    _set_field(agent_config, 'model', consolidation_model)
    _set_field(agent_config, 'model_reasoning_effort', STAGE_TWO_REASONING_EFFORT)
    return agent_config


def get_prompt(root: str | Path) -> list[UserInput]:
    return [UserInput.text_input(build_consolidation_prompt(root))]


async def loop_agent(state_db: Any, token: str, thread: Any, *, max_status_polls: int | None=None) -> AgentStatus:
    """Dependency-light projection of Rust ``src/phase2.rs::agent::loop_agent``."""
    polls = 0
    while True:
        status = await _maybe_await(_call_or_value(getattr(thread, 'agent_status', None)))
        if not isinstance(status, AgentStatus):
            status = AgentStatus.from_mapping(status)
        if phase_two_is_final_agent_status(status):
            return status
        polls += 1
        if max_status_polls is not None and polls >= max_status_polls:
            return AgentStatus.errored(f'memory consolidation agent exited before final status: {status!r}')
        try:
            still_owned = await _maybe_await(_memories_store(state_db).heartbeat_global_phase2_job(token, STAGE_TWO_JOB_LEASE_SECONDS))
        except Exception as exc:
            return AgentStatus.errored(f'phase-2 heartbeat update failed: {exc}')
        if not bool(still_owned):
            return AgentStatus.errored('lost global phase-2 ownership during heartbeat')


async def handle(context: MemoryStartupContext, claim: PhaseTwoClaim, new_watermark: int, selected_outputs: Iterable[Any], memory_root_path: str | Path, agent: SpawnedConsolidationAgent, *, final_status: AgentStatus | None=None, reset_workspace_baseline_func: Callable[[str | Path], Any]=reset_memory_workspace_baseline) -> AgentStatus:
    """Dependency-light projection of Rust ``src/phase2.rs::agent::handle`` completion flow."""
    db = context.state_db()
    if db is None:
        return AgentStatus.not_found()
    status = final_status
    if status is None:
        status = await loop_agent(db, claim.token, agent.thread)
    if not isinstance(status, AgentStatus):
        status = AgentStatus.from_mapping(status)
    if status.type == 'completed':
        token_usage_info = await _maybe_await(_call_or_value(getattr(agent.thread, 'token_usage_info', None)))
        token_usage = getattr(token_usage_info, 'total_token_usage', token_usage_info)
        if isinstance(token_usage, TokenUsage):
            emit_phase_two_token_usage_metrics(context, token_usage)
        try:
            still_owns_lock = bool(await _maybe_await(_memories_store(db).heartbeat_global_phase2_job(claim.token, STAGE_TWO_JOB_LEASE_SECONDS)))
        except Exception:
            await phase_two_mark_failed(context, db, claim, 'failed_confirm_ownership')
            still_owns_lock = False
        if still_owns_lock:
            try:
                await _maybe_await(reset_workspace_baseline_func(memory_root_path))
            except Exception:
                await phase_two_mark_failed(context, db, claim, 'failed_workspace_commit')
            else:
                await phase_two_mark_succeeded(context, db, claim, new_watermark, selected_outputs, 'succeeded')
    else:
        await phase_two_mark_failed(context, db, claim, 'failed_agent')
    shutdown = getattr(context, 'shutdown_consolidation_agent', None)
    if callable(shutdown):
        await _maybe_await(shutdown(agent))
    return status


def _disable_features(features: Any, names: Iterable[str]) -> None:
    if features is None:
        return
    disable = getattr(features, 'disable', None)
    if callable(disable):
        for name in names:
            try:
                disable(name)
            except Exception:
                continue
        return
    if isinstance(features, dict):
        for name in names:
            features[name] = False
            features[_snake_case(name)] = False
        return
    discard = getattr(features, 'discard', None)
    if callable(discard):
        for name in names:
            discard(name)
            discard(_snake_case(name))


def _snake_case(value: str) -> str:
    return re.sub('(?<!^)([A-Z])', '_\\1', value).lower()


from pycodex.memories.write import memory_root
from pycodex.memories.write.phase2 import PhaseTwoClaim
from pycodex.memories.write.phase2 import _memories_store
from pycodex.memories.write.phase2 import emit_token_usage_metrics as emit_phase_two_token_usage_metrics
from pycodex.memories.write.phase2 import is_final_agent_status as phase_two_is_final_agent_status
from pycodex.memories.write.phase2.job import failed as phase_two_mark_failed
from pycodex.memories.write.phase2.job import succeed as phase_two_mark_succeeded
from pycodex.memories.write.prompts import build_consolidation_prompt
from pycodex.memories.write.runtime import MemoryStartupContext
from pycodex.memories.write.runtime import SpawnedConsolidationAgent
from pycodex.memories.write.runtime import _call_or_value
from pycodex.memories.write.runtime import _config_codex_home
from pycodex.memories.write.runtime import _get_or_create_namespace
from pycodex.memories.write.runtime import _maybe_await
from pycodex.memories.write.runtime import _set_field
from pycodex.memories.write.stage_two import JOB_LEASE_SECONDS as STAGE_TWO_JOB_LEASE_SECONDS
from pycodex.memories.write.stage_two import MODEL as STAGE_TWO_MODEL
from pycodex.memories.write.stage_two import REASONING_EFFORT as STAGE_TWO_REASONING_EFFORT
