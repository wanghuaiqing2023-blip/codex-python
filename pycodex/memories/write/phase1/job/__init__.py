"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from pathlib import Path
from pycodex.core.client_common import Prompt
from pycodex.protocol import AgentStatus, BaseInstructions, ContentItem, ModelInfo, Op, RateLimitSnapshot, RateLimitWindow, ReasoningEffort, ReasoningSummary, ResponseItem, TokenUsage, TruncationPolicyConfig, UserInput
from pycodex.rollout import RolloutRecorder
from typing import Any, Callable, Iterable
import json
import re

def is_memory_excluded_contextual_user_fragment(content_item: Any) -> bool:
    text = _content_item_text(content_item)
    if text is None:
        return False
    return _matches_marked_fragment(text, '# AGENTS.md instructions for ', '</INSTRUCTIONS>') or _matches_marked_fragment(text, '<skill>', '</skill>')


def serialize_filtered_rollout_response_items(items: Iterable[Any]) -> str:
    filtered: list[Any] = []
    for item in items:
        item_mapping = _as_mapping(item)
        if item_mapping.get('kind') == 'response_item':
            item_mapping = _as_mapping(item_mapping.get('item'))
        elif item_mapping.get('type') == 'response_item' and 'payload' in item_mapping:
            item_mapping = _as_mapping(item_mapping.get('payload'))
        sanitized = sanitize_response_item_for_memories(item_mapping)
        if sanitized is not None:
            filtered.append(sanitized)
    return redact_secrets(json.dumps(filtered, separators=(',', ':'), ensure_ascii=False))


async def sample(context: MemoryStartupContext, config: Any, rollout_path: str | Path, rollout_cwd: str | Path, stage_one_context: StageOneRequestContext, *, rollout_items: Iterable[Any] | None=None, rollout_loader: Callable[[Path], Any] | None=None) -> tuple[StageOneOutput, TokenUsage | None]:
    """Dependency-light projection of Rust ``phase1.rs::job::sample``."""
    rollout_path_obj = Path(rollout_path)
    if rollout_items is None:
        if rollout_loader is None:
            rollout_loader = RolloutRecorder.load_rollout_items
        loaded = await _maybe_await(rollout_loader(rollout_path_obj))
        if isinstance(loaded, tuple):
            rollout_items = loaded[0]
        else:
            rollout_items = loaded
    rollout_contents = serialize_filtered_rollout_response_items(rollout_items or ())
    prompt = Prompt.default()
    prompt.input = [ResponseItem.message('user', (ContentItem.input_text(build_stage_one_input_message(stage_one_context.model_info, rollout_path_obj, Path(rollout_cwd), rollout_contents)),))]
    prompt.base_instructions = BaseInstructions(text=_STAGE_ONE_SYSTEM_PROMPT)
    prompt.output_schema = output_schema()
    prompt.output_schema_strict = True
    result, token_usage = await context.stream_stage_one_prompt(config, prompt, stage_one_context)
    return (_stage_one_output_from_json(result), token_usage)


def _stage_one_output_from_json(value: str) -> StageOneOutput:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f'failed to decode stage-one output: {exc}') from exc
    if not isinstance(payload, dict):
        raise TypeError('stage-one output must be a JSON object')
    expected = {'raw_memory', 'rollout_summary', 'rollout_slug'}
    missing = expected.difference(payload)
    if missing:
        raise ValueError(f"stage-one output missing fields: {', '.join(sorted(missing))}")
    extra = set(payload).difference(expected)
    if extra:
        raise ValueError(f"stage-one output has unknown fields: {', '.join(sorted(extra))}")
    raw_memory = payload['raw_memory']
    rollout_summary = payload['rollout_summary']
    rollout_slug = payload['rollout_slug']
    if not isinstance(raw_memory, str):
        raise TypeError('stage-one raw_memory must be a string')
    if not isinstance(rollout_summary, str):
        raise TypeError('stage-one rollout_summary must be a string')
    if rollout_slug is not None and (not isinstance(rollout_slug, str)):
        raise TypeError('stage-one rollout_slug must be a string or null')
    return StageOneOutput(raw_memory=redact_secrets(raw_memory), rollout_summary=redact_secrets(rollout_summary), rollout_slug=None if rollout_slug is None else redact_secrets(rollout_slug))


def sanitize_response_item_for_memories(item: Any) -> dict[str, Any] | None:
    mapping = dict(_as_mapping(item))
    if _response_item_kind(mapping) != 'message':
        return mapping if should_persist_response_item_for_memories(mapping) else None
    role = mapping.get('role')
    if role == 'developer':
        return None
    if role != 'user':
        return mapping
    content = [content_item for content_item in list(mapping.get('content') or []) if not is_memory_excluded_contextual_user_fragment(content_item)]
    if not content:
        return None
    mapping['content'] = content
    return mapping


