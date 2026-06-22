"""Dependency-light port of Rust ``codex-memories-write`` helpers."""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import stat
from types import SimpleNamespace
from typing import Any, Callable, Iterable
from uuid import UUID

from pycodex.core.client_common import Prompt
from pycodex.core.turn_metadata import build_turn_metadata_header
from pycodex.core.compact import content_items_to_text
from pycodex.git_utils import (
    BASELINE_COMMIT_MESSAGE,
    GitBaselineDiff,
    GitToolingError,
    diff_since_latest_init,
    resolve_head,
    run_git_for_status,
)
from pycodex.protocol import (
    AgentStatus,
    BaseInstructions,
    ContentItem,
    ModelInfo,
    Op,
    RateLimitSnapshot,
    RateLimitWindow,
    ReasoningEffort,
    ReasoningSummary,
    ResponseItem,
    TokenUsage,
    TruncationPolicyConfig,
    UserInput,
)
from pycodex.rollout import RolloutRecorder
from pycodex.state import Phase2JobClaimOutcome, Phase2JobClaimed, Stage1StartupClaimParams
from pycodex.utils.output_truncation import truncate_text

RAW_MEMORIES_FILENAME = "raw_memories.md"
ROLLOUT_SUMMARIES_SUBDIR = "rollout_summaries"
EXTENSIONS_SUBDIR = "extensions"
DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION = 20
STAGE_ONE_DEFAULT_ROLLOUT_TOKEN_LIMIT = 150_000
STAGE_ONE_CONTEXT_WINDOW_PERCENT = 70
PHASE2_WORKSPACE_DIFF_FILENAME = "phase2_workspace_diff.md"
PHASE2_WORKSPACE_DIFF_MAX_BYTES = 4 * 1024 * 1024
EXTENSION_RESOURCE_RETENTION_DAYS = 7
CODEX_LIMIT_ID = "codex"
MEMORY_PHASE_ONE_JOBS = "codex.memory.phase1"
MEMORY_PHASE_ONE_E2E_MS = "codex.memory.phase1.e2e_ms"
MEMORY_PHASE_ONE_OUTPUT = "codex.memory.phase1.output"
MEMORY_PHASE_ONE_TOKEN_USAGE = "codex.memory.phase1.token_usage"
MEMORY_PHASE_TWO_JOBS = "codex.memory.phase2"
MEMORY_PHASE_TWO_E2E_MS = "codex.memory.phase2.e2e_ms"
MEMORY_PHASE_TWO_INPUT = "codex.memory.phase2.input"
MEMORY_PHASE_TWO_TOKEN_USAGE = "codex.memory.phase2.token_usage"
STAGE_ONE_JOB_LEASE_SECONDS = 3_600
STAGE_ONE_JOB_RETRY_DELAY_SECONDS = 3_600
STAGE_ONE_THREAD_SCAN_LIMIT = 5_000
STAGE_ONE_MODEL = "gpt-5.4-mini"
STAGE_ONE_REASONING_EFFORT = ReasoningEffort.LOW
STAGE_TWO_JOB_LEASE_SECONDS = 3_600
STAGE_TWO_JOB_RETRY_DELAY_SECONDS = 3_600
STAGE_TWO_MODEL = "gpt-5.4"
STAGE_TWO_REASONING_EFFORT = "medium"
INTERACTIVE_SESSION_SOURCES = ("cli", "vscode", "atlas", "chatgpt")
PHASE_TWO_DISABLED_FEATURES = (
    "SpawnCsv",
    "Collab",
    "MemoryTool",
    "Apps",
    "Plugins",
    "SkillMcpDependencyInstall",
)
_RUST_TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "codex"
    / "codex-rs"
    / "memories"
    / "write"
    / "templates"
    / "memories"
)
_STAGE_ONE_INPUT_TEMPLATE = (_RUST_TEMPLATE_ROOT / "stage_one_input.md").read_text(encoding="utf-8")
_STAGE_ONE_SYSTEM_PROMPT = (_RUST_TEMPLATE_ROOT / "stage_one_system.md").read_text(encoding="utf-8")
_CONSOLIDATION_PROMPT_TEMPLATE = (_RUST_TEMPLATE_ROOT / "consolidation.md").read_text(encoding="utf-8")
_AD_HOC_INSTRUCTIONS_TEMPLATE = (
    Path(__file__).resolve().parents[3]
    / "codex"
    / "codex-rs"
    / "memories"
    / "write"
    / "templates"
    / "extensions"
    / "ad_hoc"
    / "instructions.md"
).read_text(encoding="utf-8")
_EXTENSIONS_FOLDER_STRUCTURE_TEMPLATE = """
Memory extensions (under {{ memory_extensions_root }}/):

- <extension_name>/instructions.md
  - Source-specific guidance for interpreting additional memory signals. If an
    extension folder exists, you must read its instructions.md to determine how to use this memory
    source.

If the user has any memory extensions, you MUST read the instructions for each extension to
determine how to use the memory source. If the workspace diff shows deleted extension resource files,
remove stale memories derived only from those resources. If it has no extension folders, continue
with the standard memory inputs only.
"""
_EXTENSIONS_PRIMARY_INPUTS_TEMPLATE = """
Optional source-specific inputs:
Under `{{ memory_extensions_root }}/`:

- `<extension_name>/instructions.md`
  - If extension folders exist, read each instructions.md first and follow it when interpreting
    that extension's memory source.

If the workspace diff shows deleted memory extension resources, use that extension-specific deletion
signal to remove stale memories derived only from those resources.
"""


@dataclass(frozen=True)
class Stage1Output:
    """Python projection of Rust ``codex_state::Stage1Output``."""

    thread_id: str
    rollout_path: Path
    source_updated_at: datetime
    raw_memory: str
    rollout_summary: str
    rollout_slug: str | None
    cwd: Path
    git_branch: str | None = None
    generated_at: datetime | None = None


@dataclass(frozen=True)
class StageOneOutput:
    """Phase-1 model output payload from Rust ``src/phase1.rs``."""

    raw_memory: str
    rollout_summary: str
    rollout_slug: str | None


@dataclass
class MemorySessionTelemetry:
    """Small telemetry sink mirroring the methods used by Rust ``SessionTelemetry``."""

    model: str
    requested_model: str | None = None
    counters: list[tuple[str, int, tuple[tuple[str, str], ...]]] | None = None
    histograms: list[tuple[str, int, tuple[tuple[str, str], ...]]] | None = None
    timers: list[str] | None = None

    def clone(self) -> "MemorySessionTelemetry":
        return MemorySessionTelemetry(
            model=self.model,
            requested_model=self.requested_model,
            counters=self.counters,
            histograms=self.histograms,
            timers=self.timers,
        )

    def with_model(self, model: str, requested_model: str) -> "MemorySessionTelemetry":
        cloned = self.clone()
        cloned.model = model
        cloned.requested_model = requested_model
        return cloned

    def counter(self, name: str, inc: int, tags: Iterable[tuple[str, str]]) -> None:
        if self.counters is not None:
            self.counters.append((name, int(inc), tuple(tags)))

    def histogram(self, name: str, value: int, tags: Iterable[tuple[str, str]]) -> None:
        if self.histograms is not None:
            self.histograms.append((name, int(value), tuple(tags)))

    def start_timer(self, name: str, tags: Iterable[tuple[str, str]] = ()) -> str:
        _ = tuple(tags)
        if self.timers is not None:
            self.timers.append(name)
        return name


@dataclass(frozen=True)
class StageOneRequestContext:
    """Dependency-light projection of Rust ``StageOneRequestContext``."""

    model_info: Any
    session_telemetry: Any
    reasoning_effort: Any | None
    reasoning_summary: Any
    service_tier: str | None
    turn_metadata_header: str | None

    def start_timer(self, name: str) -> Any:
        starter = getattr(self.session_telemetry, "start_timer", None)
        if callable(starter):
            try:
                return starter(name, ())
            except TypeError:
                return starter(name)
        return None

    def counter(self, name: str, inc: int, tags: Iterable[tuple[str, str]]) -> None:
        counter = getattr(self.session_telemetry, "counter", None)
        if callable(counter):
            counter(name, int(inc), tuple(tags))

    def histogram(self, name: str, value: int, tags: Iterable[tuple[str, str]]) -> None:
        histogram = getattr(self.session_telemetry, "histogram", None)
        if callable(histogram):
            histogram(name, int(value), tuple(tags))


