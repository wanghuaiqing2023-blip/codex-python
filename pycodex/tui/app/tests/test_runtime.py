import asyncio
import time
from types import SimpleNamespace

from pycodex.core.session.turn.runtime import UserTurnSamplingResult
from pycodex.protocol import CommandExecutionItem, ContentItem, FunctionCallOutputPayload, ResponseItem, TurnItem
from pycodex.tui.app.runtime import (
    CoreExecActiveThreadRuntime,
    ExecFunctionActiveThreadRuntime,
    TuiAppRuntime,
    exec_run_plan_for_app_command,
    user_turn_prompt,
)
from pycodex.tui.app_command import AppCommand
from pycodex.tui.chatwidget.protocol import ServerNotification


def test_tui_app_runtime_submits_user_turn_through_active_thread_routing() -> None:
    # Rust composition contract:
    # - codex-tui::chatwidget::input_submission builds AppCommand::UserTurn.
    # - codex-tui::app::thread_routing submits active-thread ops via submit_thread_op.
    # - codex-tui::app event loop consumes active-thread notifications.
    runtime = TuiAppRuntime(active_thread_runtime=ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "pong\n")))

    stream = runtime.submit_user_turn("ping")

    assert runtime.submitted_ops[-1].kind == "UserTurn"
    assert user_turn_prompt(runtime.submitted_ops[-1]) == "ping"
    assert runtime.routing_plans[-1].action == "submit_thread_op"
    assert runtime.routing_plans[-1].app_server_call == (
        "submit_thread_op",
        {"thread_id": "primary", "op": runtime.submitted_ops[-1]},
    )

    notifications = []
    while True:
        event = stream.next_event(timeout=1)
        if event is None:
            break
        notifications.append(event.kind)
        runtime.handle_notification(event)
        if event.kind == "TurnCompleted":
            break

    assert notifications == ["TurnStarted", "AgentMessageDelta", "TurnCompleted"]
    assert runtime.chat_widget.run_state_status_text() == "Ready"
    assert runtime.chat_widget.assistant_text() == "pong"


def test_tui_app_runtime_accepts_response_started_without_text() -> None:
    # Rust-derived composition contract:
    # codex-core/src/client.rs streams response.created before text deltas; the
    # TUI app must treat that as a live turn status/redraw signal, not as a
    # second assistant-delta lane and not as an unsupported notification.
    runtime = TuiAppRuntime(active_thread_runtime=ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "")))

    runtime.handle_notification(ServerNotification("TurnStarted", {"turn": {"id": "turn-1", "thread_id": "primary"}}))
    runtime.handle_notification(ServerNotification("ResponseStarted", {"thread_id": "primary", "turn_id": "turn-1"}))

    assert runtime.chat_widget.assistant_text() == ""
    assert runtime.chat_widget.run_state_status_text() == "Working"


def test_core_exec_active_thread_runtime_maps_live_function_call_item_to_command(monkeypatch) -> None:
    # Rust composition contract:
    # codex-core emits completed function_call output items before tool
    # execution/follow-up text; codex-tui::app maps them to
    # ServerNotification::ItemStarted so the terminal can render command
    # progress before the first assistant text delta.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(
            SimpleNamespace(
                type="response_output_item_done",
                payload={
                    "item": ResponseItem.function_call(
                        "exec_command",
                        '{"cmd":"Get-Location","workdir":"C:\\\\repo"}',
                        "call-1",
                        id="item-1",
                    ).to_mapping()
                },
            )
        )
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        if event.kind == "TurnCompleted":
            break

    assert [event.kind for event in events] == ["TurnStarted", "ItemStarted", "TurnCompleted"]
    item = events[1].payload["item"]
    assert item["kind"] == "CommandExecution"
    assert item["command"] == "Get-Location"


