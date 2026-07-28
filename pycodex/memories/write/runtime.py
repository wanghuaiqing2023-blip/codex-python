"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from pycodex.core.compact import content_items_to_text
from pycodex.core.turn_metadata import build_turn_metadata_header
from pycodex.protocol import AgentStatus, BaseInstructions, ContentItem, ModelInfo, Op, RateLimitSnapshot, RateLimitWindow, ReasoningEffort, ReasoningSummary, ResponseItem, TokenUsage, TruncationPolicyConfig, UserInput
from types import SimpleNamespace
from typing import Any, Callable, Iterable
import asyncio
import inspect

@dataclass
class MemorySessionTelemetry:
    """Small telemetry sink mirroring the methods used by Rust ``SessionTelemetry``."""
    model: str
    requested_model: str | None = None
    counters: list[tuple[str, int, tuple[tuple[str, str], ...]]] | None = None
    histograms: list[tuple[str, int, tuple[tuple[str, str], ...]]] | None = None
    timers: list[str] | None = None

    def clone(self) -> 'MemorySessionTelemetry':
        return MemorySessionTelemetry(model=self.model, requested_model=self.requested_model, counters=self.counters, histograms=self.histograms, timers=self.timers)

    def with_model(self, model: str, requested_model: str) -> 'MemorySessionTelemetry':
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

    def start_timer(self, name: str, tags: Iterable[tuple[str, str]]=()) -> str:
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
        starter = getattr(self.session_telemetry, 'start_timer', None)
        if callable(starter):
            try:
                return starter(name, ())
            except TypeError:
                return starter(name)
        return None

    def counter(self, name: str, inc: int, tags: Iterable[tuple[str, str]]) -> None:
        counter = getattr(self.session_telemetry, 'counter', None)
        if callable(counter):
            counter(name, int(inc), tuple(tags))

    def histogram(self, name: str, value: int, tags: Iterable[tuple[str, str]]) -> None:
        histogram = getattr(self.session_telemetry, 'histogram', None)
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
            model = getattr(self.config, 'model', None) or 'unknown'
            self.session_telemetry = MemorySessionTelemetry(model=str(model), requested_model=str(model), counters=self.counters, histograms=self.histograms, timers=self.timers)

    def state_db(self) -> Any:
        return self.state_db_value

    def counter(self, name: str, inc: int, tags: Iterable[tuple[str, str]]) -> None:
        counter = getattr(self.session_telemetry, 'counter', None)
        if callable(counter):
            counter(name, int(inc), tuple(tags))
        else:
            self.counters.append((name, int(inc), tuple(tags)))

    def histogram(self, name: str, value: int, tags: Iterable[tuple[str, str]]) -> None:
        histogram = getattr(self.session_telemetry, 'histogram', None)
        if callable(histogram):
            histogram(name, int(value), tuple(tags))
        else:
            self.histograms.append((name, int(value), tuple(tags)))

    def start_timer(self, name: str) -> Any:
        starter = getattr(self.session_telemetry, 'start_timer', None)
        if callable(starter):
            try:
                return starter(name, ())
            except TypeError:
                return starter(name)
        if self.timers is not None:
            self.timers.append(name)
        return name

    async def stage_one_request_context(self, config: Any, model_name: str, reasoning_effort: Any) -> StageOneRequestContext:
        config_snapshot = await _maybe_await(_call_or_value(getattr(self.thread, 'config_snapshot', None)))
        models_manager = _models_manager(self.thread_manager)
        model_info = await _maybe_await(_get_model_info(models_manager, model_name, config))
        turn_metadata_header = build_turn_metadata_header(Path(getattr(config, 'cwd')))
        reasoning_summary = getattr(config, 'model_reasoning_summary', None)
        if reasoning_summary is None:
            reasoning_summary = getattr(model_info, 'default_reasoning_summary', ReasoningSummary.AUTO)
        session_telemetry = _telemetry_with_model(self.session_telemetry, model_name)
        return StageOneRequestContext(model_info=model_info, session_telemetry=session_telemetry, reasoning_effort=reasoning_effort, reasoning_summary=reasoning_summary, service_tier=getattr(config_snapshot, 'service_tier', None), turn_metadata_header=turn_metadata_header)

    async def stream_stage_one_prompt(self, config: Any, prompt: Any, context: StageOneRequestContext) -> tuple[str, TokenUsage | None]:
        client_factory = getattr(config, 'model_client_factory', None) or getattr(self.auth_manager, 'model_client_factory', None)
        if not callable(client_factory):
            raise RuntimeError('model client factory is required for stream_stage_one_prompt')
        config_snapshot = await _maybe_await(_call_or_value(getattr(self.thread, 'config_snapshot', None)))
        model_client = await _maybe_await(client_factory(auth_manager=self.auth_manager, session_id=self.thread_id, thread_id=self.thread_id, config=config, session_source=getattr(config_snapshot, 'session_source', None)))
        client_session = await _maybe_await(_call_or_value(getattr(model_client, 'new_session', None)))
        stream = await _maybe_await(client_session.stream(prompt, context.model_info, context.session_telemetry, context.reasoning_effort, context.reasoning_summary, context.service_tier, context.turn_metadata_header, None))
        result = ''
        token_usage: TokenUsage | None = None
        async for message in _async_iter(stream):
            kind = _event_kind(message)
            if kind in {'output_text_delta', 'OutputTextDelta'}:
                result += str(_event_payload(message, 'delta', 'text', 'value', default=''))
            elif kind in {'output_item_done', 'OutputItemDone'}:
                item = _event_payload(message, 'item', default=message)
                if result == '':
                    fallback = _response_item_text(item)
                    if fallback is not None:
                        result += fallback
            elif kind in {'completed', 'Completed'}:
                usage = _event_payload(message, 'token_usage', 'usage', default=None)
                token_usage = usage if isinstance(usage, TokenUsage) or usage is None else TokenUsage.from_mapping(usage)
                break
        return (result, token_usage)

    async def spawn_consolidation_agent(self, config: Any, prompt: Iterable[UserInput]) -> 'SpawnedConsolidationAgent':
        environments_getter = getattr(self.thread_manager, 'default_environment_selections', None)
        environments = await _maybe_await(environments_getter(getattr(config, 'cwd', None))) if callable(environments_getter) else []
        options = SimpleNamespace(config=config, initial_history='new', session_source=('internal', 'memory_consolidation'), thread_source='memory_consolidation', dynamic_tools=[], persist_extended_history=False, metrics_service_name=None, parent_trace=None, environments=list(environments))
        new_thread = await _maybe_await(self.thread_manager.start_thread_with_options(options))
        thread_id = _field(new_thread, 'thread_id')
        thread = _field(new_thread, 'thread')
        agent = SpawnedConsolidationAgent(thread_id=thread_id, thread=thread)
        try:
            await _maybe_await(thread.submit(Op.user_input(list(prompt), environments=None, final_output_json_schema=None, responsesapi_client_metadata=None, additional_context={})))
        except Exception:
            await self.shutdown_consolidation_agent(agent)
            raise
        return agent

    async def shutdown_consolidation_agent(self, agent: 'SpawnedConsolidationAgent', *, shutdown_timeout_seconds: float=10) -> None:
        thread = agent.thread
        remover = getattr(self.thread_manager, 'remove_thread', None)
        if callable(remover):
            removed = await _maybe_await(remover(agent.thread_id))
            if removed is not None:
                thread = removed
        try:
            await asyncio.wait_for(_maybe_await(thread.shutdown_and_wait()), timeout=shutdown_timeout_seconds)
        except TimeoutError as exc:
            raise TimeoutError(f'memory consolidation agent {agent.thread_id} shutdown timed out') from exc


