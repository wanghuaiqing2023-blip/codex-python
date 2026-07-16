from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pycodex.core.client import ModelClient
from pycodex.core.session.runtime import InMemoryCodexSession
from pycodex.core.session.turn.runtime import run_user_turn_sampling_from_session
from pycodex.ext.goal import GoalExtension, GoalRuntimeHandle, install_with_backend
from pycodex.core.tools.context import ToolPayload
from pycodex.exec.local_runtime import LocalHttpModelInfo, create_exec_core_session
from pycodex.exec.session import ExecSessionConfig
from pycodex.extension_api import (
    ExtensionData,
    ExtensionRegistryBuilder,
    ThreadStartInput,
    TurnStartInput,
)
from pycodex.protocol import (
    CollaborationMode,
    CodexErr,
    ContentItem,
    ModeKind,
    ResponseItem,
    SessionSource,
    Settings,
    ThreadGoalStatus,
    TokenUsage,
    TokenUsageInfo,
    UserInput,
    UsageLimitReachedError,
)
from pycodex.state.runtime.goals import GoalStore


def test_install_registers_all_rust_goal_contributor_categories() -> None:
    # Rust source: codex-rs/ext/goal/src/extension.rs::install_with_backend.
    builder = ExtensionRegistryBuilder.new()
    extension = install_with_backend(builder, object(), lambda _config: True)
    registry = builder.build()

    assert isinstance(extension, GoalExtension)
    assert registry.thread_lifecycle_contributors() == (extension,)
    assert registry.config_contributors() == (extension,)
    assert registry.turn_lifecycle_contributors() == (extension,)
    assert registry.token_usage_contributors() == (extension,)
    assert registry.tool_lifecycle_contributors() == (extension,)
    assert registry.tool_contributors() == (extension,)


def test_thread_start_attaches_runtime_and_exposes_goal_tools() -> None:
    builder = ExtensionRegistryBuilder.new()
    extension = install_with_backend(builder, object(), lambda _config: True)
    registry = builder.build()
    session = InMemoryCodexSession(cwd="C:/work", goal_tools_enabled_value=True)
    thread_store = ExtensionData("thread-1")

    asyncio.run(
        extension.on_thread_start(
            ThreadStartInput(
                config=session,
                session_source=SessionSource.default(),
                persistent_thread_state_available=True,
                session_store=ExtensionData("session-1"),
                thread_store=thread_store,
            )
        )
    )

    assert isinstance(thread_store.get(GoalRuntimeHandle), GoalRuntimeHandle)
    assert [tool.tool_name().name for tool in registry.tool_contributors()[0].tools(None, thread_store)] == [
        "get_goal",
        "create_goal",
        "update_goal",
    ]


def test_product_session_keeps_goal_runtime_in_core_like_current_app_server() -> None:
    # Rust: codex-app-server::extensions::thread_extensions does not install
    # codex-goal-extension; product GoalRuntime is owned by codex-core::goals.
    session = InMemoryCodexSession(cwd="C:/work", state_db=object(), goal_tools_enabled_value=True)

    assert session.services.extensions.tool_contributors() == ()
    assert session.services.extensions.turn_lifecycle_contributors() == ()


