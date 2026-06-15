"""Collaboration mode presets ported from ``codex-models-manager``."""

from __future__ import annotations

from pycodex.collaboration_mode_templates import DEFAULT as COLLABORATION_MODE_DEFAULT
from pycodex.collaboration_mode_templates import PLAN as COLLABORATION_MODE_PLAN
from pycodex.protocol import (
    CollaborationModeMask,
    ModeKind,
    ReasoningEffort,
    TUI_VISIBLE_COLLABORATION_MODES,
)


KNOWN_MODE_NAMES_TEMPLATE_KEY = "{{KNOWN_MODE_NAMES}}"


def builtin_collaboration_mode_presets() -> list[CollaborationModeMask]:
    return [_plan_preset(), _default_preset()]


def format_mode_names(modes: list[ModeKind] | tuple[ModeKind, ...]) -> str:
    names = [mode.display_name() for mode in modes]
    if not names:
        return "none"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names)


def default_mode_instructions() -> str:
    known_mode_names = format_mode_names(TUI_VISIBLE_COLLABORATION_MODES)
    return COLLABORATION_MODE_DEFAULT.replace(KNOWN_MODE_NAMES_TEMPLATE_KEY, known_mode_names)


def _plan_preset() -> CollaborationModeMask:
    return CollaborationModeMask(
        name=ModeKind.PLAN.display_name(),
        mode=ModeKind.PLAN,
        model=None,
        reasoning_effort=ReasoningEffort.MEDIUM,
        developer_instructions=COLLABORATION_MODE_PLAN,
    )


def _default_preset() -> CollaborationModeMask:
    return CollaborationModeMask(
        name=ModeKind.DEFAULT.display_name(),
        mode=ModeKind.DEFAULT,
        model=None,
        reasoning_effort=None,
        developer_instructions=default_mode_instructions(),
    )


__all__ = [
    "KNOWN_MODE_NAMES_TEMPLATE_KEY",
    "builtin_collaboration_mode_presets",
    "default_mode_instructions",
    "format_mode_names",
]
