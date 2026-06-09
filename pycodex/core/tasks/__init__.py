"""Task helper modules aligned with ``codex-core::tasks``."""

from __future__ import annotations

import asyncio
import inspect
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pycodex.core.codex_delegate import CancellationToken
from pycodex.core.context import TurnAborted
from pycodex.core.state.turn import ActiveTurn, RunningTask
from pycodex.features import Feature
from pycodex.protocol import ContentItem, EventMsg, ResponseItem, TurnAbortReason, TurnAbortedEvent, TurnCompleteEvent

from .compact import CompactTask, CompactTaskPlan
from .lifecycle import (
    emit_turn_abort_lifecycle,
    emit_turn_error_lifecycle,
    emit_turn_start_lifecycle,
    emit_turn_stop_lifecycle,
)
from .regular import RegularTask, SessionStartupPrewarmResolution
from .review import (
    REVIEW_INTERRUPTED_ASSISTANT_MESSAGE,
    REVIEW_ROLLOUT_ASSISTANT_MESSAGE_ID,
    REVIEW_ROLLOUT_USER_MESSAGE_ID,
    ReviewExitMessages,
    ReviewTask,
    collect_review_user_input,
    exit_review_mode,
    normalize_review_template_line_endings,
    parse_review_output_event,
    process_review_events,
    render_review_exit_interrupted,
    render_review_exit_success,
    review_exit_messages,
    start_review_conversation,
)

GRACEFULL_INTERRUPTION_TIMEOUT_MS = 100
TASK_COMPACT_METRIC = "codex.task.compact"
TURN_MEMORY_METRIC = "codex.turn.memory"
TURN_NETWORK_PROXY_METRIC = "codex.turn.network_proxy"


class InterruptedTurnHistoryMarker(str, Enum):
    DISABLED = "disabled"
    CONTEXTUAL_USER = "contextual_user"
    DEVELOPER = "developer"

    @classmethod
    def from_config(cls, config: Any) -> "InterruptedTurnHistoryMarker":
        if not bool(getattr(config, "agent_interrupt_message_enabled", False)):
            return cls.DISABLED
        features = getattr(config, "features", None)
        enabled = getattr(features, "enabled", None)
        if callable(enabled) and enabled(Feature.MULTI_AGENT_V2):
            return cls.DEVELOPER
        return cls.CONTEXTUAL_USER


def interrupted_turn_history_marker(marker: InterruptedTurnHistoryMarker | str) -> ResponseItem | None:
    marker = InterruptedTurnHistoryMarker(marker)
    if marker is InterruptedTurnHistoryMarker.DISABLED:
        return None
    if marker is InterruptedTurnHistoryMarker.CONTEXTUAL_USER:
        return TurnAborted.new(TurnAborted.INTERRUPTED_GUIDANCE).into_response_item()
    return ResponseItem.message(
        "developer",
        (ContentItem.input_text(TurnAborted.new(TurnAborted.INTERRUPTED_DEVELOPER_GUIDANCE).render()),),
    )


def bool_tag(value: bool) -> str:
    return "true" if value else "false"


def emit_turn_network_proxy_metric(
    session_telemetry: Any,
    network_proxy_active: bool,
    tmp_mem: tuple[str, str],
) -> None:
    session_telemetry.counter(
        TURN_NETWORK_PROXY_METRIC,
        1,
        [("active", bool_tag(network_proxy_active)), tmp_mem],
    )


def emit_turn_memory_metric(
    session_telemetry: Any,
    feature_enabled: bool,
    config_enabled: bool,
    has_citations: bool,
) -> None:
    read_allowed = feature_enabled and config_enabled
    session_telemetry.counter(
        TURN_MEMORY_METRIC,
        1,
        [
            ("read_allowed", bool_tag(read_allowed)),
            ("feature_enabled", bool_tag(feature_enabled)),
            ("config_use_memories", bool_tag(config_enabled)),
            ("has_citations", bool_tag(has_citations)),
        ],
    )


def emit_compact_metric(session_telemetry: Any, compact_type: str, manual: bool) -> None:
    session_telemetry.counter(
        TASK_COMPACT_METRIC,
        1,
        [("type", compact_type), ("manual", bool_tag(manual))],
    )