def test_token_contributor_records_cumulative_usage_for_the_active_turn() -> None:
    # Rust: codex-rs/ext/goal/src/extension.rs::TokenUsageContributor::on_token_usage.
    builder = ExtensionRegistryBuilder.new()
    extension = install_with_backend(builder, object(), lambda _config: True)
    session = InMemoryCodexSession(cwd="C:/work", goal_tools_enabled_value=True)
    thread_store = ExtensionData("thread-1")
    turn_store = ExtensionData("turn-1")
    asyncio.run(
        extension.on_thread_start(
            ThreadStartInput(
                config=session,
                session_source=SessionSource.default(),
                persistent_thread_state_available=True,
                session_store=ExtensionData("session-1"),
                thread_store=thread_store,
            )
        )
    )
    runtime = thread_store.get(GoalRuntimeHandle)
    assert runtime is not None
    runtime.accounting_state.start_turn("turn-1", ModeKind.DEFAULT, TokenUsage())

    asyncio.run(
        extension.on_token_usage(
            ExtensionData("session-1"),
            thread_store,
            turn_store,
            TokenUsageInfo(
                total_token_usage=TokenUsage(
                    input_tokens=120,
                    cached_input_tokens=14,
                    output_tokens=42,
                    total_tokens=162,
                ),
                last_token_usage=TokenUsage(),
                model_context_window=128000,
            ),
        )
    )
    runtime.accounting_state.mark_turn_goal_active("turn-1", "goal-1")
    snapshot = runtime.accounting_state.progress_snapshot("turn-1")
    assert snapshot is not None
    assert snapshot.token_delta == 148

    recorded = runtime.accounting_state.record_token_usage(
        "turn-1",
        TokenUsage(input_tokens=127, cached_input_tokens=16, output_tokens=52, total_tokens=189),
    )
    assert recorded is not None
    assert recorded.turn_delta == 163


def test_installed_tools_share_extension_accounting_and_event_sink() -> None:
    # Rust crate/module/test:
    # codex-goal-extension::tool::update_goal_can_block_and_accounts_final_progress.
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    _init_goal_schema(connection)
    state_dbs = SimpleNamespace(thread_goals=lambda: GoalStore(connection))
    sink = _RecordingEventSink()
    builder = ExtensionRegistryBuilder.with_event_sink(sink)
    extension = install_with_backend(builder, state_dbs, lambda _config: True)
    registry = builder.build()
    session_store = ExtensionData("session-1")
    thread_store = ExtensionData("00000000-0000-0000-0000-000000000123")
    turn_store = ExtensionData("turn-1")

    asyncio.run(
        extension.on_thread_start(
            ThreadStartInput(
                config=SimpleNamespace(goal_tools_enabled_value=True),
                session_source=SessionSource.cli(),
                persistent_thread_state_available=True,
                session_store=session_store,
                thread_store=thread_store,
            )
        )
    )
    asyncio.run(
        extension.on_turn_start(
            TurnStartInput(
                turn_id="turn-1",
                collaboration_mode=CollaborationMode(ModeKind.DEFAULT, Settings(model="test-model")),
                token_usage_at_turn_start=TokenUsage(),
                session_store=session_store,
                thread_store=thread_store,
                turn_store=turn_store,
            )
        )
    )
    tools = {
        tool.tool_name().name: tool
        for tool in registry.tool_contributors()[0].tools(session_store, thread_store)
    }
    asyncio.run(
        tools["create_goal"].handle(
            SimpleNamespace(
                call_id="call-create-goal",
                payload=ToolPayload.function('{"objective":"ship goal extension backend"}'),
            )
        )
    )
    asyncio.run(
        extension.on_token_usage(
            session_store,
            thread_store,
            turn_store,
            TokenUsageInfo(
                total_token_usage=TokenUsage(
                    input_tokens=20,
                    cached_input_tokens=5,
                    output_tokens=8,
                    reasoning_output_tokens=2,
                    total_tokens=30,
                ),
                last_token_usage=TokenUsage(),
                model_context_window=128000,
            ),
        )
    )
    output = asyncio.run(
        tools["update_goal"].handle(
            SimpleNamespace(
                call_id="call-update-goal",
                payload=ToolPayload.function('{"status":"blocked"}'),
            )
        )
    )
    goal = asyncio.run(state_dbs.thread_goals().get_thread_goal(thread_store.level_id()))

    assert goal is not None
    assert goal.tokens_used == 23
    assert goal.status.value == "blocked"
    assert json.loads(output.body[0].text)["goal"]["tokensUsed"] == 23
    assert [event.id for event in sink.events] == [
        "call-create-goal",
        "call-update-goal",
        "call-update-goal",
    ]
    assert [event.msg.payload.goal.status for event in sink.events] == [
        ThreadGoalStatus.ACTIVE,
        ThreadGoalStatus.ACTIVE,
        ThreadGoalStatus.BLOCKED,
    ]
    assert [event.msg.payload.turn_id for event in sink.events] == ["turn-1", "turn-1", "turn-1"]