def should_persist_response_item_for_memories(item: Any) -> bool:
    mapping = _as_mapping(item)
    kind = _response_item_kind(mapping)
    return kind in {'message', 'function_call', 'function_call_output', 'local_shell_call', 'reasoning'}


def redact_secrets(value: str) -> str:
    redacted = re.sub('sk-[A-Za-z0-9]{20,}', '[REDACTED_SECRET]', value)
    redacted = re.sub('\\bAKIA[0-9A-Z]{16}\\b', '[REDACTED_SECRET]', redacted)
    redacted = re.sub('(?i)\\bBearer\\s+[A-Za-z0-9._\\-]{16,}\\b', 'Bearer [REDACTED_SECRET]', redacted)
    redacted = re.sub('(?i)\\b(api[_-]?key|token|secret|password)\\b(\\s*[:=]\\s*)([\\"\']?)[^\\s\\"\']{8,}', '\\1\\2\\3[REDACTED_SECRET]', redacted)
    return redacted


async def run(context: MemoryStartupContext, config: Any, claim: Any, stage_one_context: StageOneRequestContext, *, sample_runner: Callable[..., Any] | None=None) -> PhaseOneJobResult:
    claimed_thread = _claim_thread(claim)
    thread_id = _claim_thread_field(claimed_thread, 'id')
    ownership_token = str(_claim_field(claim, 'ownership_token'))
    runner = sample_runner or getattr(config, 'phase_one_sample_runner', None)
    if not callable(runner):

        async def runner(run_context: MemoryStartupContext, run_config: Any, rollout_path: Path, rollout_cwd: Path, request_context: StageOneRequestContext):
            return await sample(run_context, run_config, rollout_path, rollout_cwd, request_context, rollout_loader=getattr(run_config, 'phase_one_rollout_loader', None))
    try:
        stage_one_output, token_usage = await _maybe_await(runner(context, config, Path(_claim_thread_field(claimed_thread, 'rollout_path')), Path(_claim_thread_field(claimed_thread, 'cwd')), stage_one_context))
    except Exception as exc:
        await phase_one_mark_failed(context, thread_id, ownership_token, str(exc))
        return PhaseOneJobResult('failed', None)
    if not stage_one_output.raw_memory or not stage_one_output.rollout_summary:
        return PhaseOneJobResult(await phase_one_mark_succeeded_no_output(context, thread_id, ownership_token), token_usage)
    return PhaseOneJobResult(await phase_one_mark_succeeded(context, thread_id, ownership_token, _claim_thread_updated_at_timestamp(_claim_thread_field(claimed_thread, 'updated_at')), stage_one_output.raw_memory, stage_one_output.rollout_summary, stage_one_output.rollout_slug), token_usage)


def _response_item_kind(item: dict[str, Any]) -> str:
    raw = item.get('type', item.get('kind'))
    if isinstance(raw, str):
        return raw
    if 'role' in item and 'content' in item:
        return 'message'
    if 'call_id' in item and 'output' in item:
        return 'function_call_output'
    return ''


def _content_item_text(content_item: Any) -> str | None:
    mapping = _as_mapping(content_item)
    text = mapping.get('text')
    if isinstance(text, str):
        return text
    if _response_item_kind(mapping) == 'input_text':
        value = mapping.get('value')
        return value if isinstance(value, str) else None
    return None


def _matches_marked_fragment(text: str, start_marker: str, end_marker: str) -> bool:
    left_trimmed = text.lstrip()
    starts_with_marker = left_trimmed[:len(start_marker)].lower() == start_marker.lower()
    right_trimmed = left_trimmed.rstrip()
    ends_with_marker = right_trimmed[-len(end_marker):].lower() == end_marker.lower()
    return starts_with_marker and ends_with_marker


from pycodex.memories.write.phase1 import PhaseOneJobResult
from pycodex.memories.write.phase1 import StageOneOutput
from pycodex.memories.write.phase1 import output_schema
from pycodex.memories.write.phase1 import _claim_field
from pycodex.memories.write.phase1 import _claim_thread
from pycodex.memories.write.phase1 import _claim_thread_field
from pycodex.memories.write.phase1 import _claim_thread_updated_at_timestamp
from pycodex.memories.write.phase1.job.result import failed as phase_one_mark_failed
from pycodex.memories.write.phase1.job.result import no_output as phase_one_mark_succeeded_no_output
from pycodex.memories.write.phase1.job.result import success as phase_one_mark_succeeded
from pycodex.memories.write.prompts import build_stage_one_input_message
from pycodex.memories.write.runtime import MemoryStartupContext
from pycodex.memories.write.runtime import StageOneRequestContext
from pycodex.memories.write.runtime import _as_mapping
from pycodex.memories.write.runtime import _maybe_await
from pycodex.memories.write.stage_one import PROMPT as _STAGE_ONE_SYSTEM_PROMPT