def test_exec_function_active_thread_runtime_reports_failed_turn_without_throwing_to_tui() -> None:
    runtime = ExecFunctionActiveThreadRuntime(lambda _prompt: (7, "bad auth"))
    op = AppCommand.user_turn(
        [{"kind": "Text", "text": "hello"}],
        cwd=".",
        approval_policy=None,
        active_permission_profile=None,
        model="",
        effort=None,
        summary=None,
        service_tier=None,
        final_output_json_schema=None,
        collaboration_mode=None,
        personality=None,
    )

    stream = runtime.submit_thread_op("primary", op)
    events = []
    while True:
        event = stream.next_event(timeout=1)
        if event is None:
            break
        events.append(event)
        if event.kind == "TurnCompleted":
            break

    assert [event.kind for event in events] == ["TurnStarted", "AgentMessageDelta", "TurnCompleted"]
    assert events[-1].payload["turn"]["status"] == "Failed"
    assert events[-1].payload["turn"]["error"]["message"] == "bad auth"
    assert events[-1].payload["turn"]["error"]["exit_code"] == 7


def test_app_command_user_turn_builds_core_exec_plan() -> None:
    # Rust composition contract:
    # - codex-tui::chatwidget::input_submission sends AppCommand::UserTurn.
    # - codex-tui::app submits that op to the active thread as the turn boundary.
    # - codex-core/session/turn owns UserInput sampling.
    op = AppCommand.user_turn(
        [{"kind": "Text", "text": "hello"}],
        cwd=".",
        approval_policy=None,
        active_permission_profile=None,
        model="",
        effort=None,
        summary=None,
        service_tier=None,
        final_output_json_schema=None,
        collaboration_mode=None,
        personality=None,
    )

    plan = exec_run_plan_for_app_command(op)

    assert plan.initial_operation.kind == "user_turn"
    assert plan.initial_operation.items[0].text == "hello"
    assert plan.prompt_summary == "hello"


def test_core_exec_active_thread_runtime_forwards_core_result_to_chatwidget(monkeypatch) -> None:
    # Rust-derived composition test:
    # codex-tui::app observes active-thread server notifications and
    # codex-tui::chatwidget::protocol applies them to turn/streaming state.
    seen = {}

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        seen["items"] = tuple(item.text for item in plan.initial_operation.items)
        return UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("pong"),)),),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    app_runtime = TuiAppRuntime(
        active_thread_runtime=CoreExecActiveThreadRuntime(
            session_config=object(),
            model_client=object(),
            provider=object(),
            model_info=object(),
            auth=None,
        )
    )

    stream = app_runtime.submit_user_turn("ping")
    kinds = []
    while True:
        event = stream.next_event(timeout=1)
        if event is None:
            break
        kinds.append(event.kind)
        app_runtime.handle_notification(event)
        if event.kind == "TurnCompleted":
            break

    assert seen["items"] == ("ping",)
    assert kinds == ["TurnStarted", "AgentMessageDelta", "TurnCompleted"]
    assert app_runtime.chat_widget.assistant_text() == "pong"
    assert app_runtime.chat_widget.run_state_status_text() == "Ready"


def test_core_exec_active_thread_runtime_consumes_startup_prewarm_once(monkeypatch) -> None:
    # Rust-derived composition test:
    # codex-core/src/session_startup_prewarm.rs schedules a prewarmed
    # ModelClientSession, codex-core/src/tasks/regular.rs consumes it for the
    # first regular turn, and codex-core/src/session/turn.rs uses it instead
    # of creating a new session.
    prewarmed_session = object()
    seen_sessions = []

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        seen_sessions.append(kwargs.get("model_session"))
        return UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("pong"),)),),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
        prewarmed_model_session=prewarmed_session,
    )

    for prompt in ("first", "second"):
        stream = runtime.submit_thread_op(
            "primary",
            AppCommand.user_turn(
                [{"kind": "Text", "text": prompt}],
                cwd=".",
                approval_policy=None,
                active_permission_profile=None,
                model="",
                effort=None,
                summary=None,
                service_tier=None,
                final_output_json_schema=None,
                collaboration_mode=None,
                personality=None,
            ),
        )
        while True:
            event = stream.next_event(timeout=1)
            if event is None or event.kind == "TurnCompleted":
                break

    assert seen_sessions == [prewarmed_session, None]


