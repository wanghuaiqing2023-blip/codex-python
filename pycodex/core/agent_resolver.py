"""Agent target resolution ported from ``core/src/agent/agent_resolver.rs``."""

from __future__ import annotations

import inspect
from typing import Any

from pycodex.core.function_tool import FunctionCallError
from pycodex.protocol import SessionSource, ThreadId


async def resolve_agent_target(session: Any, turn: Any, target: str) -> ThreadId:
    """Resolve one tool-facing agent target to a thread id."""

    if not isinstance(target, str):
        raise TypeError("target must be a string")
    register_session_root(session, turn)
    try:
        return ThreadId.from_string(target)
    except Exception:
        pass

    agent_control = _agent_control(session)
    resolver = getattr(agent_control, "resolve_agent_reference", None)
    if not callable(resolver):
        raise FunctionCallError.respond_to_model("agent control is not available")

    try:
        return await _maybe_await(
            resolver(
                getattr(session, "conversation_id", None),
                getattr(turn, "session_source", SessionSource.default()),
                target,
            )
        )
    except Exception as exc:
        raise FunctionCallError.respond_to_model(str(exc)) from exc


def register_session_root(session: Any, turn: Any) -> None:
    """Register the current session root with AgentControl before resolution."""

    agent_control = _agent_control(session)
    register = getattr(agent_control, "register_session_root", None)
    if callable(register):
        register(
            getattr(session, "conversation_id", None),
            getattr(turn, "session_source", SessionSource.default()),
        )


def _agent_control(session: Any) -> Any:
    return getattr(getattr(session, "services", None), "agent_control", None)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "FunctionCallError",
    "register_session_root",
    "resolve_agent_target",
]
