"""Regular turn task boundary aligned with ``codex-core::tasks::regular``."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from pycodex.core.state import TaskKind
from pycodex.protocol import EventMsg, TurnStartedEvent


class SessionStartupPrewarmResolution:
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"
    READY = "ready"


@dataclass(frozen=True)
class RegularTask:
    """Python coordinate for Rust ``RegularTask``."""

    @classmethod
    def new(cls) -> "RegularTask":
        return cls()

    def kind(self) -> TaskKind:
        return TaskKind.REGULAR

    def span_name(self) -> str:
        return "session_task.turn"

    async def run(
        self,
        session_context: Any,
        ctx: Any,
        input: list[Any],
        cancellation_token: Any,
        runner: Any,
    ) -> str | None:
        sess = _clone_session(session_context)
        turn_extension_data = _turn_extension_data(session_context)

        await _send_turn_started(sess, ctx)
        await _maybe_await(sess.set_server_reasoning_included(False))

        prewarmed = await _consume_startup_prewarm(sess, cancellation_token)
        if _prewarm_kind(prewarmed) == SessionStartupPrewarmResolution.CANCELLED:
            return None
        prewarmed_client_session = _ready_payload(prewarmed)

        next_input = list(input)
        while True:
            last_agent_message = await _maybe_await(
                runner.run_turn(
                    sess,
                    ctx,
                    turn_extension_data,
                    next_input,
                    prewarmed_client_session,
                    _child_token(cancellation_token),
                )
            )
            prewarmed_client_session = None
            if not await _has_pending_input(sess):
                return last_agent_message
            next_input = []


def _clone_session(session_context: Any) -> Any:
    clone = getattr(session_context, "clone_session", None)
    return clone() if callable(clone) else getattr(session_context, "session", session_context)


def _turn_extension_data(session_context: Any) -> Any:
    getter = getattr(session_context, "turn_extension_data", None)
    return getter() if callable(getter) else getattr(session_context, "turn_extension_data_value", None)


async def _send_turn_started(sess: Any, ctx: Any) -> None:
    event = EventMsg.with_payload(
        "task_started",
        TurnStartedEvent(
            turn_id=str(getattr(ctx, "sub_id")),
            trace_id=getattr(ctx, "trace_id", None),
            started_at=await _started_at(ctx),
            model_context_window=_model_context_window(ctx),
            collaboration_mode_kind=_collaboration_mode_kind(ctx),
        )
    )
    await _maybe_await(sess.send_event(ctx, event))


async def _started_at(ctx: Any) -> int | None:
    timing = getattr(ctx, "turn_timing_state", None)
    getter = getattr(timing, "started_at_unix_secs", None)
    if callable(getter):
        return await _maybe_await(getter())
    return getattr(ctx, "started_at", None)


def _model_context_window(ctx: Any) -> int | None:
    getter = getattr(ctx, "model_context_window", None)
    return getter() if callable(getter) else getattr(ctx, "model_context_window_value", None)


def _collaboration_mode_kind(ctx: Any) -> Any:
    collaboration_mode = getattr(ctx, "collaboration_mode", None)
    return getattr(collaboration_mode, "mode", collaboration_mode)


async def _consume_startup_prewarm(sess: Any, cancellation_token: Any) -> Any:
    consumer = getattr(sess, "consume_startup_prewarm_for_regular_turn", None)
    if not callable(consumer):
        return None
    return await _maybe_await(consumer(cancellation_token))


def _prewarm_kind(value: Any) -> str:
    if value is None:
        return SessionStartupPrewarmResolution.UNAVAILABLE
    if isinstance(value, str):
        return value.lower()
    kind = getattr(value, "kind", None) or getattr(value, "type", None)
    if isinstance(kind, str):
        return kind.lower()
    return SessionStartupPrewarmResolution.READY


def _ready_payload(value: Any) -> Any:
    if _prewarm_kind(value) != SessionStartupPrewarmResolution.READY:
        return None
    return getattr(value, "client_session", getattr(value, "value", value))


async def _has_pending_input(sess: Any) -> bool:
    input_queue = getattr(sess, "input_queue", None)
    checker = getattr(input_queue, "has_pending_input", None)
    if not callable(checker):
        return False
    return bool(await _maybe_await(checker(getattr(sess, "active_turn", None))))


def _child_token(cancellation_token: Any) -> Any:
    child = getattr(cancellation_token, "child_token", None)
    return child() if callable(child) else cancellation_token


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = ["RegularTask", "SessionStartupPrewarmResolution"]