@dataclass(frozen=True)
class SessionTaskContext:
    session: Any
    turn_extension_data_value: Any

    @classmethod
    def new(cls, session: Any, turn_extension_data: Any) -> "SessionTaskContext":
        return cls(session, turn_extension_data)

    def clone_session(self) -> Any:
        return self.session

    def turn_extension_data(self) -> Any:
        return self.turn_extension_data_value

    def auth_manager(self) -> Any:
        return self.session.services.auth_manager

    def models_manager(self) -> Any:
        return self.session.services.models_manager


async def spawn_task(session: Any, turn_context: Any, input: list[Any], task: Any) -> None:
    """Abort existing work and start a new session task, mirroring Rust `Session::spawn_task`."""

    await _call_required(session, "abort_all_tasks", TurnAbortReason.REPLACED)
    clear_connector_selection = getattr(session, "clear_connector_selection", None)
    if callable(clear_connector_selection):
        await _maybe_await(clear_connector_selection())
    await start_task(session, turn_context, input, task)


async def start_task(session: Any, turn_context: Any, input: list[Any], task: Any) -> None:
    """Start a task and record a Rust-shaped `RunningTask` on the active turn."""

    task_kind = _call_task(task, "kind")
    cancellation_token = CancellationToken()
    done = asyncio.Event()
    session_ctx = SessionTaskContext.new(session, _field(turn_context, "extension_data"))
    await _mark_turn_started(turn_context)
    await _clear_guardian_rejection_turn(session, _field(turn_context, "sub_id"))
    await _emit_lifecycle(session, "emit_turn_start_lifecycle", turn_context)

    async def runner() -> None:
        last_agent_message: str | None = None
        try:
            last_agent_message = await _run_task(task, session_ctx, turn_context, list(input), cancellation_token.child_token())
            flush = getattr(session, "flush_rollout", None)
            if callable(flush):
                await _maybe_await(flush())
            if not cancellation_token.is_cancelled():
                await on_task_finished(session, turn_context, last_agent_message)
        finally:
            done.set()

    handle = asyncio.create_task(runner())
    running_task = RunningTask(
        done=done,
        kind=task_kind,
        task=task,
        cancellation_token=cancellation_token,
        handle=handle,
        turn_context=turn_context,
        turn_extension_data=_field(turn_context, "extension_data"),
        timer=_start_turn_timer(turn_context),
    )
    active_turn = _ensure_active_turn(session)
    active_turn.task = running_task


async def maybe_start_turn_for_pending_work(session: Any) -> None:
    await maybe_start_turn_for_pending_work_with_sub_id(session, str(uuid.uuid4()))


async def maybe_start_turn_for_pending_work_with_sub_id(session: Any, sub_id: str) -> None:
    input_queue = _field(session, "input_queue")
    checker = getattr(input_queue, "has_trigger_turn_mailbox_items", None)
    if not callable(checker) or not bool(await _maybe_await(checker())):
        return
    if _active_turn(session).task is not None:
        return
    turn_context = await _call_required(session, "new_default_turn_with_sub_id", sub_id)
    warning = getattr(session, "maybe_emit_unknown_model_warning_for_turn", None)
    if callable(warning):
        await _maybe_await(warning(turn_context))
    await start_task(session, turn_context, [], RegularTask.new())


async def abort_all_tasks(session: Any, reason: TurnAbortReason | str) -> None:
    reason = TurnAbortReason(reason)
    active_turn = _active_turn(session)
    task = active_turn.task
    if task is None:
        return
    active_turn.task = None
    await handle_task_abort(session, task, reason)
    await _emit_lifecycle(session, "emit_turn_abort_lifecycle", reason, _field(task.turn_context, "extension_data"))
    input_queue = _field(session, "input_queue")
    clear_pending = getattr(input_queue, "clear_pending", None)
    if callable(clear_pending):
        await _maybe_await(clear_pending(active_turn))
    if reason is TurnAbortReason.INTERRUPTED:
        await maybe_start_turn_for_pending_work(session)