@dataclass
class MemoryStartupContext:
    """Dependency-light projection of Rust ``MemoryStartupContext``."""

    thread_manager: Any
    auth_manager: Any
    thread_id: Any
    thread: Any
    config: Any
    source: Any
    state_db_value: Any
    counters: list[tuple[str, int, tuple[tuple[str, str], ...]]]
    histograms: list[tuple[str, int, tuple[tuple[str, str], ...]]]
    session_telemetry: Any | None = None
    timers: list[str] | None = None

    def __post_init__(self) -> None:
        if self.timers is None:
            self.timers = []
        if self.session_telemetry is None:
            model = getattr(self.config, "model", None) or "unknown"
            self.session_telemetry = MemorySessionTelemetry(
                model=str(model),
                requested_model=str(model),
                counters=self.counters,
                histograms=self.histograms,
                timers=self.timers,
            )

    def state_db(self) -> Any:
        return self.state_db_value

    def counter(self, name: str, inc: int, tags: Iterable[tuple[str, str]]) -> None:
        counter = getattr(self.session_telemetry, "counter", None)
        if callable(counter):
            counter(name, int(inc), tuple(tags))
        else:
            self.counters.append((name, int(inc), tuple(tags)))

    def histogram(self, name: str, value: int, tags: Iterable[tuple[str, str]]) -> None:
        histogram = getattr(self.session_telemetry, "histogram", None)
        if callable(histogram):
            histogram(name, int(value), tuple(tags))
        else:
            self.histograms.append((name, int(value), tuple(tags)))

    def start_timer(self, name: str) -> Any:
        starter = getattr(self.session_telemetry, "start_timer", None)
        if callable(starter):
            try:
                return starter(name, ())
            except TypeError:
                return starter(name)
        if self.timers is not None:
            self.timers.append(name)
        return name

    async def stage_one_request_context(self, config: Any, model_name: str, reasoning_effort: Any) -> StageOneRequestContext:
        config_snapshot = await _maybe_await(_call_or_value(getattr(self.thread, "config_snapshot", None)))
        models_manager = _models_manager(self.thread_manager)
        model_info = await _maybe_await(_get_model_info(models_manager, model_name, config))
        turn_metadata_header = build_turn_metadata_header(Path(getattr(config, "cwd")))
        reasoning_summary = getattr(config, "model_reasoning_summary", None)
        if reasoning_summary is None:
            reasoning_summary = getattr(model_info, "default_reasoning_summary", ReasoningSummary.AUTO)
        session_telemetry = _telemetry_with_model(self.session_telemetry, model_name)
        return StageOneRequestContext(
            model_info=model_info,
            session_telemetry=session_telemetry,
            reasoning_effort=reasoning_effort,
            reasoning_summary=reasoning_summary,
            service_tier=getattr(config_snapshot, "service_tier", None),
            turn_metadata_header=turn_metadata_header,
        )

    async def stream_stage_one_prompt(
        self,
        config: Any,
        prompt: Any,
        context: StageOneRequestContext,
    ) -> tuple[str, TokenUsage | None]:
        client_factory = getattr(config, "model_client_factory", None) or getattr(self.auth_manager, "model_client_factory", None)
        if not callable(client_factory):
            raise RuntimeError("model client factory is required for stream_stage_one_prompt")
        config_snapshot = await _maybe_await(_call_or_value(getattr(self.thread, "config_snapshot", None)))
        model_client = await _maybe_await(
            client_factory(
                auth_manager=self.auth_manager,
                session_id=self.thread_id,
                thread_id=self.thread_id,
                config=config,
                session_source=getattr(config_snapshot, "session_source", None),
            )
        )
        client_session = await _maybe_await(_call_or_value(getattr(model_client, "new_session", None)))
        stream = await _maybe_await(
            client_session.stream(
                prompt,
                context.model_info,
                context.session_telemetry,
                context.reasoning_effort,
                context.reasoning_summary,
                context.service_tier,
                context.turn_metadata_header,
                None,
            )
        )

        result = ""
        token_usage: TokenUsage | None = None
        async for message in _async_iter(stream):
            kind = _event_kind(message)
            if kind in {"output_text_delta", "OutputTextDelta"}:
                result += str(_event_payload(message, "delta", "text", "value", default=""))
            elif kind in {"output_item_done", "OutputItemDone"}:
                item = _event_payload(message, "item", default=message)
                if result == "":
                    fallback = _response_item_text(item)
                    if fallback is not None:
                        result += fallback
            elif kind in {"completed", "Completed"}:
                usage = _event_payload(message, "token_usage", "usage", default=None)
                token_usage = usage if isinstance(usage, TokenUsage) or usage is None else TokenUsage.from_mapping(usage)
                break
        return result, token_usage

    async def spawn_consolidation_agent(self, config: Any, prompt: Iterable[UserInput]) -> "SpawnedConsolidationAgent":
        environments_getter = getattr(self.thread_manager, "default_environment_selections", None)
        environments = (
            await _maybe_await(environments_getter(getattr(config, "cwd", None)))
            if callable(environments_getter)
            else []
        )
        options = SimpleNamespace(
            config=config,
            initial_history="new",
            session_source=("internal", "memory_consolidation"),
            thread_source="memory_consolidation",
            dynamic_tools=[],
            persist_extended_history=False,
            metrics_service_name=None,
            parent_trace=None,
            environments=list(environments),
        )
        new_thread = await _maybe_await(self.thread_manager.start_thread_with_options(options))
        thread_id = _field(new_thread, "thread_id")
        thread = _field(new_thread, "thread")
        agent = SpawnedConsolidationAgent(thread_id=thread_id, thread=thread)
        try:
            await _maybe_await(
                thread.submit(
                    Op.user_input(
                        list(prompt),
                        environments=None,
                        final_output_json_schema=None,
                        responsesapi_client_metadata=None,
                        additional_context={},
                    )
                )
            )
        except Exception:
            await self.shutdown_consolidation_agent(agent)
            raise
        return agent

    async def shutdown_consolidation_agent(
        self,
        agent: "SpawnedConsolidationAgent",
        *,
        shutdown_timeout_seconds: float = 10,
    ) -> None:
        thread = agent.thread
        remover = getattr(self.thread_manager, "remove_thread", None)
        if callable(remover):
            removed = await _maybe_await(remover(agent.thread_id))
            if removed is not None:
                thread = removed
        try:
            await asyncio.wait_for(
                _maybe_await(thread.shutdown_and_wait()),
                timeout=shutdown_timeout_seconds,
            )
        except TimeoutError as exc:
            raise TimeoutError(f"memory consolidation agent {agent.thread_id} shutdown timed out") from exc


@dataclass(frozen=True)
class MemoryStartupResult:
    status: str
    memory_root: Path | None = None
    context: MemoryStartupContext | None = None


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


@dataclass(frozen=True)
class PhaseTwoClaim:
    token: str
    watermark: int


@dataclass(frozen=True)
class SpawnedConsolidationAgent:
    """Python projection of Rust ``runtime::SpawnedConsolidationAgent``."""

    thread_id: Any
    thread: Any


def memory_root(codex_home: str | Path) -> Path:
    return Path(codex_home) / "memories"


def rollout_summaries_dir(root: str | Path) -> Path:
    return Path(root) / ROLLOUT_SUMMARIES_SUBDIR


def memory_extensions_root(root: str | Path) -> Path:
    return Path(root) / EXTENSIONS_SUBDIR


def raw_memories_file(root: str | Path) -> Path:
    return Path(root) / RAW_MEMORIES_FILENAME


async def prepare_memory_workspace(root: str | Path) -> None:
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    await remove_workspace_diff(root_path)
    _ensure_memory_git_baseline(root_path)


async def memory_workspace_diff(root: str | Path) -> GitBaselineDiff:
    root_path = Path(root)
    await remove_workspace_diff(root_path)
    return diff_since_latest_init(root_path)


async def write_workspace_diff(root: str | Path, diff: GitBaselineDiff) -> None:
    path = Path(root) / PHASE2_WORKSPACE_DIFF_FILENAME
    path.write_text(render_workspace_diff_file(diff), encoding="utf-8")


async def reset_memory_workspace_baseline(root: str | Path) -> None:
    root_path = Path(root)
    await remove_workspace_diff(root_path)
    _reset_memory_git_baseline(root_path)


async def remove_workspace_diff(root: str | Path) -> None:
    path = Path(root) / PHASE2_WORKSPACE_DIFF_FILENAME
    try:
        path.unlink()
    except FileNotFoundError:
        return


async def seed_extension_instructions(memory_root_path: str | Path) -> None:
    extension_root = memory_extensions_root(memory_root_path) / "ad_hoc"
    instructions_path = extension_root / "instructions.md"
    extension_root.mkdir(parents=True, exist_ok=True)
    try:
        with instructions_path.open("x", encoding="utf-8") as file:
            file.write(_AD_HOC_INSTRUCTIONS_TEMPLATE)
    except FileExistsError:
        return


async def prune_old_extension_resources(memory_root_path: str | Path) -> None:
    await prune_old_extension_resources_with_now(memory_root_path, datetime.now(UTC))


