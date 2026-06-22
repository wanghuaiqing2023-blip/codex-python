from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from pycodex.memories.write import MemoryStartupContext, SpawnedConsolidationAgent, StageOneRequestContext
from pycodex.protocol import ContentItem, Op, ReasoningEffort, ReasoningSummary, ResponseItem, TokenUsage, UserInput


class Thread:
    def __init__(
        self,
        service_tier: str | None = None,
        state_db=None,
        *,
        thread_id: str = "thread-1",
        submit_error: Exception | None = None,
        shutdown_delay: float = 0,
    ) -> None:
        self._service_tier = service_tier
        self._state_db = state_db
        self.thread_id = thread_id
        self.submit_error = submit_error
        self.shutdown_delay = shutdown_delay
        self.submitted: list[Op] = []
        self.shutdowns = 0

    async def config_snapshot(self):
        return SimpleNamespace(service_tier=self._service_tier, session_source="cli")

    def state_db(self):
        return self._state_db

    async def submit(self, op: Op) -> None:
        self.submitted.append(op)
        if self.submit_error is not None:
            raise self.submit_error

    async def shutdown_and_wait(self) -> None:
        self.shutdowns += 1
        if self.shutdown_delay:
            await asyncio.sleep(self.shutdown_delay)


class ModelsManager:
    def __init__(self, model_info) -> None:
        self.model_info = model_info
        self.calls: list[tuple[str, object]] = []

    async def get_model_info(self, model_name: str, config):
        self.calls.append((model_name, config))
        return self.model_info


class ThreadManager:
    def __init__(self, models_manager: ModelsManager) -> None:
        self.models_manager = models_manager
        self.default_environment_calls: list[Path] = []
        self.start_options: list[SimpleNamespace] = []
        self.remove_calls: list[str] = []
        self.next_thread = Thread(thread_id="agent-thread")
        self.removed_thread = None

    def get_models_manager(self) -> ModelsManager:
        return self.models_manager

    def default_environment_selections(self, cwd):
        self.default_environment_calls.append(cwd)
        return ["default-env"]

    async def start_thread_with_options(self, options):
        self.start_options.append(options)
        return SimpleNamespace(thread_id=self.next_thread.thread_id, thread=self.next_thread)

    async def remove_thread(self, thread_id):
        self.remove_calls.append(thread_id)
        return self.removed_thread


class Telemetry:
    def __init__(self, model: str = "startup-model") -> None:
        self.model = model
        self.requested_model = model
        self.counters: list[tuple[str, int, tuple[tuple[str, str], ...]]] = []
        self.histograms: list[tuple[str, int, tuple[tuple[str, str], ...]]] = []
        self.timers: list[str] = []

    def clone(self) -> "Telemetry":
        cloned = Telemetry(self.model)
        cloned.counters = self.counters
        cloned.histograms = self.histograms
        cloned.timers = self.timers
        return cloned

    def with_model(self, model: str, requested_model: str) -> "Telemetry":
        self.model = model
        self.requested_model = requested_model
        return self

    def counter(self, name: str, inc: int, tags) -> None:
        self.counters.append((name, inc, tuple(tags)))

    def histogram(self, name: str, value: int, tags) -> None:
        self.histograms.append((name, value, tuple(tags)))

    def start_timer(self, name: str, tags=()) -> str:
        self.timers.append(name)
        return name


class AsyncStream:
    def __init__(self, events) -> None:
        self.events = list(events)

    def __aiter__(self):
        self._iter = iter(self.events)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class ModelSession:
    def __init__(self, events) -> None:
        self.events = events
        self.calls: list[tuple] = []

    async def stream(self, prompt, model_info, session_telemetry, reasoning_effort, reasoning_summary, service_tier, turn_metadata_header, trace_context):
        self.calls.append((prompt, model_info, session_telemetry, reasoning_effort, reasoning_summary, service_tier, turn_metadata_header, trace_context))
        return AsyncStream(self.events)


class ModelClient:
    def __init__(self, session: ModelSession) -> None:
        self.session = session

    def new_session(self) -> ModelSession:
        return self.session


