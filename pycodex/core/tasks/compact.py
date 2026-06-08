"""Compact task boundary aligned with ``codex-core::tasks::compact``."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from pycodex.core.compact import should_use_remote_compact_task
from pycodex.core.state import TaskKind
from pycodex.features import Feature
from pycodex.protocol.user_input import UserInput


@dataclass(frozen=True)
class CompactTaskPlan:
    strategy: str
    metric_kind: str
    manual: bool
    input: tuple[UserInput, ...] = ()

    def __post_init__(self) -> None:
        if self.strategy not in {"local", "remote", "remote_v2"}:
            raise ValueError("strategy must be local, remote, or remote_v2")
        if self.metric_kind != self.strategy:
            raise ValueError("metric_kind must match strategy")
        if not isinstance(self.manual, bool):
            raise TypeError("manual must be a bool")
        object.__setattr__(self, "input", tuple(self.input))
        if not all(isinstance(item, UserInput) for item in self.input):
            raise TypeError("input must contain UserInput values")


@dataclass(frozen=True)
class CompactTask:
    """Python coordinate for Rust ``CompactTask``.

    This module captures the selected task's own contract: task identity,
    span naming, compaction strategy selection, metric label, and local prompt
    input construction. The actual compact/remote runtime remains owned by the
    compact modules and session runtime.
    """

    def kind(self) -> TaskKind:
        return TaskKind.COMPACT

    def span_name(self) -> str:
        return "session_task.compact"

    def plan(self, ctx: Any) -> CompactTaskPlan:
        provider = _provider_info(ctx)
        if should_use_remote_compact_task(provider):
            if _feature_enabled(ctx, Feature.REMOTE_COMPACTION_V2):
                return CompactTaskPlan(strategy="remote_v2", metric_kind="remote_v2", manual=True)
            return CompactTaskPlan(strategy="remote", metric_kind="remote", manual=True)

        prompt = _compact_prompt(ctx)
        return CompactTaskPlan(
            strategy="local",
            metric_kind="local",
            manual=True,
            input=(UserInput.text_input(prompt),),
        )

    async def run(self, session: Any, ctx: Any, runner: Any) -> None:
        plan = self.plan(ctx)
        _emit_compact_metric(session, plan.metric_kind, plan.manual)
        if plan.strategy == "remote_v2":
            await _maybe_await(_call_runner(runner, "run_remote_v2", session, ctx))
        elif plan.strategy == "remote":
            await _maybe_await(_call_runner(runner, "run_remote", session, ctx))
        else:
            await _maybe_await(_call_runner(runner, "run_local", session, ctx, plan.input))
        return None


def _provider_info(ctx: Any) -> Any:
    provider = getattr(ctx, "provider", None)
    if provider is None:
        raise TypeError("ctx must expose provider")
    info = getattr(provider, "info", None)
    return info() if callable(info) else info if info is not None else provider


def _feature_enabled(ctx: Any, feature: Feature | str) -> bool:
    features = getattr(ctx, "features", None)
    enabled = getattr(features, "enabled", None)
    if callable(enabled):
        try:
            return bool(enabled(feature))
        except (TypeError, ValueError, AttributeError):
            return bool(enabled(getattr(feature, "value", feature)))
    if isinstance(features, dict):
        return bool(features.get(feature) or features.get(getattr(feature, "value", feature)))
    return bool(getattr(features, getattr(feature, "name", str(feature)), False))


def _compact_prompt(ctx: Any) -> str:
    prompt = getattr(ctx, "compact_prompt", None)
    value = prompt() if callable(prompt) else prompt
    if not isinstance(value, str):
        raise TypeError("ctx.compact_prompt must be a string or callable returning a string")
    return value


def _emit_compact_metric(session: Any, metric_kind: str, manual: bool) -> None:
    emitter = getattr(session, "emit_compact_metric", None)
    if callable(emitter):
        emitter(metric_kind, manual)
        return
    telemetry = getattr(getattr(session, "services", None), "session_telemetry", None)
    counter = getattr(telemetry, "counter", None)
    if callable(counter):
        counter("codex.task.compact", 1, [("type", metric_kind), ("manual", str(manual).lower())])


def _call_runner(runner: Any, name: str, *args: Any) -> Any:
    method = getattr(runner, name, None)
    if not callable(method):
        raise TypeError(f"runner must expose {name}()")
    return method(*args)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = ["CompactTask", "CompactTaskPlan"]