async def prune_old_extension_resources_with_now(memory_root_path: str | Path, now: datetime) -> None:
    cutoff = _as_utc(now) - timedelta(days=EXTENSION_RESOURCE_RETENTION_DAYS)
    extensions_root = memory_extensions_root(memory_root_path)
    try:
        extension_entries = list(os.scandir(extensions_root))
    except FileNotFoundError:
        return
    except OSError:
        return

    for extension_entry in extension_entries:
        try:
            is_extension_dir = extension_entry.is_dir(follow_symlinks=False)
        except OSError:
            continue
        if not is_extension_dir:
            continue
        extension_path = Path(extension_entry.path)
        if not (extension_path / "instructions.md").exists():
            continue
        resources_path = extension_path / "resources"
        try:
            resource_entries = list(os.scandir(resources_path))
        except FileNotFoundError:
            continue
        except OSError:
            continue

        for resource_entry in resource_entries:
            try:
                is_file = resource_entry.is_file(follow_symlinks=False)
            except OSError:
                continue
            if not is_file:
                continue
            file_name = resource_entry.name
            if not file_name.endswith(".md"):
                continue
            resource_time = resource_timestamp(file_name)
            if resource_time is None or resource_time > cutoff:
                continue
            try:
                Path(resource_entry.path).unlink()
            except FileNotFoundError:
                pass
            except OSError:
                continue


def resource_timestamp(file_name: str) -> datetime | None:
    timestamp = file_name[:19]
    try:
        parsed = datetime.strptime(timestamp, "%Y-%m-%dT%H-%M-%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC)


async def start_memories_startup_task(
    thread_manager: Any,
    auth_manager: Any,
    thread_id: Any,
    thread: Any,
    config: Any,
    source: Any,
    *,
    phase1_prune: Callable[[MemoryStartupContext, Any], Any] | None = None,
    rate_limits_ok_fn: Callable[[Any, Any], Any] | None = None,
    phase1_run: Callable[[MemoryStartupContext, Any], Any] | None = None,
    phase2_run: Callable[[MemoryStartupContext, Any], Any] | None = None,
) -> MemoryStartupResult:
    state_db_value = _thread_state_db(thread)
    skip_reason = memory_startup_skip_reason(config, source, state_db_value is not None)
    if skip_reason is not None:
        return MemoryStartupResult(skip_reason)

    context = MemoryStartupContext(
        thread_manager=thread_manager,
        auth_manager=auth_manager,
        thread_id=thread_id,
        thread=thread,
        config=config,
        source=source,
        state_db_value=state_db_value,
        counters=[],
        histograms=[],
    )
    root = memory_root(_config_codex_home(config))
    root.mkdir(parents=True, exist_ok=True)
    await seed_extension_instructions(root)

    if phase1_prune is not None:
        await _maybe_await(phase1_prune(context, config))

    rate_limits_ok = True
    if rate_limits_ok_fn is not None:
        rate_limits_ok = bool(await _maybe_await(rate_limits_ok_fn(auth_manager, config)))
    if not rate_limits_ok:
        context.counter("memory_startup", 1, (("status", "skipped_rate_limit"),))
        return MemoryStartupResult("skipped_rate_limit", root, context)

    if phase1_run is not None:
        await _maybe_await(phase1_run(context, config))
    if phase2_run is not None:
        await _maybe_await(phase2_run(context, config))
    return MemoryStartupResult("completed", root, context)


def memory_startup_skip_reason(config: Any, source: Any, state_db_available: bool) -> str | None:
    if bool(getattr(config, "ephemeral", False)):
        return "skipped_ephemeral"
    if not _memory_feature_enabled(config):
        return "skipped_feature_disabled"
    if _source_is_non_root_agent(source):
        return "skipped_non_root_agent"
    if not state_db_available:
        return "skipped_state_db_unavailable"
    return None


def phase_one_output_schema() -> dict[str, Any]:
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


def is_memory_excluded_contextual_user_fragment(content_item: Any) -> bool:
    text = _content_item_text(content_item)
    if text is None:
        return False
    return _matches_marked_fragment(text, "# AGENTS.md instructions for ", "</INSTRUCTIONS>") or _matches_marked_fragment(
        text,
        "<skill>",
        "</skill>",
    )


def serialize_filtered_rollout_response_items(items: Iterable[Any]) -> str:
    filtered: list[Any] = []
    for item in items:
        item_mapping = _as_mapping(item)
        if item_mapping.get("kind") == "response_item":
            item_mapping = _as_mapping(item_mapping.get("item"))
        elif item_mapping.get("type") == "response_item" and "payload" in item_mapping:
            item_mapping = _as_mapping(item_mapping.get("payload"))
        sanitized = sanitize_response_item_for_memories(item_mapping)
        if sanitized is not None:
            filtered.append(sanitized)
    return redact_secrets(json.dumps(filtered, separators=(",", ":"), ensure_ascii=False))


async def phase_one_sample(
    context: MemoryStartupContext,
    config: Any,
    rollout_path: str | Path,
    rollout_cwd: str | Path,
    stage_one_context: StageOneRequestContext,
    *,
    rollout_items: Iterable[Any] | None = None,
    rollout_loader: Callable[[Path], Any] | None = None,
) -> tuple[StageOneOutput, TokenUsage | None]:
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
    prompt.input = [
        ResponseItem.message(
            "user",
            (
                ContentItem.input_text(
                    build_stage_one_input_message(
                        stage_one_context.model_info,
                        rollout_path_obj,
                        Path(rollout_cwd),
                        rollout_contents,
                    )
                ),
            ),
        )
    ]
    prompt.base_instructions = BaseInstructions(text=_STAGE_ONE_SYSTEM_PROMPT)
    prompt.output_schema = phase_one_output_schema()
    prompt.output_schema_strict = True

    result, token_usage = await context.stream_stage_one_prompt(config, prompt, stage_one_context)
    return _stage_one_output_from_json(result), token_usage


def _stage_one_output_from_json(value: str) -> StageOneOutput:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"failed to decode stage-one output: {exc}") from exc
    if not isinstance(payload, dict):
        raise TypeError("stage-one output must be a JSON object")

    expected = {"raw_memory", "rollout_summary", "rollout_slug"}
    missing = expected.difference(payload)
    if missing:
        raise ValueError(f"stage-one output missing fields: {', '.join(sorted(missing))}")
    extra = set(payload).difference(expected)
    if extra:
        raise ValueError(f"stage-one output has unknown fields: {', '.join(sorted(extra))}")

    raw_memory = payload["raw_memory"]
    rollout_summary = payload["rollout_summary"]
    rollout_slug = payload["rollout_slug"]
    if not isinstance(raw_memory, str):
        raise TypeError("stage-one raw_memory must be a string")
    if not isinstance(rollout_summary, str):
        raise TypeError("stage-one rollout_summary must be a string")
    if rollout_slug is not None and not isinstance(rollout_slug, str):
        raise TypeError("stage-one rollout_slug must be a string or null")

    return StageOneOutput(
        raw_memory=redact_secrets(raw_memory),
        rollout_summary=redact_secrets(rollout_summary),
        rollout_slug=None if rollout_slug is None else redact_secrets(rollout_slug),
    )


def sanitize_response_item_for_memories(item: Any) -> dict[str, Any] | None:
    mapping = dict(_as_mapping(item))
    if _response_item_kind(mapping) != "message":
        return mapping if should_persist_response_item_for_memories(mapping) else None

    role = mapping.get("role")
    if role == "developer":
        return None
    if role != "user":
        return mapping

    content = [
        content_item
        for content_item in list(mapping.get("content") or [])
        if not is_memory_excluded_contextual_user_fragment(content_item)
    ]
    if not content:
        return None
    mapping["content"] = content
    return mapping


def should_persist_response_item_for_memories(item: Any) -> bool:
    mapping = _as_mapping(item)
    kind = _response_item_kind(mapping)
    return kind in {
        "message",
        "function_call",
        "function_call_output",
        "local_shell_call",
        "reasoning",
    }


def redact_secrets(value: str) -> str:
    redacted = re.sub(r"sk-[A-Za-z0-9]{20,}", "[REDACTED_SECRET]", value)
    redacted = re.sub(r"\bAKIA[0-9A-Z]{16}\b", "[REDACTED_SECRET]", redacted)
    redacted = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{16,}\b", "Bearer [REDACTED_SECRET]", redacted)
    redacted = re.sub(
        r"(?i)\b(api[_-]?key|token|secret|password)\b(\s*[:=]\s*)([\"']?)[^\s\"']{8,}",
        r"\1\2\3[REDACTED_SECRET]",
        redacted,
    )
    return redacted


def aggregate_phase_one_stats(outcomes: Iterable[PhaseOneJobResult]) -> PhaseOneStats:
    results = list(outcomes)
    succeeded_with_output = sum(1 for result in results if result.outcome == "succeeded_with_output")
    succeeded_no_output = sum(1 for result in results if result.outcome == "succeeded_no_output")
    failed = sum(1 for result in results if result.outcome == "failed")
    total_usage = TokenUsage()
    has_usage = False
    for result in results:
        if result.token_usage is not None:
            total_usage = total_usage.add(result.token_usage)
            has_usage = True
    return PhaseOneStats(
        claimed=len(results),
        succeeded_with_output=succeeded_with_output,
        succeeded_no_output=succeeded_no_output,
        failed=failed,
        total_token_usage=total_usage if has_usage else None,
    )