def test_core_exec_active_thread_runtime_schedules_startup_prewarm(monkeypatch) -> None:
    # Rust-derived composition test:
    # startup prewarm runs before the first regular turn and the first turn
    # consumes the warmed session through the canonical session lane.
    prewarmed_session = object()
    seen_sessions = []
    prewarm_calls = []

    class ModelClient:
        def new_session(self):
            return prewarmed_session

    class ProviderInfo:
        def websocket_connect_timeout(self):
            return 1000

    class Provider:
        def info(self):
            return ProviderInfo()

    class ModelInfo:
        slug = "gpt-test"

    async def fake_prewarm(session_config, model_client, provider, model_info, **kwargs):
        prewarm_calls.append((session_config, model_client, provider, model_info, kwargs.get("model_session")))
        await asyncio.sleep(0)
        return kwargs.get("model_session")

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        seen_sessions.append(kwargs.get("model_session"))
        return UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("pong"),)),),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.prewarm_exec_core_websocket_session", fake_prewarm)
    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=ModelClient(),
        provider=Provider(),
        model_info=ModelInfo(),
        auth=None,
        startup_prewarm_enabled=True,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )
    while True:
        event = stream.next_event(timeout=1)
        if event is None or event.kind == "TurnCompleted":
            break

    assert prewarm_calls == [(runtime.session_config, runtime.model_client, runtime.provider, runtime.model_info, prewarmed_session)]
    assert seen_sessions == [prewarmed_session]


def test_core_exec_active_thread_runtime_does_not_wait_full_timeout_for_stale_prewarm(monkeypatch) -> None:
    # Rust source: codex-core/src/session_startup_prewarm.rs.
    # Contract: resolving startup prewarm waits only
    # websocket_connect_timeout - age_at_first_turn. Once the warmup is already
    # older than the timeout, the first regular turn proceeds without paying a
    # second full timeout.
    prewarmed_session = object()
    seen_sessions = []

    class ModelClient:
        def new_session(self):
            return prewarmed_session

    class ProviderInfo:
        def websocket_connect_timeout(self):
            return 10

    class Provider:
        def info(self):
            return ProviderInfo()

    class ModelInfo:
        slug = "gpt-test"

    async def slow_prewarm(session_config, model_client, provider, model_info, **kwargs):
        await asyncio.sleep(0.2)
        return kwargs.get("model_session")

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        seen_sessions.append(kwargs.get("model_session"))
        return UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("pong"),)),),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.prewarm_exec_core_websocket_session", slow_prewarm)
    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=ModelClient(),
        provider=Provider(),
        model_info=ModelInfo(),
        startup_prewarm_enabled=True,
    )
    time.sleep(0.05)

    started = time.monotonic()
    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )
    while True:
        event = stream.next_event(timeout=1)
        if event is None or event.kind == "TurnCompleted":
            break
    elapsed = time.monotonic() - started

    assert elapsed < 0.1
    assert seen_sessions == [None]


def test_core_exec_active_thread_runtime_does_not_force_fallback_after_generic_prewarm_failure(monkeypatch) -> None:
    # Rust modules:
    # - codex-core/src/session_startup_prewarm.rs
    # - codex-core/src/client.rs::ModelClientSession::prewarm_websocket
    # Contract: a generic startup prewarm failure resolves as unavailable and
    # is not itself a sticky fallback decision. Sticky HTTP fallback is owned by
    # the websocket transport fallback policy, such as 426 or retry exhaustion.
    fallback_calls = []
    seen_disabled = []

    class ModelClient:
        disabled = False

        def new_session(self):
            return object()

        def force_http_fallback(self):
            fallback_calls.append(True)
            self.disabled = True
            return True

    class ProviderInfo:
        def websocket_connect_timeout(self):
            return 1000

    class Provider:
        def info(self):
            return ProviderInfo()

    class ModelInfo:
        slug = "gpt-test"

    async def failing_prewarm(*args, **kwargs):
        raise RuntimeError("websocket unavailable")

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        seen_disabled.append(model_client.disabled)
        return UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("pong"),)),),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.prewarm_exec_core_websocket_session", failing_prewarm)
    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=ModelClient(),
        provider=Provider(),
        model_info=ModelInfo(),
        startup_prewarm_enabled=True,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )
    while True:
        event = stream.next_event(timeout=1)
        if event is None or event.kind == "TurnCompleted":
            break

    assert fallback_calls == []
    assert seen_disabled == [False]