async def abort_turn_if_active(session: Any, turn_id: str, reason: TurnAbortReason | str) -> bool:
    active_turn = _active_turn(session)
    task = active_turn.task
    if task is None or str(_field(task.turn_context, "sub_id")) != str(turn_id):
        return False
    active_turn.task = None
    await handle_task_abort(session, task, TurnAbortReason(reason))
    await _emit_lifecycle(session, "emit_turn_abort_lifecycle", TurnAbortReason(reason), _field(task.turn_context, "extension_data"))
    return True


async def on_task_finished(session: Any, turn_context: Any, last_agent_message: str | None) -> None:
    """Finish a task uniformly from the root tasks module."""

    active_turn = _active_turn(session)
    if active_turn.task is not None:
        handle = _field(active_turn.task, "handle")
        if handle is not None and hasattr(handle, "done") and not handle.done():
            pass
        active_turn.task = None
    await _emit_lifecycle(session, "emit_turn_stop_lifecycle", _field(turn_context, "extension_data"))
    completed_at, duration_ms = await _completed_at_and_duration_ms(turn_context)
    time_to_first_token_ms = await _time_to_first_token_ms(turn_context)
    await _send_event(
        session,
        turn_context,
        EventMsg.with_payload(
            "task_complete",
            TurnCompleteEvent(
                turn_id=str(_field(turn_context, "sub_id")),
                last_agent_message=last_agent_message,
                completed_at=completed_at,
                duration_ms=duration_ms,
                time_to_first_token_ms=time_to_first_token_ms,
            ),
        ),
    )
    await _clear_guardian_rejection_turn(session, _field(turn_context, "sub_id"))


async def handle_task_abort(session: Any, task: RunningTask, reason: TurnAbortReason) -> None:
    token = _field(task, "cancellation_token")
    cancel = getattr(token, "cancel", None)
    if callable(cancel):
        cancel()
    done = _field(task, "done")
    try:
        if done is not None:
            await asyncio.wait_for(done.wait(), GRACEFULL_INTERRUPTION_TIMEOUT_MS / 1000)
    except asyncio.TimeoutError:
        pass
    handle = _field(task, "handle")
    if handle is not None and hasattr(handle, "cancel"):
        handle.cancel()
    await _abort_task_object(task.task, SessionTaskContext.new(session, task.turn_extension_data), task.turn_context)
    if reason is TurnAbortReason.INTERRUPTED:
        marker = interrupted_turn_history_marker(InterruptedTurnHistoryMarker.from_config(_field(task.turn_context, "config")))
        if marker is not None:
            record = getattr(session, "record_conversation_items", None)
            if callable(record):
                await _maybe_await(record(task.turn_context, [marker]))
            flush = getattr(session, "flush_rollout", None)
            if callable(flush):
                await _maybe_await(flush())
    completed_at, duration_ms = await _completed_at_and_duration_ms(task.turn_context)
    await _send_event(
        session,
        task.turn_context,
        EventMsg.with_payload(
            "turn_aborted",
            TurnAbortedEvent(
                turn_id=str(_field(task.turn_context, "sub_id")),
                reason=reason,
                completed_at=completed_at,
                duration_ms=duration_ms,
            ),
        ),
    )
    await _clear_guardian_rejection_turn(session, _field(task.turn_context, "sub_id"))


def _ensure_active_turn(session: Any) -> ActiveTurn:
    active = getattr(session, "active_turn", None)
    if isinstance(active, ActiveTurn):
        return active
    active = ActiveTurn()
    setattr(session, "active_turn", active)
    return active


def _active_turn(session: Any) -> ActiveTurn:
    return _ensure_active_turn(session)


async def _run_task(task: Any, session_ctx: SessionTaskContext, turn_context: Any, input: list[Any], token: CancellationToken) -> str | None:
    run = getattr(task, "run", None)
    if not callable(run):
        raise TypeError("session task must expose run()")
    params = inspect.signature(run).parameters
    if "runner" in params:
        runner = _field(session_ctx.session, "turn_runner")
        if runner is None:
            raise TypeError("regular task runtime requires session.turn_runner")
        return await _maybe_await(run(session_ctx, turn_context, input, token, runner))
    return await _maybe_await(run(session_ctx, turn_context, input, token))


