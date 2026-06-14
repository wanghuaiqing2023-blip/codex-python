"""Session lifecycle helpers for Rust ``codex-tui::app::session_lifecycle``.

Upstream source: ``codex/codex-rs/tui/src/app/session_lifecycle.rs``.
"""

from __future__ import annotations

from typing import Any

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::session_lifecycle",
    source="codex/codex-rs/tui/src/app/session_lifecycle.rs",
)


def _error_chain_messages(error: Any) -> list[str]:
    messages: list[str] = []
    current = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        messages.append(str(current))
        current = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
    if not messages:
        messages.append(str(error))
    return messages


def is_terminal_thread_read_error(error: Any) -> bool:
    return any("thread not loaded:" in message for message in _error_chain_messages(error))


def closed_state_for_thread_read_error(error: Any, existing_is_closed: bool | None) -> bool:
    return is_terminal_thread_read_error(error) or bool(existing_is_closed)


def can_fallback_from_include_turns_error(error: Any) -> bool:
    for message in _error_chain_messages(error):
        if (
            "includeTurns is unavailable before first user message" in message
            or "ephemeral threads do not support includeTurns" in message
        ):
            return True
    return False


async def open_agent_picker(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::session_lifecycle.open_agent_picker UI/app-server flow is not ported")


async def refresh_agent_picker_thread_liveness(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::session_lifecycle.refresh_agent_picker_thread_liveness app-server flow is not ported")


async def attach_live_thread_for_selection(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::session_lifecycle.attach_live_thread_for_selection app-server flow is not ported")


async def select_agent_thread(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::session_lifecycle.select_agent_thread UI/app-server flow is not ported")


async def start_fresh_session_with_summary_hint(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::session_lifecycle.start_fresh_session_with_summary_hint app-server flow is not ported")


async def resume_target_session(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::session_lifecycle.resume_target_session app-server flow is not ported")


__all__ = [
    "RUST_MODULE",
    "attach_live_thread_for_selection",
    "can_fallback_from_include_turns_error",
    "closed_state_for_thread_read_error",
    "is_terminal_thread_read_error",
    "open_agent_picker",
    "refresh_agent_picker_thread_liveness",
    "resume_target_session",
    "select_agent_thread",
    "start_fresh_session_with_summary_hint",
]