def test_core_exec_active_thread_runtime_forwards_core_delta_before_result(monkeypatch) -> None:
    # Rust composition contract:
    # codex-tui observes active-thread app-server notifications while the turn
    # is running. The Python TUI adapter must forward core session stream
    # events as they are emitted, not only after the sampling result returns.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(
            SimpleNamespace(
                type="agent_message_content_delta",
                payload=SimpleNamespace(delta="live chunk"),
            )
        )
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(
            request_plan=None,
            session_events=(
                SimpleNamespace(
                    type="agent_message_content_delta",
                    payload=SimpleNamespace(delta="live chunk"),
                ),
            ),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    first = stream.next_event(timeout=1)
    second = stream.next_event(timeout=1)
    assert first is not None and first.kind == "TurnStarted"
    assert second is not None and second.kind == "AgentMessageDelta"
    assert second.payload["delta"] == "live chunk"

    remaining = []
    while True:
        event = stream.next_event(timeout=1)
        if event is None:
            break
        remaining.append(event)
        if event.kind == "TurnCompleted":
            break

    assert [event.kind for event in remaining] == ["TurnCompleted"]


def test_core_exec_active_thread_runtime_normalizes_transport_delta_into_session_lane(monkeypatch) -> None:
    # Rust composition contract:
    # codex-core/src/session/turn.rs maps ResponseEvent::OutputTextDelta into
    # sess.send_event(EventMsg::AgentMessageContentDelta); codex-tui::app then
    # observes the session/server-notification lane. Python may observe raw
    # websocket frames for latency, but TUI rendering must still enter through
    # the same canonical session event lane.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(SimpleNamespace(type="agent_message_content_delta", payload=SimpleNamespace(delta="transport live")))
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    first = stream.next_event(timeout=1)
    second = stream.next_event(timeout=1)
    assert first is not None and first.kind == "TurnStarted"
    assert second is not None and second.kind == "AgentMessageDelta"
    assert second.payload["delta"] == "transport live"

    completed = None
    while completed is None:
        event = stream.next_event(timeout=1)
        assert event is not None
        if event.kind == "TurnCompleted":
            completed = event

    assert completed.payload["turn"]["status"] == "Completed"


def test_core_exec_active_thread_runtime_does_not_attach_raw_stream_observer(monkeypatch) -> None:
    # Rust composition contract:
    # codex-core/src/session/turn.rs is the sole mapper from ResponseEvent into
    # EventMsg, and codex-tui consumes that session/app-server notification
    # lane. The product TUI must not also attach a raw stream observer as a
    # second visible lane.
    seen_kwargs = {}

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        seen_kwargs.update(kwargs)
        kwargs["session_event_observer"](
            SimpleNamespace(
                type="agent_message_content_delta",
                payload=SimpleNamespace(delta="single lane"),
            )
        )
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        if event.kind == "TurnCompleted":
            break

    assert "stream_event_observer" not in seen_kwargs
    assert [event.payload["delta"] for event in events if event.kind == "AgentMessageDelta"] == ["single lane"]


def test_core_exec_active_thread_runtime_keeps_multiple_transport_delta_chunks(monkeypatch) -> None:
    # Rust composition contract:
    # ResponseEvent::OutputTextDelta is an ordered stream; each chunk from the
    # same canonical stream lane must render. Replay suppression must be
    # source-based, not "first delta wins" for the whole turn.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(SimpleNamespace(type="agent_message_content_delta", payload=SimpleNamespace(delta="hel")))
        observer(SimpleNamespace(type="agent_message_content_delta", payload=SimpleNamespace(delta="lo")))
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        if event.kind == "TurnCompleted":
            break

    deltas = [event.payload["delta"] for event in events if event.kind == "AgentMessageDelta"]
    assert deltas == ["hel", "lo"]


def test_core_exec_active_thread_runtime_uses_one_delta_lane_even_when_replay_differs(monkeypatch) -> None:
    # Rust composition contract:
    # Rust has one visible assistant-delta lane from core session events into
    # codex-tui; it does not fuzzy-match text to remove duplicates. Python's
    # raw websocket observation is normalized into that lane, and a later replay
    # from the result/session side must not become a second visible message even
    # when the text differs by a small amount.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        kwargs["session_event_observer"](
            SimpleNamespace(
                type="agent_message_content_delta",
                payload=SimpleNamespace(delta="hello"),
            )
        )
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(
            request_plan=None,
            session_events=(
                SimpleNamespace(
                    type="agent_message_content_delta",
                    payload=SimpleNamespace(delta="hello!"),
                ),
            ),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        if event.kind == "TurnCompleted":
            break

    deltas = [event.payload["delta"] for event in events if event.kind == "AgentMessageDelta"]
    assert deltas == ["hello"]


def test_core_exec_active_thread_runtime_surfaces_exec_command_item_before_agent_text(monkeypatch) -> None:
    # Rust composition contract:
    # codex-api/codex-core expose response output items before assistant text,
    # and codex-tui::app forwards command execution lifecycle as
    # ServerNotification::ItemStarted/ItemCompleted. This keeps tool work
    # visible during the no-agent-text phase of a turn.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(
            SimpleNamespace(
                type="response_output_item_done",
                payload=SimpleNamespace(
                    item=ResponseItem.function_call(
                        "exec_command",
                        '{"cmd":"Get-Content README.md","workdir":"C:\\\\repo"}',
                        "call-1",
                        id="item-1",
                    ),
                ),
            )
        )
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(
            request_plan=None,
            tool_response_items=(
                ResponseItem(
                    type="function_call_output",
                    call_id="call-1",
                    output=FunctionCallOutputPayload.text("readme contents", success=True),
                ),
            ),
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("done"),)),),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "analyze"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        if event.kind == "TurnCompleted":
            break

    assert [event.kind for event in events] == [
        "TurnStarted",
        "ItemStarted",
        "ItemCompleted",
        "AgentMessageDelta",
        "TurnCompleted",
    ]
    started_item = events[1].payload["item"]
    completed_item = events[2].payload["item"]
    assert started_item["kind"] == "CommandExecution"
    assert started_item["command"] == "Get-Content README.md"
    assert started_item["cwd"] == "C:\\repo"
    assert completed_item["status"] == "Completed"
    assert completed_item["aggregated_output"] == "readme contents"
    app_runtime = TuiAppRuntime(active_thread_runtime=runtime)
    app_runtime.handle_notification(events[0])
    app_runtime.handle_notification(events[1])
    app_runtime.handle_notification(events[2])
    assert app_runtime.chat_widget.command_lifecycle.history_cells[0].calls[0].call_id == "call-1"