def context(tmp_path: Path, *, model_info, service_tier: str | None = "fast") -> MemoryStartupContext:
    models_manager = ModelsManager(model_info)
    return MemoryStartupContext(
        thread_manager=ThreadManager(models_manager),
        auth_manager="auth-manager",
        thread_id="thread-1",
        thread=Thread(service_tier=service_tier, state_db={"db": "ok"}),
        config=SimpleNamespace(model="startup-model", cwd=tmp_path),
        source="cli",
        state_db_value={"db": "ok"},
        counters=[],
        histograms=[],
        session_telemetry=Telemetry(),
    )


def test_stage_one_request_context_uses_thread_service_tier_and_detached_metadata(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/runtime.rs::stage_one_request_context + src/startup_tests.rs::memories_startup_phase1_uses_live_thread_service_tier_and_detached_metadata
    # Contract: stage-one requests use the live thread service tier and detached memory turn metadata without session/thread/turn/window identity.
    model_info = SimpleNamespace(default_reasoning_summary=ReasoningSummary.CONCISE)
    cfg = SimpleNamespace(
        cwd=tmp_path,
        model_reasoning_summary=None,
        to_models_manager_config=lambda: {"from": "config"},
    )
    ctx = context(tmp_path, model_info=model_info, service_tier="fast")

    request_context = asyncio.run(ctx.stage_one_request_context(cfg, "gpt-5.4-mini", ReasoningEffort.LOW))

    assert request_context.model_info is model_info
    assert request_context.reasoning_effort == ReasoningEffort.LOW
    assert request_context.reasoning_summary == ReasoningSummary.CONCISE
    assert request_context.service_tier == "fast"
    assert request_context.session_telemetry.model == "gpt-5.4-mini"
    assert request_context.session_telemetry.requested_model == "gpt-5.4-mini"
    metadata = json.loads(request_context.turn_metadata_header or "")
    assert metadata["request_kind"] == "memory"
    for forbidden in ("session_id", "thread_id", "forked_from_thread_id", "turn_id", "window_id"):
        assert forbidden not in metadata


def test_stage_one_request_context_config_reasoning_summary_overrides_model_default(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/runtime.rs::stage_one_request_context
    # Contract: config.model_reasoning_summary wins over ModelInfo.default_reasoning_summary.
    model_info = SimpleNamespace(default_reasoning_summary=ReasoningSummary.CONCISE)
    cfg = SimpleNamespace(
        cwd=tmp_path,
        model_reasoning_summary=ReasoningSummary.DETAILED,
        to_models_manager_config=lambda: "models-config",
    )
    ctx = context(tmp_path, model_info=model_info, service_tier=None)

    request_context = asyncio.run(ctx.stage_one_request_context(cfg, "model-a", ReasoningEffort.MEDIUM))

    assert request_context.reasoning_summary == ReasoningSummary.DETAILED
    assert request_context.service_tier is None
    models_manager = ctx.thread_manager.get_models_manager()
    assert models_manager.calls == [("model-a", "models-config")]


def test_runtime_context_and_stage_one_context_delegate_telemetry(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/runtime.rs::MemoryStartupContext::{counter,histogram,start_timer} and StageOneRequestContext::{counter,histogram,start_timer}
    # Contract: runtime contexts delegate metric operations to their SessionTelemetry sink.
    telemetry = Telemetry()
    ctx = MemoryStartupContext(
        thread_manager="thread-manager",
        auth_manager="auth-manager",
        thread_id="thread-1",
        thread=Thread(state_db={"db": "ok"}),
        config=SimpleNamespace(model="startup-model", cwd=tmp_path),
        source="cli",
        state_db_value={"db": "ok"},
        counters=[],
        histograms=[],
        session_telemetry=telemetry,
    )

    assert ctx.state_db() == {"db": "ok"}
    assert ctx.start_timer("startup") == "startup"
    ctx.counter("memory", 2, (("status", "ok"),))
    ctx.histogram("tokens", 7, (("token_type", "total"),))

    stage = StageOneRequestContext(
        model_info=SimpleNamespace(),
        session_telemetry=telemetry,
        reasoning_effort=ReasoningEffort.LOW,
        reasoning_summary=ReasoningSummary.AUTO,
        service_tier=None,
        turn_metadata_header=None,
    )
    assert stage.start_timer("stage1") == "stage1"
    stage.counter("phase1", 1, ())
    stage.histogram("phase1.tokens", 3, ())

    assert telemetry.timers == ["startup", "stage1"]
    assert telemetry.counters == [
        ("memory", 2, (("status", "ok"),)),
        ("phase1", 1, ()),
    ]
    assert telemetry.histograms == [
        ("tokens", 7, (("token_type", "total"),)),
        ("phase1.tokens", 3, ()),
    ]


def test_stream_stage_one_prompt_collects_deltas_and_completed_token_usage(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/runtime.rs::MemoryStartupContext::stream_stage_one_prompt
    # Contract: OutputTextDelta appends text, Completed stores token usage and stops reading the stream.
    usage = TokenUsage(total_tokens=11, input_tokens=5, output_tokens=6)
    session = ModelSession(
        [
            SimpleNamespace(type="output_text_delta", delta="hello "),
            SimpleNamespace(type="output_text_delta", delta="world"),
            SimpleNamespace(type="completed", token_usage=usage),
            SimpleNamespace(type="output_text_delta", delta=" ignored"),
        ]
    )
    cfg = SimpleNamespace(
        cwd=tmp_path,
        model_client_factory=lambda **kwargs: ModelClient(session),
    )
    ctx = context(tmp_path, model_info=SimpleNamespace(default_reasoning_summary=ReasoningSummary.CONCISE))
    request_context = StageOneRequestContext(
        model_info=SimpleNamespace(name="model-info"),
        session_telemetry=Telemetry(),
        reasoning_effort=ReasoningEffort.LOW,
        reasoning_summary=ReasoningSummary.AUTO,
        service_tier="fast",
        turn_metadata_header='{"request_kind":"memory"}',
    )

    text, token_usage = asyncio.run(ctx.stream_stage_one_prompt(cfg, "prompt", request_context))

    assert text == "hello world"
    assert token_usage is usage
    assert session.calls == [
        (
            "prompt",
            request_context.model_info,
            request_context.session_telemetry,
            ReasoningEffort.LOW,
            ReasoningSummary.AUTO,
            "fast",
            '{"request_kind":"memory"}',
            None,
        )
    ]


def test_stream_stage_one_prompt_uses_message_item_only_when_no_delta_seen(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/runtime.rs::MemoryStartupContext::stream_stage_one_prompt
    # Contract: OutputItemDone(Message) contributes content text only while the accumulated result is empty.
    fallback_item = ResponseItem.message("assistant", (ContentItem.output_text("fallback text"),))
    ignored_item = ResponseItem.message("assistant", (ContentItem.output_text("ignored fallback"),))
    first_session = ModelSession(
        [
            {"type": "output_item_done", "item": fallback_item},
            {"type": "completed", "token_usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 2, "reasoning_output_tokens": 0, "total_tokens": 3}},
        ]
    )
    second_session = ModelSession(
        [
            {"type": "output_text_delta", "delta": "delta wins"},
            {"type": "output_item_done", "item": ignored_item},
            {"type": "completed", "token_usage": None},
        ]
    )

    ctx = context(tmp_path, model_info=SimpleNamespace(default_reasoning_summary=ReasoningSummary.CONCISE))
    cfg = SimpleNamespace(cwd=tmp_path, model_client_factory=lambda **kwargs: ModelClient(first_session))
    request_context = StageOneRequestContext(SimpleNamespace(), Telemetry(), None, ReasoningSummary.AUTO, None, None)

    text, usage = asyncio.run(ctx.stream_stage_one_prompt(cfg, "prompt", request_context))

    assert text == "fallback text"
    assert isinstance(usage, TokenUsage)
    assert usage.total_tokens == 3

    cfg.model_client_factory = lambda **kwargs: ModelClient(second_session)
    text, usage = asyncio.run(ctx.stream_stage_one_prompt(cfg, "prompt", request_context))

    assert text == "delta wins"
    assert usage is None


def test_spawn_consolidation_agent_uses_memory_thread_options_and_submits_prompt(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/runtime.rs::MemoryStartupContext::spawn_consolidation_agent
    # Contract: consolidation agents start a new internal memory_consolidation thread with no dynamic tools, no extended history persistence, default environments, then submit Op::UserInput.
    model_info = SimpleNamespace(default_reasoning_summary=ReasoningSummary.CONCISE)
    ctx = context(tmp_path, model_info=model_info)
    cfg = SimpleNamespace(cwd=tmp_path / "memories")
    prompt = [UserInput.text_input("consolidate")]

    agent = asyncio.run(ctx.spawn_consolidation_agent(cfg, prompt))

    manager = ctx.thread_manager
    assert agent == SpawnedConsolidationAgent("agent-thread", manager.next_thread)
    assert manager.default_environment_calls == [cfg.cwd]
    assert len(manager.start_options) == 1
    options = manager.start_options[0]
    assert options.config is cfg
    assert options.initial_history == "new"
    assert options.session_source == ("internal", "memory_consolidation")
    assert options.thread_source == "memory_consolidation"
    assert options.dynamic_tools == []
    assert options.persist_extended_history is False
    assert options.metrics_service_name is None
    assert options.parent_trace is None
    assert options.environments == ["default-env"]
    assert len(manager.next_thread.submitted) == 1
    op = manager.next_thread.submitted[0]
    assert op.type == "user_input"
    assert op.fields["items"] == tuple(prompt)


def test_spawn_consolidation_agent_shuts_down_started_thread_when_submit_fails(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/runtime.rs::MemoryStartupContext::spawn_consolidation_agent
    # Contract: if submitting the initial user input fails after thread start, Rust shuts down the spawned consolidation agent and returns the submit error.
    ctx = context(tmp_path, model_info=SimpleNamespace(default_reasoning_summary=ReasoningSummary.CONCISE))
    manager = ctx.thread_manager
    manager.next_thread = Thread(thread_id="agent-thread", submit_error=RuntimeError("submit failed"))

    try:
        asyncio.run(ctx.spawn_consolidation_agent(SimpleNamespace(cwd=tmp_path), [UserInput.text_input("go")]))
    except RuntimeError as exc:
        assert str(exc) == "submit failed"
    else:
        raise AssertionError("expected submit failure")

    assert manager.remove_calls == ["agent-thread"]
    assert manager.next_thread.shutdowns == 1


def test_shutdown_consolidation_agent_prefers_removed_thread_and_times_out(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/runtime.rs::MemoryStartupContext::shutdown_consolidation_agent
    # Contract: shutdown removes the thread from ThreadManager, falls back to the supplied thread only when removal returns none, and reports the Rust timeout message.
    ctx = context(tmp_path, model_info=SimpleNamespace(default_reasoning_summary=ReasoningSummary.CONCISE))
    manager = ctx.thread_manager
    supplied = Thread(thread_id="agent-thread")
    removed = Thread(thread_id="agent-thread")
    manager.removed_thread = removed

    asyncio.run(ctx.shutdown_consolidation_agent(SpawnedConsolidationAgent("agent-thread", supplied)))

    assert manager.remove_calls == ["agent-thread"]
    assert supplied.shutdowns == 0
    assert removed.shutdowns == 1

    manager.removed_thread = Thread(thread_id="slow-thread", shutdown_delay=0.05)
    try:
        asyncio.run(
            ctx.shutdown_consolidation_agent(
                SpawnedConsolidationAgent("slow-thread", supplied),
                shutdown_timeout_seconds=0.001,
            )
        )
    except TimeoutError as exc:
        assert str(exc) == "memory consolidation agent slow-thread shutdown timed out"
    else:
        raise AssertionError("expected shutdown timeout")