def emit_phase_one_metrics(context: StageOneRequestContext, counts: PhaseOneStats) -> None:
    if counts.claimed > 0:
        context.counter(MEMORY_PHASE_ONE_JOBS, counts.claimed, (("status", "claimed"),))
    if counts.succeeded_with_output > 0:
        context.counter(MEMORY_PHASE_ONE_JOBS, counts.succeeded_with_output, (("status", "succeeded"),))
        context.counter(MEMORY_PHASE_ONE_OUTPUT, counts.succeeded_with_output, ())
    if counts.succeeded_no_output > 0:
        context.counter(
            MEMORY_PHASE_ONE_JOBS,
            counts.succeeded_no_output,
            (("status", "succeeded_no_output"),),
        )
    if counts.failed > 0:
        context.counter(MEMORY_PHASE_ONE_JOBS, counts.failed, (("status", "failed"),))
    token_usage = counts.total_token_usage
    if token_usage is not None:
        context.histogram(MEMORY_PHASE_ONE_TOKEN_USAGE, max(token_usage.total_tokens, 0), (("token_type", "total"),))
        context.histogram(MEMORY_PHASE_ONE_TOKEN_USAGE, max(token_usage.input_tokens, 0), (("token_type", "input"),))
        context.histogram(MEMORY_PHASE_ONE_TOKEN_USAGE, token_usage.cached_input(), (("token_type", "cached_input"),))
        context.histogram(MEMORY_PHASE_ONE_TOKEN_USAGE, max(token_usage.output_tokens, 0), (("token_type", "output"),))
        context.histogram(
            MEMORY_PHASE_ONE_TOKEN_USAGE,
            max(token_usage.reasoning_output_tokens, 0),
            (("token_type", "reasoning_output"),),
        )


async def phase_one_run(
    context: MemoryStartupContext,
    config: Any,
    *,
    job_runner: Callable[[MemoryStartupContext, Any, Any, StageOneRequestContext], Any] | None = None,
) -> PhaseOneStats | None:
    memories_config = getattr(config, "memories")
    model_name = getattr(memories_config, "extract_model", None) or STAGE_ONE_MODEL
    stage_one_context = await _maybe_await(
        context.stage_one_request_context(config, model_name, STAGE_ONE_REASONING_EFFORT)
    )
    stage_one_context.start_timer(MEMORY_PHASE_ONE_E2E_MS)

    claimed_candidates = await phase_one_claim_startup_jobs(context, memories_config)
    if claimed_candidates is None:
        return None
    if not claimed_candidates:
        stage_one_context.counter(MEMORY_PHASE_ONE_JOBS, 1, (("status", "skipped_no_candidates"),))
        return PhaseOneStats(0, 0, 0, 0, None)

    runner = job_runner or getattr(config, "phase_one_job_runner", None) or phase_one_job_run

    outcomes = [
        await _maybe_await(runner(context, config, claim, stage_one_context))
        for claim in claimed_candidates
    ]
    stats = aggregate_phase_one_stats(outcomes)
    emit_phase_one_metrics(stage_one_context, stats)
    return stats


async def phase_one_job_run(
    context: MemoryStartupContext,
    config: Any,
    claim: Any,
    stage_one_context: StageOneRequestContext,
    *,
    sample_runner: Callable[..., Any] | None = None,
) -> PhaseOneJobResult:
    claimed_thread = _claim_thread(claim)
    thread_id = _claim_thread_field(claimed_thread, "id")
    ownership_token = str(_claim_field(claim, "ownership_token"))
    runner = sample_runner or getattr(config, "phase_one_sample_runner", None)
    if not callable(runner):
        async def runner(run_context: MemoryStartupContext, run_config: Any, rollout_path: Path, rollout_cwd: Path, request_context: StageOneRequestContext):
            return await phase_one_sample(
                run_context,
                run_config,
                rollout_path,
                rollout_cwd,
                request_context,
                rollout_loader=getattr(run_config, "phase_one_rollout_loader", None),
            )

    try:
        stage_one_output, token_usage = await _maybe_await(
            runner(
                context,
                config,
                Path(_claim_thread_field(claimed_thread, "rollout_path")),
                Path(_claim_thread_field(claimed_thread, "cwd")),
                stage_one_context,
            )
        )
    except Exception as exc:
        await phase_one_mark_failed(context, thread_id, ownership_token, str(exc))
        return PhaseOneJobResult("failed", None)

    if not stage_one_output.raw_memory or not stage_one_output.rollout_summary:
        return PhaseOneJobResult(
            await phase_one_mark_succeeded_no_output(context, thread_id, ownership_token),
            token_usage,
        )

    return PhaseOneJobResult(
        await phase_one_mark_succeeded(
            context,
            thread_id,
            ownership_token,
            _claim_thread_updated_at_timestamp(_claim_thread_field(claimed_thread, "updated_at")),
            stage_one_output.raw_memory,
            stage_one_output.rollout_summary,
            stage_one_output.rollout_slug,
        ),
        token_usage,
    )


async def phase_one_claim_startup_jobs(context: MemoryStartupContext, memories_config: Any) -> list[Any] | None:
    state_db = context.state_db()
    if state_db is None:
        return None
    params = Stage1StartupClaimParams(
        scan_limit=STAGE_ONE_THREAD_SCAN_LIMIT,
        max_claimed=int(getattr(memories_config, "max_rollouts_per_startup")),
        max_age_days=int(getattr(memories_config, "max_rollout_age_days")),
        min_rollout_idle_hours=int(getattr(memories_config, "min_rollout_idle_hours")),
        allowed_sources=INTERACTIVE_SESSION_SOURCES,
        lease_seconds=STAGE_ONE_JOB_LEASE_SECONDS,
    )
    try:
        return list(
            await _maybe_await(
                _memories_store(state_db).claim_stage1_jobs_for_startup(context.thread_id, params)
            )
        )
    except Exception:
        return None


async def phase_one_mark_failed(
    context: MemoryStartupContext,
    thread_id: Any,
    ownership_token: str,
    reason: str,
) -> None:
    state_db = context.state_db()
    if state_db is None:
        return
    try:
        await _maybe_await(
            _memories_store(state_db).mark_stage1_job_failed(
                thread_id,
                ownership_token,
                reason,
                STAGE_ONE_JOB_RETRY_DELAY_SECONDS,
            )
        )
    except Exception:
        return


async def phase_one_mark_succeeded_no_output(
    context: MemoryStartupContext,
    thread_id: Any,
    ownership_token: str,
) -> str:
    state_db = context.state_db()
    if state_db is None:
        return "failed"
    try:
        ok = await _maybe_await(_memories_store(state_db).mark_stage1_job_succeeded_no_output(thread_id, ownership_token))
    except Exception:
        ok = False
    return "succeeded_no_output" if bool(ok) else "failed"


async def phase_one_mark_succeeded(
    context: MemoryStartupContext,
    thread_id: Any,
    ownership_token: str,
    source_updated_at: int,
    raw_memory: str,
    rollout_summary: str,
    rollout_slug: str | None,
) -> str:
    state_db = context.state_db()
    if state_db is None:
        return "failed"
    try:
        ok = await _maybe_await(
            _memories_store(state_db).mark_stage1_job_succeeded(
                thread_id,
                ownership_token,
                int(source_updated_at),
                raw_memory,
                rollout_summary,
                rollout_slug,
            )
        )
    except Exception:
        ok = False
    return "succeeded_with_output" if bool(ok) else "failed"


async def phase_two_claim(context: MemoryStartupContext, state_db: Any | None = None) -> PhaseTwoClaim | str:
    db = state_db if state_db is not None else context.state_db()
    if db is None:
        return "failed_claim"
    try:
        outcome = await _maybe_await(
            _memories_store(db).try_claim_global_phase2_job(context.thread_id, STAGE_TWO_JOB_LEASE_SECONDS)
        )
    except Exception:
        return "failed_claim"
    if isinstance(outcome, Phase2JobClaimed) or _has_attrs(outcome, "ownership_token", "input_watermark"):
        context.counter(MEMORY_PHASE_TWO_JOBS, 1, (("status", "claimed"),))
        return PhaseTwoClaim(token=str(getattr(outcome, "ownership_token")), watermark=int(getattr(outcome, "input_watermark")))
    if outcome is Phase2JobClaimOutcome.SKIPPED_RETRY_UNAVAILABLE or str(outcome).endswith("skipped_retry_unavailable"):
        return "skipped_retry_unavailable"
    if outcome is Phase2JobClaimOutcome.SKIPPED_COOLDOWN or str(outcome).endswith("skipped_cooldown"):
        return "skipped_cooldown"
    if outcome is Phase2JobClaimOutcome.SKIPPED_RUNNING or str(outcome).endswith("skipped_running"):
        return "skipped_running"
    return "failed_claim"