def test_core_exec_active_thread_runtime_forwards_canonical_item_lifecycle(monkeypatch) -> None:
    # Rust-derived composition test:
    # codex-core::session emits EventMsg::ItemStarted/ItemCompleted carrying a
    # TurnItem, app-server turns that into ServerNotification::ItemStarted and
    # ::ItemCompleted, and codex-tui::chatwidget::protocol consumes the command
    # execution lifecycle without a raw ResponseItem side channel.
    started = TurnItem.command_execution(
        CommandExecutionItem(
            id="call-1",
            command="Get-ChildItem",
            cwd="C:\\repo",
            status="inProgress",
            source="agent",
            command_actions=({"type": "unknown", "cmd": "Get-ChildItem"},),
        )
    )
    completed = TurnItem.command_execution(
        CommandExecutionItem(
            id="call-1",
            command="Get-ChildItem",
            cwd="C:\\repo",
            status="completed",
            source="agent",
            command_actions=({"type": "unknown", "cmd": "Get-ChildItem"},),
            aggregated_output="file.txt",
            exit_code=0,
            duration_ms=12,
        )
    )

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(
            SimpleNamespace(
                type="item_started",
                payload=SimpleNamespace(thread_id="primary", turn_id="terminal-turn", item=started, started_at_ms=1),
            )
        )
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(
            request_plan=None,
            session_events=(
                SimpleNamespace(
                    type="item_started",
                    payload=SimpleNamespace(thread_id="primary", turn_id="terminal-turn", item=started, started_at_ms=1),
                ),
                SimpleNamespace(
                    type="item_completed",
                    payload=SimpleNamespace(thread_id="primary", turn_id="terminal-turn", item=completed, completed_at_ms=2),
                ),
            ),
            tool_response_items=(
                ResponseItem(
                    type="function_call_output",
                    call_id="call-1",
                    output=FunctionCallOutputPayload.text("fallback duplicate", success=True),
                ),
            ),
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("done"),)),),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    app_runtime = TuiAppRuntime(
        active_thread_runtime=CoreExecActiveThreadRuntime(
            session_config=object(),
            model_client=object(),
            provider=object(),
            model_info=object(),
            auth=None,
        )
    )

    stream = app_runtime.submit_user_turn("analyze")
    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        app_runtime.handle_notification(event)
        if event.kind == "TurnCompleted":
            break

    assert [event.kind for event in events] == [
        "TurnStarted",
        "ItemStarted",
        "ItemCompleted",
        "AgentMessageDelta",
        "TurnCompleted",
    ]
    assert events[1].payload["item"]["kind"] == "CommandExecution"
    assert events[1].payload["item"]["command_actions"] == ({"type": "unknown", "cmd": "Get-ChildItem"},)
    assert events[2].payload["item"]["aggregated_output"] == "file.txt"
    assert app_runtime.chat_widget.command_lifecycle.history_cells[0].calls[0].call_id == "call-1"
    assert app_runtime.chat_widget.command_lifecycle.history_cells[0].calls[0].output.aggregated_output == "file.txt"