@dataclass(frozen=True)
class SpawnedConsolidationAgent:
    """Python projection of Rust ``runtime::SpawnedConsolidationAgent``."""
    thread_id: Any
    thread: Any


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _auth_manager_auth(auth_manager: Any) -> Any | None:
    auth_method = getattr(auth_manager, 'auth', None)
    if callable(auth_method):
        return await _maybe_await(auth_method())
    current = getattr(auth_manager, 'current_auth', None)
    if callable(current):
        return await _maybe_await(current())
    if current is not None:
        return current
    return getattr(auth_manager, 'auth_value', None)


async def _uses_codex_backend(auth: Any) -> bool:
    uses = getattr(auth, 'uses_codex_backend', None)
    if callable(uses):
        return bool(await _maybe_await(uses()))
    if uses is not None:
        return bool(uses)
    return bool(getattr(auth, 'uses_codex_backend_value', False))


async def _backend_client_from_auth(auth_manager: Any, config: Any, auth: Any) -> Any | None:
    factory = getattr(config, 'backend_client_factory', None) or getattr(auth_manager, 'backend_client_factory', None) or getattr(auth, 'backend_client_factory', None)
    if callable(factory):
        base_url = getattr(config, 'chatgpt_base_url', None)
        for args in ((base_url, auth), (auth,), (config, auth), ()):
            try:
                return await _maybe_await(factory(*args))
            except TypeError:
                continue
            except Exception:
                return None
        return None
    if callable(getattr(auth_manager, 'get_rate_limits_many', None)):
        return auth_manager
    if callable(getattr(auth, 'get_rate_limits_many', None)):
        return auth
    return None