async def phase_two_mark_failed(context: MemoryStartupContext, state_db: Any, claim: PhaseTwoClaim, reason: str) -> None:
    context.counter(MEMORY_PHASE_TWO_JOBS, 1, (("status", reason),))
    store = _memories_store(state_db)
    try:
        ok = await _maybe_await(
            store.mark_global_phase2_job_failed(
                claim.token,
                reason,
                STAGE_TWO_JOB_RETRY_DELAY_SECONDS,
            )
        )
    except Exception:
        ok = False
    if bool(ok):
        return
    fallback = getattr(store, "mark_global_phase2_job_failed_if_unowned", None)
    if callable(fallback):
        try:
            await _maybe_await(fallback(claim.token, reason, STAGE_TWO_JOB_RETRY_DELAY_SECONDS))
        except Exception:
            return


async def phase_two_mark_succeeded(
    context: MemoryStartupContext,
    state_db: Any,
    claim: PhaseTwoClaim,
    completion_watermark: int,
    selected_outputs: Iterable[Any],
    reason: str,
) -> bool:
    context.counter(MEMORY_PHASE_TWO_JOBS, 1, (("status", reason),))
    try:
        return bool(
            await _maybe_await(
                _memories_store(state_db).mark_global_phase2_job_succeeded(
                    claim.token,
                    int(completion_watermark),
                    list(selected_outputs),
                )
            )
        )
    except Exception:
        return False


async def phase_two_run(context: MemoryStartupContext, config: Any) -> str:
    """Dependency-light projection of Rust ``src/phase2.rs::run`` orchestration."""

    context.start_timer(MEMORY_PHASE_TWO_E2E_MS)
    db = context.state_db()
    if db is None:
        return "skipped_state_db_unavailable"

    root = memory_root(_config_codex_home(config))
    memories_config = getattr(config, "memories", None)
    max_raw_memories = int(
        getattr(memories_config, "max_raw_memories_for_consolidation", DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION)
    )
    max_unused_days = int(getattr(memories_config, "max_unused_days", 0))

    claim = await phase_two_claim(context, db)
    if not isinstance(claim, PhaseTwoClaim):
        reason = str(claim)
        context.counter(MEMORY_PHASE_TWO_JOBS, 1, (("status", reason),))
        return reason

    try:
        await prepare_memory_workspace(root)
    except Exception:
        await phase_two_mark_failed(context, db, claim, "failed_prepare_workspace")
        return "failed_prepare_workspace"

    agent_config = phase_two_agent_config(config)
    if agent_config is None:
        await phase_two_mark_failed(context, db, claim, "failed_sandbox_policy")
        return "failed_sandbox_policy"

    try:
        raw_memories = list(
            await _maybe_await(
                _memories_store(db).get_phase2_input_selection(
                    max_raw_memories,
                    max_unused_days,
                )
            )
        )
    except Exception:
        await phase_two_mark_failed(context, db, claim, "failed_load_stage1_outputs")
        return "failed_load_stage1_outputs"

    raw_memory_count = len(raw_memories)
    new_watermark = phase_two_get_watermark(claim.watermark, raw_memories)

    try:
        await sync_phase2_workspace_inputs(root, raw_memories)
    except Exception:
        await phase_two_mark_failed(context, db, claim, "failed_sync_workspace_inputs")
        return "failed_sync_workspace_inputs"

    try:
        workspace_diff = await memory_workspace_diff(root)
    except Exception:
        await phase_two_mark_failed(context, db, claim, "failed_workspace_status")
        return "failed_workspace_status"

    if not workspace_diff.has_changes():
        await phase_two_mark_succeeded(
            context,
            db,
            claim,
            new_watermark,
            raw_memories,
            "succeeded_no_workspace_changes",
        )
        return "succeeded_no_workspace_changes"

    try:
        await write_workspace_diff(root, workspace_diff)
    except Exception:
        await phase_two_mark_failed(context, db, claim, "failed_workspace_diff_file")
        return "failed_workspace_diff_file"

    try:
        agent = await _maybe_await(context.spawn_consolidation_agent(agent_config, phase_two_agent_prompt(root)))
    except Exception:
        await phase_two_mark_failed(context, db, claim, "failed_spawn_agent")
        return "failed_spawn_agent"

    status = await phase_two_handle_agent_completion(
        context,
        claim,
        new_watermark,
        raw_memories,
        root,
        agent,
    )
    emit_phase_two_metrics(context, raw_memory_count)
    return status.type


def phase_two_agent_config(config: Any) -> Any | None:
    root = memory_root(_config_codex_home(config))
    agent_config = copy.deepcopy(config)
    _set_field(agent_config, "cwd", root)

    # Consolidation threads must never feed back into phase-1 memory generation.
    _set_field(agent_config, "ephemeral", True)
    memories = _get_or_create_namespace(agent_config, "memories")
    _set_field(memories, "generate_memories", False)
    _set_field(memories, "use_memories", False)
    _set_field(agent_config, "include_apps_instructions", False)
    _set_field(agent_config, "mcp_servers", {})

    permissions = _get_or_create_namespace(agent_config, "permissions")
    _set_field(permissions, "approval_policy", "never")
    sandbox_policy = {
        "type": "workspace_write",
        "writable_roots": [root],
        "network_access": False,
        "exclude_tmpdir_env_var": True,
        "exclude_slash_tmp": True,
    }
    setter = getattr(permissions, "set_legacy_sandbox_policy", None)
    if callable(setter):
        try:
            result = setter(sandbox_policy, root)
        except Exception:
            return None
        if result is False:
            return None
    _set_field(permissions, "sandbox_policy", sandbox_policy)

    _disable_features(getattr(agent_config, "features", None), PHASE_TWO_DISABLED_FEATURES)
    consolidation_model = getattr(memories, "consolidation_model", None) or STAGE_TWO_MODEL
    _set_field(agent_config, "model", consolidation_model)
    _set_field(agent_config, "model_reasoning_effort", STAGE_TWO_REASONING_EFFORT)
    return agent_config


def phase_two_agent_prompt(root: str | Path) -> list[UserInput]:
    return [UserInput.text_input(build_consolidation_prompt(root))]


async def sync_phase2_workspace_inputs(root: str | Path, raw_memories: Iterable[Stage1Output]) -> None:
    memories = list(raw_memories)
    raw_memory_count = len(memories)
    await sync_rollout_summaries_from_memories(root, memories, raw_memory_count)
    await rebuild_raw_memories_file_from_memories(root, memories, raw_memory_count)
    await prune_old_extension_resources(root)


def phase_two_get_watermark(claimed_watermark: int, latest_memories: Iterable[Stage1Output]) -> int:
    newest = max((_as_utc(memory.source_updated_at).timestamp() for memory in latest_memories), default=claimed_watermark)
    return max(int(claimed_watermark), int(newest))


def phase_two_is_final_agent_status(status: AgentStatus | str | Any) -> bool:
    if isinstance(status, AgentStatus):
        status_type = status.type
    elif isinstance(status, str):
        status_type = status
    else:
        status_type = str(getattr(status, "type", status))
    return status_type not in {"pending_init", "running", "interrupted"}


async def phase_two_loop_agent(
    state_db: Any,
    token: str,
    thread: Any,
    *,
    max_status_polls: int | None = None,
) -> AgentStatus:
    """Dependency-light projection of Rust ``src/phase2.rs::agent::loop_agent``."""

    polls = 0
    while True:
        status = await _maybe_await(_call_or_value(getattr(thread, "agent_status", None)))
        if not isinstance(status, AgentStatus):
            status = AgentStatus.from_mapping(status)
        if phase_two_is_final_agent_status(status):
            return status

        polls += 1
        if max_status_polls is not None and polls >= max_status_polls:
            return AgentStatus.errored(f"memory consolidation agent exited before final status: {status!r}")

        try:
            still_owned = await _maybe_await(
                _memories_store(state_db).heartbeat_global_phase2_job(
                    token,
                    STAGE_TWO_JOB_LEASE_SECONDS,
                )
            )
        except Exception as exc:
            return AgentStatus.errored(f"phase-2 heartbeat update failed: {exc}")
        if not bool(still_owned):
            return AgentStatus.errored("lost global phase-2 ownership during heartbeat")


