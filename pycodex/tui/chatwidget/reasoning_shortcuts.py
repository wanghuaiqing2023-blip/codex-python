"""Reasoning-effort shortcut helpers for ``codex-tui::chatwidget::reasoning_shortcuts``.

The Rust module owns the narrow state machine behind Alt+, / Alt+. reasoning
shortcuts.  Python ports the complete pure helper behavior and exposes a small
semantic shortcut handler result for callers; concrete crossterm key handling
and ChatWidget mutation remain runtime integration boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from pycodex.protocol.config_types import ReasoningEffort
from pycodex.protocol.openai_models import ModelPreset, ReasoningEffortPreset

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::reasoning_shortcuts",
    source="codex/codex-rs/tui/src/chatwidget/reasoning_shortcuts.rs",
)


class ReasoningShortcutDirection(Enum):
    Lower = "lower"
    Raise = "raise"

    def bound_message(self, effort: ReasoningEffort | str | Any) -> str:
        label = reasoning_effort_label(_coerce_effort(effort)).lower()
        if self is ReasoningShortcutDirection.Lower:
            return f"Reasoning is already at the lowest level ({label})."
        return f"Reasoning is already at the highest level ({label})."


@dataclass(frozen=True)
class ReasoningShortcutResult:
    handled: bool
    next_effort: ReasoningEffort | None = None
    info_message: str | None = None
    plan_mode_update: bool = False


def reasoning_choices(preset: ModelPreset | Any) -> list[ReasoningEffort]:
    supported = [_coerce_supported_effort(option) for option in _get(preset, "supported_reasoning_efforts", ())]
    choices = [effort for effort in _EFFORT_ORDER if effort in supported]
    if not choices:
        choices.append(_coerce_effort(_get(preset, "default_reasoning_effort")))
    return choices


def next_reasoning_effort(
    choices: Iterable[ReasoningEffort | str | Any],
    current_effort: ReasoningEffort | str | Any | None,
    direction: ReasoningShortcutDirection | str | Any,
) -> ReasoningEffort | None:
    if current_effort is None:
        return None
    normalized_choices = [_coerce_effort(choice) for choice in choices]
    if not normalized_choices:
        return None
    current_rank = effort_rank(current_effort)
    normalized_direction = _coerce_direction(direction)
    if normalized_direction is ReasoningShortcutDirection.Lower:
        for choice in reversed(normalized_choices):
            if effort_rank(choice) < current_rank:
                return choice
        return None
    for choice in normalized_choices:
        if effort_rank(choice) > current_rank:
            return choice
    return None


def effort_rank(effort: ReasoningEffort | str | Any) -> int:
    return _EFFORT_RANK[_coerce_effort(effort)]


def reasoning_effort_label(effort: ReasoningEffort | str | Any) -> str:
    return {
        ReasoningEffort.NONE: "None",
        ReasoningEffort.MINIMAL: "Minimal",
        ReasoningEffort.LOW: "Low",
        ReasoningEffort.MEDIUM: "Medium",
        ReasoningEffort.HIGH: "High",
        ReasoningEffort.XHIGH: "XHigh",
    }[_coerce_effort(effort)]


def handle_reasoning_shortcut_semantic(
    *,
    recognized: bool,
    modal_or_popup_active: bool,
    session_configured: bool,
    current_model: str,
    preset: ModelPreset | Any | None,
    effective_effort: ReasoningEffort | str | Any | None,
    direction: ReasoningShortcutDirection | str | Any,
    plan_mode_active: bool = False,
) -> ReasoningShortcutResult:
    if not recognized:
        return ReasoningShortcutResult(handled=False)
    if modal_or_popup_active:
        return ReasoningShortcutResult(handled=False)
    if not session_configured:
        return ReasoningShortcutResult(
            handled=True,
            info_message="Reasoning shortcuts are disabled until startup completes.",
        )
    if preset is None:
        return ReasoningShortcutResult(
            handled=True,
            info_message=f"Reasoning shortcuts are unavailable for {current_model}.",
        )
    choices = reasoning_choices(preset)
    current = _coerce_effort(effective_effort) if effective_effort is not None else _coerce_effort(_get(preset, "default_reasoning_effort"))
    normalized_direction = _coerce_direction(direction)
    next_effort = next_reasoning_effort(choices, current, normalized_direction)
    if next_effort is None:
        return ReasoningShortcutResult(handled=True, info_message=normalized_direction.bound_message(current))
    return ReasoningShortcutResult(handled=True, next_effort=next_effort, plan_mode_update=plan_mode_active)


_EFFORT_ORDER = [
    ReasoningEffort.NONE,
    ReasoningEffort.MINIMAL,
    ReasoningEffort.LOW,
    ReasoningEffort.MEDIUM,
    ReasoningEffort.HIGH,
    ReasoningEffort.XHIGH,
]
_EFFORT_RANK = {effort: index for index, effort in enumerate(_EFFORT_ORDER)}


def _coerce_direction(value: ReasoningShortcutDirection | str | Any) -> ReasoningShortcutDirection:
    if isinstance(value, ReasoningShortcutDirection):
        return value
    text = str(getattr(value, "value", value))
    lowered = text.lower()
    if lowered in {"lower", "decrease", "down"}:
        return ReasoningShortcutDirection.Lower
    if lowered in {"raise", "increase", "up"}:
        return ReasoningShortcutDirection.Raise
    raise ValueError(f"unknown ReasoningShortcutDirection: {value!r}")


def _coerce_effort(value: ReasoningEffort | str | Any) -> ReasoningEffort:
    if isinstance(value, ReasoningEffort):
        return value
    raw = getattr(value, "value", value)
    return ReasoningEffort(str(raw))


def _coerce_supported_effort(option: ReasoningEffortPreset | ReasoningEffort | str | Any) -> ReasoningEffort:
    effort = _get(option, "effort", None)
    if effort is None:
        effort = _get(option, "reasoning_effort", option)
    return _coerce_effort(effort)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


__all__ = [
    "ReasoningShortcutDirection",
    "ReasoningShortcutResult",
    "RUST_MODULE",
    "effort_rank",
    "handle_reasoning_shortcut_semantic",
    "next_reasoning_effort",
    "reasoning_choices",
    "reasoning_effort_label",
]