def _rate_limit_snapshot(value: Any) -> RateLimitSnapshot:
    if isinstance(value, RateLimitSnapshot):
        return value
    if isinstance(value, dict):
        return RateLimitSnapshot.from_mapping(value)
    return RateLimitSnapshot.from_mapping(vars(value))


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
    if hasattr(value, '__aiter__'):
        async for item in value:
            yield item
        return
    for item in value:
        yield (await _maybe_await(item))


def _event_kind(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get('type') or value.get('kind') or value.get('event'))
    return str(getattr(value, 'type', getattr(value, 'kind', value.__class__.__name__)))


def _event_payload(value: Any, *names: str, default: Any=None) -> Any:
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
        if item.type == 'message':
            return content_items_to_text(item.content)
        return None
    item_type = _event_payload(value, 'type', default=None)
    role = _event_payload(value, 'role', default=None)
    content = _event_payload(value, 'content', default=())
    if item_type == 'message' and role in {None, 'assistant'}:
        pieces: list[str] = []
        for entry in content or ():
            if isinstance(entry, ContentItem):
                if entry.type in {'input_text', 'output_text'} and entry.text:
                    pieces.append(entry.text)
            elif isinstance(entry, dict) and entry.get('type') in {'input_text', 'output_text'} and entry.get('text'):
                pieces.append(str(entry['text']))
        return '\n'.join(pieces) if pieces else None
    return None


def _call_or_value(value: Any) -> Any:
    if callable(value):
        return value()
    return value


def _models_manager(thread_manager: Any) -> Any:
    getter = getattr(thread_manager, 'get_models_manager', None)
    if callable(getter):
        return getter()
    return getattr(thread_manager, 'models_manager', thread_manager)


def _get_model_info(models_manager: Any, model_name: str, config: Any) -> Any:
    getter = getattr(models_manager, 'get_model_info', None)
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
    converter = getattr(config, 'to_models_manager_config', None)
    if callable(converter):
        return converter()
    return config


def _telemetry_with_model(session_telemetry: Any, model_name: str) -> Any:
    clone = getattr(session_telemetry, 'clone', None)
    telemetry = clone() if callable(clone) else session_telemetry
    with_model = getattr(telemetry, 'with_model', None)
    if callable(with_model):
        return with_model(model_name, model_name)
    return telemetry


def _config_codex_home(config: Any) -> Path:
    return Path(getattr(config, 'codex_home'))


def _as_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    to_mapping = getattr(value, 'to_mapping', None)
    if callable(to_mapping):
        mapped = to_mapping()
        return dict(mapped) if isinstance(mapped, dict) else {}
    if hasattr(value, '__dict__'):
        return dict(vars(value))
    return {}