async def phase_two_handle_agent_completion(
    context: MemoryStartupContext,
    claim: PhaseTwoClaim,
    new_watermark: int,
    selected_outputs: Iterable[Any],
    memory_root_path: str | Path,
    agent: SpawnedConsolidationAgent,
    *,
    final_status: AgentStatus | None = None,
    reset_workspace_baseline_func: Callable[[str | Path], Any] = reset_memory_workspace_baseline,
) -> AgentStatus:
    """Dependency-light projection of Rust ``src/phase2.rs::agent::handle`` completion flow."""

    db = context.state_db()
    if db is None:
        return AgentStatus.not_found()

    status = final_status
    if status is None:
        status = await phase_two_loop_agent(db, claim.token, agent.thread)

    if not isinstance(status, AgentStatus):
        status = AgentStatus.from_mapping(status)

    if status.type == "completed":
        token_usage_info = await _maybe_await(_call_or_value(getattr(agent.thread, "token_usage_info", None)))
        token_usage = getattr(token_usage_info, "total_token_usage", token_usage_info)
        if isinstance(token_usage, TokenUsage):
            emit_phase_two_token_usage_metrics(context, token_usage)

        try:
            still_owns_lock = bool(
                await _maybe_await(
                    _memories_store(db).heartbeat_global_phase2_job(
                        claim.token,
                        STAGE_TWO_JOB_LEASE_SECONDS,
                    )
                )
            )
        except Exception:
            await phase_two_mark_failed(context, db, claim, "failed_confirm_ownership")
            still_owns_lock = False

        if still_owns_lock:
            try:
                await _maybe_await(reset_workspace_baseline_func(memory_root_path))
            except Exception:
                await phase_two_mark_failed(context, db, claim, "failed_workspace_commit")
            else:
                await phase_two_mark_succeeded(
                    context,
                    db,
                    claim,
                    new_watermark,
                    selected_outputs,
                    "succeeded",
                )
    else:
        await phase_two_mark_failed(context, db, claim, "failed_agent")

    shutdown = getattr(context, "shutdown_consolidation_agent", None)
    if callable(shutdown):
        await _maybe_await(shutdown(agent))
    return status


def emit_phase_two_metrics(context: MemoryStartupContext, input_count: int) -> None:
    if input_count > 0:
        context.counter(MEMORY_PHASE_TWO_INPUT, int(input_count), ())
    context.counter(MEMORY_PHASE_TWO_JOBS, 1, (("status", "agent_spawned"),))


def emit_phase_two_token_usage_metrics(context: MemoryStartupContext, token_usage: TokenUsage) -> None:
    context.histogram(MEMORY_PHASE_TWO_TOKEN_USAGE, max(token_usage.total_tokens, 0), (("token_type", "total"),))
    context.histogram(MEMORY_PHASE_TWO_TOKEN_USAGE, max(token_usage.input_tokens, 0), (("token_type", "input"),))
    context.histogram(
        MEMORY_PHASE_TWO_TOKEN_USAGE,
        token_usage.cached_input(),
        (("token_type", "cached_input"),),
    )
    context.histogram(MEMORY_PHASE_TWO_TOKEN_USAGE, max(token_usage.output_tokens, 0), (("token_type", "output"),))
    context.histogram(
        MEMORY_PHASE_TWO_TOKEN_USAGE,
        max(token_usage.reasoning_output_tokens, 0),
        (("token_type", "reasoning_output"),),
    )


def render_workspace_diff_file(diff: GitBaselineDiff) -> str:
    rendered = (
        "# Memory Workspace Diff\n\n"
        "Generated by Codex before Phase 2 memory consolidation. Read this file first and do not edit it.\n\n"
        "## Status\n"
    )
    if not diff.has_changes():
        return rendered + "- none\n"

    for change in diff.changes:
        rendered += f"- {change.status.label()} {change.path}\n"
    rendered += "\n## Diff\n\n```diff\n"
    rendered = _append_bounded_diff(rendered, diff.unified_diff)
    rendered += "```\n"
    return rendered


def previous_char_boundary(value: str, max_bytes: int) -> int:
    encoded = value.encode("utf-8")
    if max_bytes >= len(encoded):
        return len(encoded)
    index = max(0, int(max_bytes))
    while index > 0:
        try:
            encoded[:index].decode("utf-8")
            return index
        except UnicodeDecodeError:
            index -= 1
    return 0


def _ensure_memory_git_baseline(root: Path) -> None:
    if (root / ".git").is_dir():
        try:
            if (root / ".git" / "HEAD").is_file() and resolve_head(root) is not None:
                run_git_for_status(root, ("read-tree", "--reset", "HEAD"))
                return
        except GitToolingError:
            pass
    _reset_memory_git_baseline(root)