@pytest.mark.asyncio
async def test_product_goal_continuation_reuses_session_and_persisted_accounting(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Rust crate/module anchors:
    # - codex-core::session::turn::built_tools
    # - codex-core::goals::{create_thread_goal,goal_runtime_apply}
    # - codex-core::goals::maybe_start_goal_continuation_turn
    # The first turn creates a goal through the built-in core executor;
    # turn-stop accounts later usage, and the next hidden GoalContext must be
    # built from that persisted goal on the same Session.
    now = [100.0]
    monkeypatch.setattr("pycodex.core.goals.time.monotonic", lambda: now[0])
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))

    connection = sqlite3.connect(":memory:", check_same_thread=False)
    _init_goal_schema(connection)
    state_dbs = SimpleNamespace(thread_goals=lambda: GoalStore(connection))
    thread_id = str(uuid4())
    config = ExecSessionConfig(
        model="gpt-test",
        model_provider_id="openai",
        cwd=tmp_path,
    )
    model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
    session = create_exec_core_session(
        config,
        model_info,
        thread_id=thread_id,
        state_db=state_dbs,
    )
    queued = []
    session.goal_continuation_callback = lambda item, goal: queued.append((item, goal))
    client = ModelClient(
        session_id=thread_id,
        thread_id=thread_id,
        installation_id="install",
        session_source=SessionSource.cli(),
    )
    provider = {"base_url": "https://example.test/v1"}
    first_requests = []

    async def first_sampler(request):
        first_requests.append(request.request_plan)
        if len(first_requests) == 1:
            return SimpleNamespace(
                response_items=(
                    ResponseItem.function_call(
                        "create_goal",
                        '{"objective":"finish module parity","token_budget":1000}',
                        "call-create-goal",
                    ),
                ),
                raw_result={
                    "usage": {
                        "input_tokens": 100,
                        "input_tokens_details": {"cached_tokens": 20},
                        "output_tokens": 10,
                        "total_tokens": 110,
                    }
                },
            )
        now[0] = 103.0
        return SimpleNamespace(
            response_items=(
                ResponseItem.message("assistant", (ContentItem.output_text("first-turn progress"),)),
            ),
            raw_result={
                "usage": {
                    "input_tokens": 20,
                    "input_tokens_details": {"cached_tokens": 5},
                    "output_tokens": 6,
                    "total_tokens": 26,
                }
            },
        )

    first = await run_user_turn_sampling_from_session(
        session,
        (UserInput.text_input("start parity work"),),
        client,
        provider,
        model_info,
        first_sampler,
    )
    stored_after_first = await state_dbs.thread_goals().get_thread_goal(thread_id)

    assert stored_after_first is not None
    assert stored_after_first.status.value == "active"
    assert stored_after_first.tokens_used == 21
    assert stored_after_first.time_used_seconds == 3
    first_event_types = [item.payload.type for item in first.rollout_items if item.type == "event_msg"]
    assert first_event_types[0] == "task_started"
    assert first_event_types[-1] == "task_complete"
    assert first_event_types.count("thread_goal_updated") == 2
    assert max(index for index, value in enumerate(first_event_types) if value == "thread_goal_updated") < (
        len(first_event_types) - 1
    )

    assert len(queued) == 1
    continuation_item, continuation_goal = queued[0]
    continuation_text = "\n".join(content.text for content in continuation_item.content)
    assert continuation_goal.tokens_used == 21
    assert continuation_goal.time_used_seconds == 3
    assert "<goal_context>" in continuation_text
    assert "- Tokens used: 21" in continuation_text
    assert "- Token budget: 1000" in continuation_text
    assert "- Tokens remaining: 979" in continuation_text

    second_requests = []

    async def second_sampler(request):
        second_requests.append(request.request_plan)
        now[0] = 105.0
        return SimpleNamespace(
            response_items=(
                ResponseItem.message("assistant", (ContentItem.output_text("second-turn progress"),)),
            ),
            raw_result={
                "usage": {
                    "input_tokens": 12,
                    "input_tokens_details": {"cached_tokens": 2},
                    "output_tokens": 4,
                    "total_tokens": 16,
                }
            },
        )

    second = await run_user_turn_sampling_from_session(
        session,
        (UserInput.text_input(continuation_text),),
        client,
        provider,
        model_info,
        second_sampler,
    )
    second_prompt_text = json.dumps(
        [item.to_mapping() for item in second_requests[0].prompt.input],
        ensure_ascii=False,
    )
    second_tool_names = {spec["name"] for spec in second_requests[0].prompt.tools}

    assert "<goal_context>" in second_prompt_text
    assert "- Tokens used: 21" in second_prompt_text
    assert "first-turn progress" in second_prompt_text
    assert "call-create-goal" in second_prompt_text
    assert {"get_goal", "create_goal", "update_goal"}.issubset(second_tool_names)
    assert second.rollout_items[0].type == "event_msg"
    assert second.rollout_items[0].payload.type == "task_started"
    assert second.rollout_items[-1].payload.type == "task_complete"

    stored_after_second = await state_dbs.thread_goals().get_thread_goal(thread_id)
    assert stored_after_second is not None
    assert stored_after_second.tokens_used == 35
    assert stored_after_second.time_used_seconds == 5

    # Rust session tests: interrupt_accounts_active_goal_without_pausing.
    # Interrupt accounts elapsed progress but does not pause or enqueue another
    # continuation; a later user turn can therefore resume the same active goal.
    class CancellationToken:
        def __init__(self) -> None:
            self.event = asyncio.Event()

        def cancel(self) -> None:
            self.event.set()

        def is_cancelled(self) -> bool:
            return self.event.is_set()

        async def cancelled(self) -> None:
            await self.event.wait()

    queued.clear()
    cancellation = CancellationToken()
    interrupted_started = asyncio.Event()

    async def interrupted_sampler(_request):
        now[0] = 108.0
        interrupted_started.set()
        await asyncio.sleep(30)
        raise AssertionError("cancelled sampler must not complete")

    interrupted_task = asyncio.create_task(
        run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("continue after inspection"),),
            client,
            provider,
            model_info,
            interrupted_sampler,
            cancellation_token=cancellation,
        )
    )
    await asyncio.wait_for(interrupted_started.wait(), timeout=1)
    cancellation.cancel()
    interrupted = await asyncio.wait_for(interrupted_task, timeout=1)
    stored_after_interrupt = await state_dbs.thread_goals().get_thread_goal(thread_id)

    assert interrupted.turn_status == "interrupted"
    assert stored_after_interrupt is not None
    assert stored_after_interrupt.status.value == "active"
    assert stored_after_interrupt.tokens_used == 35
    assert stored_after_interrupt.time_used_seconds == 8
    assert queued == []

    # Rust session tests:
    # usage_limit_runtime_stops_active_goal_and_prevents_idle_continuation.
    async def usage_limited_sampler(_request):
        now[0] = 110.0
        raise CodexErr.usage_limit_reached(UsageLimitReachedError())

    usage_limited = await run_user_turn_sampling_from_session(
        session,
        (UserInput.text_input("resume after interrupt"),),
        client,
        provider,
        model_info,
        usage_limited_sampler,
    )
    stored_after_usage_limit = await state_dbs.thread_goals().get_thread_goal(thread_id)

    assert usage_limited.turn_status == "completed"
    assert stored_after_usage_limit is not None
    assert stored_after_usage_limit.status.value == "usage_limited"
    assert stored_after_usage_limit.tokens_used == 35
    assert stored_after_usage_limit.time_used_seconds == 10
    assert queued == []


class _RecordingEventSink:
    def __init__(self) -> None:
        self.events: list[object] = []

    def emit(self, event: object) -> None:
        self.events.append(event)


def _init_goal_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
CREATE TABLE thread_goals (
    thread_id TEXT PRIMARY KEY NOT NULL,
    goal_id TEXT NOT NULL,
    objective TEXT NOT NULL,
    status TEXT NOT NULL,
    token_budget INTEGER,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    time_used_seconds INTEGER NOT NULL DEFAULT 0,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL
);
        """
    )