async def _abort_task_object(task: Any, session_ctx: SessionTaskContext, turn_context: Any) -> None:
    abort = getattr(task, "abort", None)
    if callable(abort):
        await _maybe_await(abort(session_ctx, turn_context))


def _call_task(task: Any, name: str) -> Any:
    method = getattr(task, name, None)
    if not callable(method):
        raise TypeError(f"session task must expose {name}()")
    return method()


async def _mark_turn_started(turn_context: Any) -> None:
    timing = _field(turn_context, "turn_timing_state")
    marker = getattr(timing, "mark_turn_started", None)
    if callable(marker):
        started = await _maybe_await(marker())
        metadata = _field(turn_context, "turn_metadata_state")
        setter = getattr(metadata, "set_turn_started_at_unix_ms", None)
        if callable(setter):
            setter(started)


def _start_turn_timer(turn_context: Any) -> Any:
    telemetry = _field(turn_context, "session_telemetry")
    starter = getattr(telemetry, "start_timer", None)
    if callable(starter):
        return starter("codex.turn.e2e.duration", [])
    return None


async def _completed_at_and_duration_ms(turn_context: Any) -> tuple[int | None, int | None]:
    timing = _field(turn_context, "turn_timing_state")
    getter = getattr(timing, "completed_at_and_duration_ms", None)
    if callable(getter):
        return await _maybe_await(getter())
    return None, None


async def _time_to_first_token_ms(turn_context: Any) -> int | None:
    timing = _field(turn_context, "turn_timing_state")
    getter = getattr(timing, "time_to_first_token_ms", None)
    if callable(getter):
        return await _maybe_await(getter())
    return None


async def _clear_guardian_rejection_turn(session: Any, sub_id: Any) -> None:
    breaker = _field(_field(session, "services"), "guardian_rejection_circuit_breaker")
    clear = getattr(breaker, "clear_turn", None)
    if callable(clear) and sub_id is not None:
        await _maybe_await(clear(str(sub_id)))


async def _emit_lifecycle(session: Any, name: str, *args: Any) -> None:
    method = getattr(session, name, None)
    if callable(method):
        await _maybe_await(method(*args))


async def _send_event(session: Any, ctx: Any, msg: EventMsg) -> None:
    await _call_required(session, "send_event", ctx, msg)


async def _call_required(target: Any, name: str, *args: Any) -> Any:
    method = getattr(target, name, None)
    if not callable(method):
        raise TypeError(f"tasks runtime requires {name}()")
    return await _maybe_await(method(*args))


def _field(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "CompactTask",
    "CompactTaskPlan",
    "GRACEFULL_INTERRUPTION_TIMEOUT_MS",
    "InterruptedTurnHistoryMarker",
    "RegularTask",
    "REVIEW_INTERRUPTED_ASSISTANT_MESSAGE",
    "REVIEW_ROLLOUT_ASSISTANT_MESSAGE_ID",
    "REVIEW_ROLLOUT_USER_MESSAGE_ID",
    "ReviewExitMessages",
    "ReviewTask",
    "SessionStartupPrewarmResolution",
    "SessionTaskContext",
    "TASK_COMPACT_METRIC",
    "TURN_MEMORY_METRIC",
    "TURN_NETWORK_PROXY_METRIC",
    "bool_tag",
    "abort_all_tasks",
    "abort_turn_if_active",
    "collect_review_user_input",
    "exit_review_mode",
    "emit_compact_metric",
    "emit_turn_abort_lifecycle",
    "emit_turn_error_lifecycle",
    "emit_turn_memory_metric",
    "emit_turn_network_proxy_metric",
    "emit_turn_start_lifecycle",
    "emit_turn_stop_lifecycle",
    "interrupted_turn_history_marker",
    "handle_task_abort",
    "maybe_start_turn_for_pending_work",
    "maybe_start_turn_for_pending_work_with_sub_id",
    "normalize_review_template_line_endings",
    "parse_review_output_event",
    "process_review_events",
    "render_review_exit_interrupted",
    "render_review_exit_success",
    "review_exit_messages",
    "on_task_finished",
    "spawn_task",
    "start_task",
    "start_review_conversation",
]