def _reset_memory_git_baseline(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _remove_memory_git_metadata(root)
    run_git_for_status(root, ("init",))
    run_git_for_status(root, ("config", "core.autocrlf", "false"))
    run_git_for_status(root, ("add", "-A"))
    run_git_for_status(
        root,
        (
            "-c",
            "user.name=Codex",
            "-c",
            "user.email=noreply@openai.com",
            "commit",
            "--allow-empty",
            "-m",
            BASELINE_COMMIT_MESSAGE,
        ),
        env=(
            ("GIT_AUTHOR_NAME", "Codex"),
            ("GIT_AUTHOR_EMAIL", "noreply@openai.com"),
            ("GIT_COMMITTER_NAME", "Codex"),
            ("GIT_COMMITTER_EMAIL", "noreply@openai.com"),
        ),
    )
    run_git_for_status(root, ("read-tree", "--reset", "HEAD"))


def _remove_memory_git_metadata(root: Path) -> None:
    git_path = root / ".git"
    try:
        git_path.lstat()
    except FileNotFoundError:
        return
    if git_path.is_dir() and not git_path.is_symlink():
        shutil.rmtree(git_path, onerror=_make_writable_and_retry)
    else:
        git_path.unlink()


def _make_writable_and_retry(function, path: str, _exc_info) -> None:
    try:
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
    except OSError:
        pass
    function(path)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _thread_state_db(thread: Any) -> Any:
    state_db = getattr(thread, "state_db", None)
    if callable(state_db):
        return state_db()
    return state_db


def _memories_store(state_db: Any) -> Any:
    memories = getattr(state_db, "memories", None)
    if callable(memories):
        return memories()
    if memories is not None:
        return memories
    return state_db


def _has_attrs(value: Any, *names: str) -> bool:
    return all(hasattr(value, name) for name in names)


async def _auth_manager_auth(auth_manager: Any) -> Any | None:
    auth_method = getattr(auth_manager, "auth", None)
    if callable(auth_method):
        return await _maybe_await(auth_method())
    current = getattr(auth_manager, "current_auth", None)
    if callable(current):
        return await _maybe_await(current())
    if current is not None:
        return current
    return getattr(auth_manager, "auth_value", None)


async def _uses_codex_backend(auth: Any) -> bool:
    uses = getattr(auth, "uses_codex_backend", None)
    if callable(uses):
        return bool(await _maybe_await(uses()))
    if uses is not None:
        return bool(uses)
    return bool(getattr(auth, "uses_codex_backend_value", False))


async def _backend_client_from_auth(auth_manager: Any, config: Any, auth: Any) -> Any | None:
    factory = (
        getattr(config, "backend_client_factory", None)
        or getattr(auth_manager, "backend_client_factory", None)
        or getattr(auth, "backend_client_factory", None)
    )
    if callable(factory):
        base_url = getattr(config, "chatgpt_base_url", None)
        for args in ((base_url, auth), (auth,), (config, auth), ()):
            try:
                return await _maybe_await(factory(*args))
            except TypeError:
                continue
            except Exception:
                return None
        return None
    if callable(getattr(auth_manager, "get_rate_limits_many", None)):
        return auth_manager
    if callable(getattr(auth, "get_rate_limits_many", None)):
        return auth
    return None


def _rate_limit_snapshot(value: Any) -> RateLimitSnapshot:
    if isinstance(value, RateLimitSnapshot):
        return value
    if isinstance(value, dict):
        return RateLimitSnapshot.from_mapping(value)
    return RateLimitSnapshot.from_mapping(vars(value))


def _claim_field(claim: Any, name: str) -> Any:
    if isinstance(claim, dict):
        return claim[name]
    return getattr(claim, name)


def _claim_thread(claim: Any) -> Any:
    return _claim_field(claim, "thread")


def _claim_thread_field(thread: Any, name: str) -> Any:
    if isinstance(thread, dict):
        return thread[name]
    return getattr(thread, name)


def _claim_thread_updated_at_timestamp(value: Any) -> int:
    if isinstance(value, datetime):
        return int(_as_utc(value).timestamp())
    timestamp = getattr(value, "timestamp", None)
    if callable(timestamp):
        return int(timestamp())
    return int(value)


def _get_or_create_namespace(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        existing = value.get(name)
        if existing is None:
            existing = {}
            value[name] = existing
        return existing
    existing = getattr(value, name, None)
    if existing is None:
        existing = SimpleNamespace()
        setattr(value, name, existing)
    return existing


def _set_field(value: Any, name: str, field_value: Any) -> None:
    if isinstance(value, dict):
        value[name] = field_value
    else:
        setattr(value, name, field_value)


def _field(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value[name]
    return getattr(value, name)


async def _async_iter(value: Any):
    if hasattr(value, "__aiter__"):
        async for item in value:
            yield item
        return
    for item in value:
        yield await _maybe_await(item)


def _event_kind(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("type") or value.get("kind") or value.get("event"))
    return str(getattr(value, "type", getattr(value, "kind", value.__class__.__name__)))


def _event_payload(value: Any, *names: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        for name in names:
            if name in value:
                return value[name]
        return default
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _response_item_text(value: Any) -> str | None:
    item = value if isinstance(value, ResponseItem) else None
    if item is None:
        try:
            item = ResponseItem.from_mapping(value)
        except Exception:
            item = None
    if item is not None:
        if item.type == "message":
            return content_items_to_text(item.content)
        return None

    item_type = _event_payload(value, "type", default=None)
    role = _event_payload(value, "role", default=None)
    content = _event_payload(value, "content", default=())
    if item_type == "message" and role in {None, "assistant"}:
        pieces: list[str] = []
        for entry in content or ():
            if isinstance(entry, ContentItem):
                if entry.type in {"input_text", "output_text"} and entry.text:
                    pieces.append(entry.text)
            elif isinstance(entry, dict) and entry.get("type") in {"input_text", "output_text"} and entry.get("text"):
                pieces.append(str(entry["text"]))
        return "\n".join(pieces) if pieces else None
    return None


def _disable_features(features: Any, names: Iterable[str]) -> None:
    if features is None:
        return
    disable = getattr(features, "disable", None)
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
    discard = getattr(features, "discard", None)
    if callable(discard):
        for name in names:
            discard(name)
            discard(_snake_case(name))


def _snake_case(value: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", value).lower()


def _call_or_value(value: Any) -> Any:
    if callable(value):
        return value()
    return value


def _models_manager(thread_manager: Any) -> Any:
    getter = getattr(thread_manager, "get_models_manager", None)
    if callable(getter):
        return getter()
    return getattr(thread_manager, "models_manager", thread_manager)


def _get_model_info(models_manager: Any, model_name: str, config: Any) -> Any:
    getter = getattr(models_manager, "get_model_info", None)
    if not callable(getter):
        if models_manager is not None:
            return models_manager
        return SimpleNamespace(slug=model_name, default_reasoning_summary=ReasoningSummary.AUTO)
    models_config = _to_models_manager_config(config)
    try:
        return getter(model_name, models_config)
    except TypeError:
        return getter(model_name)


def _to_models_manager_config(config: Any) -> Any:
    converter = getattr(config, "to_models_manager_config", None)
    if callable(converter):
        return converter()
    return config


def _telemetry_with_model(session_telemetry: Any, model_name: str) -> Any:
    clone = getattr(session_telemetry, "clone", None)
    telemetry = clone() if callable(clone) else session_telemetry
    with_model = getattr(telemetry, "with_model", None)
    if callable(with_model):
        return with_model(model_name, model_name)
    return telemetry


def _config_codex_home(config: Any) -> Path:
    return Path(getattr(config, "codex_home"))


def _memory_feature_enabled(config: Any) -> bool:
    features = getattr(config, "features", None)
    if features is None:
        return False
    enabled = getattr(features, "enabled", None)
    if callable(enabled):
        for candidate in ("MemoryTool", "memory_tool"):
            try:
                if bool(enabled(candidate)):
                    return True
            except (KeyError, TypeError, ValueError):
                continue
        return False
    if isinstance(features, dict):
        return bool(features.get("MemoryTool") or features.get("memory_tool"))
    if isinstance(features, (set, list, tuple, frozenset)):
        return "MemoryTool" in features or "memory_tool" in features
    return bool(getattr(features, "MemoryTool", False) or getattr(features, "memory_tool", False))


def _source_is_non_root_agent(source: Any) -> bool:
    checker = getattr(source, "is_non_root_agent", None)
    if callable(checker):
        return bool(checker())
    kind = getattr(source, "kind", source)
    if isinstance(kind, str):
        normalized = kind.strip().lower()
        return normalized.startswith("internal") or normalized.startswith("subagent")
    return False


def _as_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    to_mapping = getattr(value, "to_mapping", None)
    if callable(to_mapping):
        mapped = to_mapping()
        return dict(mapped) if isinstance(mapped, dict) else {}
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}


def _response_item_kind(item: dict[str, Any]) -> str:
    raw = item.get("type", item.get("kind"))
    if isinstance(raw, str):
        return raw
    if "role" in item and "content" in item:
        return "message"
    if "call_id" in item and "output" in item:
        return "function_call_output"
    return ""


def _content_item_text(content_item: Any) -> str | None:
    mapping = _as_mapping(content_item)
    text = mapping.get("text")
    if isinstance(text, str):
        return text
    if _response_item_kind(mapping) == "input_text":
        value = mapping.get("value")
        return value if isinstance(value, str) else None
    return None


def _matches_marked_fragment(text: str, start_marker: str, end_marker: str) -> bool:
    left_trimmed = text.lstrip()
    starts_with_marker = left_trimmed[: len(start_marker)].lower() == start_marker.lower()
    right_trimmed = left_trimmed.rstrip()
    ends_with_marker = right_trimmed[-len(end_marker) :].lower() == end_marker.lower()
    return starts_with_marker and ends_with_marker


async def clear_memory_roots_contents(codex_home: str | Path) -> None:
    codex_home = Path(codex_home)
    for root in (codex_home / "memories", codex_home / "memories_extensions"):
        await clear_memory_root_contents(root)


async def clear_memory_root_contents(memory_root_path: str | Path) -> None:
    memory_root_path = Path(memory_root_path)
    if memory_root_path.is_symlink():
        raise OSError(f"refusing to clear symlinked memory root {memory_root_path}")

    memory_root_path.mkdir(parents=True, exist_ok=True)
    for child in list(memory_root_path.iterdir()):
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def build_consolidation_prompt(memory_root_path: str | Path) -> str:
    memory_root_path = Path(memory_root_path)
    extensions_root = memory_extensions_root(memory_root_path)
    extensions_exist = extensions_root.is_dir()
    extension_structure = (
        _render_template(
            _EXTENSIONS_FOLDER_STRUCTURE_TEMPLATE,
            memory_extensions_root=_display_path(extensions_root),
        )
        if extensions_exist
        else ""
    )
    extension_inputs = (
        _render_template(
            _EXTENSIONS_PRIMARY_INPUTS_TEMPLATE,
            memory_extensions_root=_display_path(extensions_root),
        )
        if extensions_exist
        else ""
    )
    return _render_template(
        _CONSOLIDATION_PROMPT_TEMPLATE,
        memory_root=_display_path(memory_root_path),
        memory_extensions_folder_structure=extension_structure,
        memory_extensions_primary_inputs=extension_inputs,
        phase2_workspace_diff_file=PHASE2_WORKSPACE_DIFF_FILENAME,
    )


def build_stage_one_input_message(
    model_info: ModelInfo,
    rollout_path: str | Path,
    rollout_cwd: str | Path,
    rollout_contents: str,
) -> str:
    resolved = model_info.resolved_context_window()
    if resolved is not None and resolved > 0:
        effective = (resolved * model_info.effective_context_window_percent) // 100
        rollout_token_limit = max((effective * STAGE_ONE_CONTEXT_WINDOW_PERCENT) // 100, 1)
    else:
        rollout_token_limit = STAGE_ONE_DEFAULT_ROLLOUT_TOKEN_LIMIT
    truncated = truncate_text(str(rollout_contents), TruncationPolicyConfig.tokens(rollout_token_limit))
    return _render_template(
        _STAGE_ONE_INPUT_TEMPLATE,
        rollout_path=_display_path(Path(rollout_path)),
        rollout_cwd=_display_path(Path(rollout_cwd)),
        rollout_contents=truncated,
    )


def snapshot_allows_startup(snapshot: RateLimitSnapshot, min_remaining_percent: int) -> bool:
    if snapshot.rate_limit_reached_type is not None:
        return False
    max_used_percent = 100.0 - float(_clamp(int(min_remaining_percent), 0, 100))
    return window_allows_startup(snapshot.primary, max_used_percent) and window_allows_startup(
        snapshot.secondary,
        max_used_percent,
    )


def window_allows_startup(window: RateLimitWindow | None, max_used_percent: float) -> bool:
    if window is None:
        return True
    return float(window.used_percent) <= float(max_used_percent)


async def rate_limits_ok(auth_manager: Any, config: Any) -> bool:
    checked = await rate_limits_check(auth_manager, config)
    return True if checked is None else bool(checked)


async def rate_limits_check(auth_manager: Any, config: Any) -> bool | None:
    auth = await _auth_manager_auth(auth_manager)
    if auth is None or not await _uses_codex_backend(auth):
        return None

    client = await _backend_client_from_auth(auth_manager, config, auth)
    if client is None:
        return None

    getter = getattr(client, "get_rate_limits_many", None)
    if not callable(getter):
        return None
    try:
        snapshots = await _maybe_await(getter())
    except Exception:
        return None

    parsed = [_rate_limit_snapshot(snapshot) for snapshot in list(snapshots or ())]
    if not parsed:
        return None
    selected = next((snapshot for snapshot in parsed if snapshot.limit_id == CODEX_LIMIT_ID), parsed[0])
    memories_config = getattr(config, "memories", None)
    min_remaining_percent = int(getattr(memories_config, "min_rate_limit_remaining_percent", 0))
    return snapshot_allows_startup(selected, min_remaining_percent)


async def ensure_layout(root: str | Path) -> None:
    rollout_summaries_dir(root).mkdir(parents=True, exist_ok=True)


async def rebuild_raw_memories_file_from_memories(
    root: str | Path,
    memories: Iterable[Stage1Output],
    max_raw_memories_for_consolidation: int = DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION,
) -> None:
    await ensure_layout(root)
    retained = _retained_memories(list(memories), max_raw_memories_for_consolidation)
    body = "# Raw Memories\n\n"
    if not retained:
        raw_memories_file(root).write_text(body + "No raw memories yet.\n", encoding="utf-8")
        return

    body += "Merged stage-1 raw memories (stable ascending thread-id order):\n\n"
    for memory in retained:
        summary_file = f"{rollout_summary_file_stem(memory)}.md"
        body += f"## Thread `{memory.thread_id}`\n"
        body += f"updated_at: {_rfc3339(memory.source_updated_at)}\n"
        body += f"cwd: {_display_path(memory.cwd)}\n"
        body += f"rollout_path: {_display_path(memory.rollout_path)}\n"
        body += f"rollout_summary_file: {summary_file}\n\n"
        body += memory.raw_memory.strip()
        body += "\n\n"
    raw_memories_file(root).write_text(body, encoding="utf-8")


async def sync_rollout_summaries_from_memories(
    root: str | Path,
    memories: Iterable[Stage1Output],
    max_raw_memories_for_consolidation: int = DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION,
) -> None:
    await ensure_layout(root)
    retained = _retained_memories(list(memories), max_raw_memories_for_consolidation)
    keep = {rollout_summary_file_stem(memory) for memory in retained}
    summaries_dir = rollout_summaries_dir(root)

    if summaries_dir.exists():
        for path in summaries_dir.iterdir():
            if path.name.endswith(".md") and path.stem not in keep:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

    for memory in retained:
        _write_rollout_summary_for_thread(root, memory)


def rollout_summary_file_stem(memory: Stage1Output) -> str:
    return _rollout_summary_file_stem_from_parts(
        memory.thread_id,
        memory.source_updated_at,
        memory.rollout_slug,
    )


def _write_rollout_summary_for_thread(root: str | Path, memory: Stage1Output) -> None:
    path = rollout_summaries_dir(root) / f"{rollout_summary_file_stem(memory)}.md"
    body = f"thread_id: {memory.thread_id}\n"
    body += f"updated_at: {_rfc3339(memory.source_updated_at)}\n"
    body += f"rollout_path: {_display_path(memory.rollout_path)}\n"
    body += f"cwd: {_display_path(memory.cwd)}\n"
    if memory.git_branch is not None:
        body += f"git_branch: {memory.git_branch}\n"
    body += "\n"
    body += memory.rollout_summary
    body += "\n"
    path.write_text(body, encoding="utf-8")


def _retained_memories(memories: list[Stage1Output], limit: int) -> list[Stage1Output]:
    return memories[: min(len(memories), max(0, int(limit)))]


def _rollout_summary_file_stem_from_parts(
    thread_id: str,
    source_updated_at: datetime,
    rollout_slug: str | None,
) -> str:
    slug_max_len = 60
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    hash_space = 14_776_336
    thread_id_text = str(thread_id)

    try:
        thread_uuid = UUID(thread_id_text)
    except ValueError:
        short_hash_seed = 0
        for byte in thread_id_text.encode("utf-8"):
            short_hash_seed = ((short_hash_seed * 31) + byte) & 0xFFFF_FFFF
        timestamp = _as_utc(source_updated_at)
    else:
        timestamp = _uuid_timestamp_or_source_time(thread_uuid, source_updated_at)
        short_hash_seed = thread_uuid.int & 0xFFFF_FFFF

    short_hash_value = short_hash_seed % hash_space
    chars = ["0"] * 4
    for idx in range(len(chars) - 1, -1, -1):
        chars[idx] = alphabet[short_hash_value % len(alphabet)]
        short_hash_value //= len(alphabet)
    file_prefix = f"{timestamp.strftime('%Y-%m-%dT%H-%M-%S')}-{''.join(chars)}"

    if rollout_slug is None:
        return file_prefix

    slug = ""
    for ch in rollout_slug:
        if len(slug) >= slug_max_len:
            break
        slug += ch.lower() if ch.isascii() and ch.isalnum() else "_"
    slug = slug.rstrip("_")
    return file_prefix if not slug else f"{file_prefix}-{slug}"


def _uuid_timestamp_or_source_time(thread_uuid: UUID, source_updated_at: datetime) -> datetime:
    if thread_uuid.version == 7:
        millis = thread_uuid.int >> 80
        return datetime.fromtimestamp(millis / 1000, tz=UTC)
    if thread_uuid.version == 1:
        seconds = (thread_uuid.time - 0x01B21DD213814000) / 10_000_000
        return datetime.fromtimestamp(seconds, tz=UTC)
    return _as_utc(source_updated_at)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _rfc3339(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _display_path(value: Path) -> str:
    return Path(value).as_posix()


def _render_template(template: str, **values: str) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{ " + key + " }}", value)
    return rendered


def _clamp(value: int, low: int, high: int) -> int:
    return min(max(value, low), high)


def _append_bounded_diff(rendered: str, diff: str) -> str:
    if len(diff.encode("utf-8")) <= PHASE2_WORKSPACE_DIFF_MAX_BYTES:
        rendered += diff
        if not diff.endswith("\n"):
            rendered += "\n"
        return rendered

    encoded = diff.encode("utf-8")
    boundary = previous_char_boundary(diff, PHASE2_WORKSPACE_DIFF_MAX_BYTES)
    rendered += encoded[:boundary].decode("utf-8")
    if not rendered.endswith("\n"):
        rendered += "\n"
    rendered += f"\n[workspace diff truncated at {PHASE2_WORKSPACE_DIFF_MAX_BYTES} bytes]\n"
    return rendered


__all__ = [
    "DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION",
    "CODEX_LIMIT_ID",
    "EXTENSION_RESOURCE_RETENTION_DAYS",
    "EXTENSIONS_SUBDIR",
    "PHASE2_WORKSPACE_DIFF_FILENAME",
    "PHASE2_WORKSPACE_DIFF_MAX_BYTES",
    "RAW_MEMORIES_FILENAME",
    "ROLLOUT_SUMMARIES_SUBDIR",
    "MEMORY_PHASE_TWO_E2E_MS",
    "MEMORY_PHASE_TWO_INPUT",
    "MEMORY_PHASE_TWO_JOBS",
    "MEMORY_PHASE_TWO_TOKEN_USAGE",
    "STAGE_TWO_JOB_LEASE_SECONDS",
    "STAGE_TWO_JOB_RETRY_DELAY_SECONDS",
    "STAGE_TWO_MODEL",
    "STAGE_TWO_REASONING_EFFORT",
    "STAGE_ONE_CONTEXT_WINDOW_PERCENT",
    "STAGE_ONE_DEFAULT_ROLLOUT_TOKEN_LIMIT",
    "STAGE_ONE_MODEL",
    "STAGE_ONE_REASONING_EFFORT",
    "MemoryStartupContext",
    "MemoryStartupResult",
    "PhaseOneJobResult",
    "PhaseOneStats",
    "PhaseTwoClaim",
    "SpawnedConsolidationAgent",
    "Stage1Output",
    "StageOneOutput",
    "aggregate_phase_one_stats",
    "emit_phase_one_metrics",
    "build_consolidation_prompt",
    "build_stage_one_input_message",
    "clear_memory_root_contents",
    "clear_memory_roots_contents",
    "ensure_layout",
    "emit_phase_two_metrics",
    "emit_phase_two_token_usage_metrics",
    "memory_extensions_root",
    "memory_root",
    "memory_startup_skip_reason",
    "memory_workspace_diff",
    "is_memory_excluded_contextual_user_fragment",
    "phase_one_output_schema",
    "phase_one_job_run",
    "phase_one_run",
    "phase_one_sample",
    "phase_two_agent_config",
    "phase_two_agent_prompt",
    "phase_two_claim",
    "phase_two_get_watermark",
    "phase_two_handle_agent_completion",
    "phase_two_is_final_agent_status",
    "phase_two_loop_agent",
    "phase_two_mark_failed",
    "phase_two_mark_succeeded",
    "phase_two_run",
    "prepare_memory_workspace",
    "previous_char_boundary",
    "raw_memories_file",
    "rate_limits_check",
    "rate_limits_ok",
    "rebuild_raw_memories_file_from_memories",
    "remove_workspace_diff",
    "redact_secrets",
    "render_workspace_diff_file",
    "reset_memory_workspace_baseline",
    "resource_timestamp",
    "rollout_summaries_dir",
    "rollout_summary_file_stem",
    "sanitize_response_item_for_memories",
    "serialize_filtered_rollout_response_items",
    "should_persist_response_item_for_memories",
    "prune_old_extension_resources",
    "prune_old_extension_resources_with_now",
    "seed_extension_instructions",
    "snapshot_allows_startup",
    "start_memories_startup_task",
    "sync_phase2_workspace_inputs",
    "sync_rollout_summaries_from_memories",
    "window_allows_startup",
    "write_workspace_diff",
]
