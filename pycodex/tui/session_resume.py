"""Saved-session resolution helpers for TUI resume/fork flows.

Rust counterpart: ``codex-rs/tui/src/session_resume.rs``.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


@dataclass
class RolloutResumeState:
    thread_id: str | None = None
    cwd: Path | None = None
    model: str | None = None


@dataclass(frozen=True)
class SessionMetadata:
    id: str
    cwd: Path


@dataclass(frozen=True)
class TurnContextResumeState:
    cwd: Path
    model: str


@dataclass(frozen=True)
class RawRecord:
    item_type: str
    payload: Mapping[str, Any] | None = None


class ResolveCwdOutcomeKind(str, Enum):
    CONTINUE = "continue"
    EXIT = "exit"


@dataclass(frozen=True)
class ResolveCwdOutcome:
    kind: ResolveCwdOutcomeKind
    cwd: Path | None = None

    @classmethod
    def Continue(cls, cwd: str | Path | None = None) -> "ResolveCwdOutcome":
        return cls(ResolveCwdOutcomeKind.CONTINUE, Path(cwd) if cwd is not None else None)

    @classmethod
    def Exit(cls) -> "ResolveCwdOutcome":
        return cls(ResolveCwdOutcomeKind.EXIT, None)


async def resolve_session_thread_id(path: str | Path, id_str_if_uuid: str | None = None) -> str | None:
    if id_str_if_uuid is not None:
        try:
            return str(uuid.UUID(str(id_str_if_uuid)))
        except ValueError:
            return None
    try:
        return (await read_rollout_resume_state(path)).thread_id
    except OSError:
        return None


async def read_session_model(
    state_db_ctx: Any | None,
    thread_id: str,
    path: str | Path | None,
) -> str | None:
    metadata = await _get_thread_metadata(state_db_ctx, thread_id)
    model = _get_field(metadata, "model") if metadata is not None else None
    if model is not None:
        return str(model)
    if path is None:
        return None
    try:
        return (await read_rollout_resume_state(path)).model
    except OSError:
        return None


async def resolve_cwd_for_resume_or_fork(
    tui: Any,
    state_db_ctx: Any | None,
    current_cwd: str | Path,
    thread_id: str,
    path: str | Path | None,
    action: Any,
    allow_prompt: bool,
) -> ResolveCwdOutcome:
    history_cwd = await read_session_cwd(state_db_ctx, thread_id, path)
    if history_cwd is None:
        return ResolveCwdOutcome.Continue(None)
    current_path = Path(current_cwd)
    if allow_prompt and cwds_differ(current_path, history_cwd):
        prompt = getattr(tui, "run_cwd_selection_prompt", None)
        if prompt is None:
            raise NotImplementedError("cwd selection prompt is required when cwd differs and prompting is allowed")
        selection = await _maybe_await(prompt(action, current_path, history_cwd))
        if selection == "current":
            return ResolveCwdOutcome.Continue(current_path)
        if selection == "session":
            return ResolveCwdOutcome.Continue(history_cwd)
        if selection == "exit":
            return ResolveCwdOutcome.Exit()
        raise ValueError(f"unknown cwd prompt outcome: {selection!r}")
    return ResolveCwdOutcome.Continue(history_cwd)


async def read_session_cwd(
    state_db_ctx: Any | None,
    thread_id: str,
    path: str | Path | None,
) -> Path | None:
    metadata = await _get_thread_metadata(state_db_ctx, thread_id)
    cwd = _get_field(metadata, "cwd") if metadata is not None else None
    if cwd is not None:
        return Path(cwd)
    if path is None:
        return None
    try:
        return (await read_rollout_resume_state(path)).cwd
    except OSError:
        return None


def cwds_differ(current_cwd: str | Path, session_cwd: str | Path) -> bool:
    return _normalized_path(current_cwd) != _normalized_path(session_cwd)


async def read_rollout_resume_state(path: str | Path) -> RolloutResumeState:
    rollout_path = Path(path)
    state = RolloutResumeState()
    saw_record = False
    with rollout_path.open("r", encoding="utf-8") as file:
        for line in file:
            trimmed = line.strip()
            if not trimmed:
                continue
            try:
                raw = json.loads(trimmed)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, Mapping):
                continue
            item_type = raw.get("type")
            payload = raw.get("payload")
            saw_record = True
            if not isinstance(item_type, str) or not isinstance(payload, Mapping):
                continue
            if item_type == "session_meta" and state.thread_id is None:
                thread_id = payload.get("id")
                cwd = payload.get("cwd")
                if isinstance(thread_id, str) and cwd is not None:
                    state.thread_id = thread_id
                    if state.cwd is None:
                        state.cwd = Path(cwd)
            elif item_type == "turn_context":
                cwd = payload.get("cwd")
                model = payload.get("model")
                if cwd is not None and isinstance(model, str):
                    state.cwd = Path(cwd)
                    state.model = model
    if not saw_record:
        raise OSError(f"rollout at {rollout_path} is empty")
    return state


def rollout_line(timestamp: str, item_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"timestamp": timestamp, "type": item_type, "payload": dict(payload)}


def write_rollout_lines(path: str | Path, lines: list[Mapping[str, Any]]) -> None:
    text = "".join(json.dumps(line, default=str) + "\n" for line in lines)
    Path(path).write_text(text, encoding="utf-8")


async def _get_thread_metadata(state_db_ctx: Any | None, thread_id: str) -> Any | None:
    if state_db_ctx is None:
        return None
    getter = getattr(state_db_ctx, "get_thread", None)
    if getter is None:
        return None
    try:
        return await _maybe_await(getter(thread_id))
    except Exception:
        return None


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


def _get_field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _normalized_path(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(os.path.normpath(str(path))))


__all__ = [
    "RawRecord",
    "ResolveCwdOutcome",
    "ResolveCwdOutcomeKind",
    "RolloutResumeState",
    "SessionMetadata",
    "TurnContextResumeState",
    "cwds_differ",
    "read_rollout_resume_state",
    "read_session_cwd",
    "read_session_model",
    "resolve_cwd_for_resume_or_fork",
    "resolve_session_thread_id",
    "rollout_line",
    "write_rollout_lines",
]