def test_core_exec_active_thread_runtime_forwards_reasoning_delta(monkeypatch) -> None:
    # Rust composition contract:
    # codex-core/src/session/turn.rs maps ResponseEvent::ReasoningSummaryDelta
    # into EventMsg::ReasoningContentDelta. codex-tui::app must treat that
    # session event as a visible ReasoningSummaryTextDelta.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        kwargs["session_event_observer"](SimpleNamespace(type="reasoning_content_delta", payload=SimpleNamespace(delta="**Reading**")))
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    first = stream.next_event(timeout=1)
    second = stream.next_event(timeout=1)
    assert first is not None and first.kind == "TurnStarted"
    assert second is not None and second.kind == "ReasoningSummaryTextDelta"
    assert second.payload["delta"] == "**Reading**"


def test_core_exec_active_thread_runtime_forwards_reasoning_section_and_raw_delta(monkeypatch) -> None:
    # Rust composition contract:
    # - codex-core/src/session/turn.rs forwards summary text as
    #   ReasoningContentDelta, section breaks as AgentReasoningSectionBreak,
    #   and raw text as ReasoningRawContentDelta.
    # - codex-tui::app preserves them as distinct ServerNotification variants.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(SimpleNamespace(type="reasoning_content_delta", payload=SimpleNamespace(delta="**Inspecting**")))
        observer(SimpleNamespace(type="agent_reasoning_section_break", payload=SimpleNamespace(summary_index=0)))
        observer(SimpleNamespace(type="reasoning_raw_content_delta", payload=SimpleNamespace(delta="raw detail")))
        await asyncio.sleep(0.01)
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        if event.kind == "TurnCompleted":
            break

    assert [event.kind for event in events[:4]] == [
        "TurnStarted",
        "ReasoningSummaryTextDelta",
        "ReasoningSummaryPartAdded",
        "ReasoningTextDelta",
    ]
    assert events[1].payload["delta"] == "**Inspecting**"
    assert events[3].payload["delta"] == "raw detail"


def test_core_exec_active_thread_runtime_surfaces_stream_error_when_no_agent_text(monkeypatch) -> None:
    # Rust composition contract: core stream/error events are user-visible turn
    # failures when the model never produces assistant text.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(
            SimpleNamespace(
                type="stream_error",
                payload=SimpleNamespace(
                    message="Reconnecting... 1/5",
                    additional_details="Error while reading the server response",
                ),
            )
        )
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    assert stream.next_event(timeout=1).kind == "TurnStarted"
    completed = stream.next_event(timeout=1)

    assert completed is not None
    assert completed.kind == "TurnCompleted"
    assert completed.payload["turn"]["status"] == "Failed"
    assert "Error while reading the server response" in completed.payload["turn"]["error"]["message"]
