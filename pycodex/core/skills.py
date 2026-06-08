"""Facade for skill loading/rendering/invocation helpers.

Ported from ``codex/codex-rs/core/src/skills.rs``. The Rust module mainly
re-exports the ``codex_core_skills`` crate and adds two core helpers. This
Python version mirrors that facade over the already-ported ``skill_*`` modules
and keeps analytics emission as an injectable/session boundary.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex import core_skills
from pycodex.core_skills import config_rules, remote
from pycodex.core_skills import injections as injection
from pycodex.core_skills import invocation_utils
from pycodex.core_skills import mentions as mention_counts
from pycodex.core_skills import model
from pycodex.core_skills import rendering as render
from pycodex.core_skills.model import SkillError, SkillMetadata
from pycodex.core_skills.config_rules import SkillConfigRules
from pycodex.core_skills.injections import SkillInjections, build_skill_injections
from pycodex.core_skills.invocation_utils import (
    SkillLoadOutcome,
    SkillPolicy,
    detect_implicit_skill_invocation_for_command,
    filter_skill_load_outcome_for_product,
)
from pycodex.core_skills.mentions import build_skill_name_counts, collect_explicit_skill_mentions
from pycodex.core_skills.rendering import (
    SKILLS_HOW_TO_USE_WITH_ABSOLUTE_PATHS,
    SKILLS_HOW_TO_USE_WITH_ALIASES,
    SKILLS_INTRO_WITH_ABSOLUTE_PATHS,
    SKILLS_INTRO_WITH_ALIASES,
    SkillRenderSideEffects,
    SkillRenderReport,
    build_available_skills,
    default_skill_metadata_budget,
    render_available_skills_body,
)


@dataclass(frozen=True)
class SkillsLoadInput:
    cwd: Path
    effective_skill_roots: tuple[Any, ...]
    config_layer_stack: Any
    bundled_skills_enabled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if isinstance(self.effective_skill_roots, (str, bytes)) or not isinstance(self.effective_skill_roots, tuple):
            object.__setattr__(self, "effective_skill_roots", tuple(self.effective_skill_roots))
        if not isinstance(self.bundled_skills_enabled, bool):
            raise TypeError("bundled_skills_enabled must be a bool")


@dataclass(frozen=True)
class SkillInvocation:
    skill_name: str
    skill_scope: str
    skill_path: Path
    plugin_id: str | None
    invocation_type: str = "implicit"


def skills_load_input_from_config(
    config: Any,
    effective_skill_roots: Iterable[Any],
) -> SkillsLoadInput:
    roots = tuple(effective_skill_roots)
    cwd = getattr(config, "cwd", None)
    if cwd is None and isinstance(config, dict):
        cwd = config.get("cwd")
    if cwd is None:
        raise TypeError("config must provide cwd")

    config_layer_stack = getattr(config, "config_layer_stack", None)
    if config_layer_stack is None and isinstance(config, dict):
        config_layer_stack = config.get("config_layer_stack")

    bundled = _bundled_skills_enabled(config)
    return SkillsLoadInput(
        cwd=Path(cwd),
        effective_skill_roots=roots,
        config_layer_stack=config_layer_stack,
        bundled_skills_enabled=bundled,
    )


async def maybe_emit_implicit_skill_invocation(
    sess: Any,
    turn_context: Any,
    command: str,
    workdir: str | Path,
) -> SkillInvocation | None:
    outcome = getattr(getattr(turn_context, "turn_skills", None), "outcome", None)
    if outcome is None:
        return None
    candidate = detect_implicit_skill_invocation_for_command(outcome, command, Path(workdir))
    if candidate is None:
        return None

    skill_path = _skill_path(candidate)
    if skill_path is None:
        return None
    scope = _skill_scope(candidate)
    invocation = SkillInvocation(
        skill_name=candidate.name,
        skill_scope=scope,
        skill_path=skill_path,
        plugin_id=candidate.plugin_id,
        invocation_type="implicit",
    )
    seen_key = f"{scope}:{skill_path}:{candidate.name}"
    if not await _insert_seen_skill(turn_context, seen_key):
        return None

    telemetry = getattr(turn_context, "session_telemetry", None)
    counter = getattr(telemetry, "counter", None)
    if callable(counter):
        counter(
            "codex.skill.injected",
            1,
            (("status", "ok"), ("skill", candidate.name), ("invoke_type", "implicit")),
        )

    analytics = getattr(getattr(sess, "services", None), "analytics_events_client", None)
    tracker = getattr(analytics, "track_skill_invocations", None)
    if callable(tracker):
        tracker(_track_events_context(sess, turn_context), (invocation,))
    return invocation


def _bundled_skills_enabled(config: Any) -> bool:
    method = getattr(config, "bundled_skills_enabled", None)
    if callable(method):
        value = method()
    elif isinstance(config, dict) and "bundled_skills_enabled" in config:
        value = config["bundled_skills_enabled"]
    else:
        value = True
    if not isinstance(value, bool):
        raise TypeError("bundled_skills_enabled must be a bool")
    return value


async def _insert_seen_skill(turn_context: Any, seen_key: str) -> bool:
    turn_skills = getattr(turn_context, "turn_skills", None)
    seen = getattr(turn_skills, "implicit_invocation_seen_skills", None)
    if seen is None:
        seen = set()
        if turn_skills is not None:
            setattr(turn_skills, "implicit_invocation_seen_skills", seen)
    lock = getattr(seen, "lock", None)
    if callable(lock):
        async with lock():
            return _set_insert(seen, seen_key)
    return _set_insert(seen, seen_key)


def _set_insert(seen: Any, seen_key: str) -> bool:
    if not isinstance(seen, set):
        inner = getattr(seen, "value", None)
        if isinstance(inner, set):
            seen = inner
        else:
            raise TypeError("implicit_invocation_seen_skills must be a set-like value")
    if seen_key in seen:
        return False
    seen.add(seen_key)
    return True


def _skill_scope(skill: SkillMetadata) -> str:
    scope = getattr(skill, "scope", "user")
    value = getattr(scope, "value", scope)
    if not isinstance(value, str):
        value = str(value)
    return value.lower()


def _skill_path(skill: SkillMetadata) -> Path | None:
    path = getattr(skill, "path_to_skills_md", None)
    return Path(path) if path is not None else None


def _track_events_context(sess: Any, turn_context: Any) -> dict[str, str]:
    model_info = getattr(turn_context, "model_info", None)
    return {
        "model": str(getattr(model_info, "slug", "")),
        "conversation_id": str(getattr(sess, "conversation_id", "")),
        "sub_id": str(getattr(turn_context, "sub_id", "")),
    }


__all__ = [
    "SkillConfigRules",
    "SkillError",
    "SkillInjections",
    "SkillInvocation",
    "SkillLoadOutcome",
    "SkillMetadata",
    "SkillPolicy",
    "SkillRenderReport",
    "SkillRenderSideEffects",
    "SkillsLoadInput",
    "SKILLS_HOW_TO_USE_WITH_ABSOLUTE_PATHS",
    "SKILLS_HOW_TO_USE_WITH_ALIASES",
    "SKILLS_INTRO_WITH_ABSOLUTE_PATHS",
    "SKILLS_INTRO_WITH_ALIASES",
    "build_available_skills",
    "build_skill_injections",
    "build_skill_name_counts",
    "collect_explicit_skill_mentions",
    "default_skill_metadata_budget",
    "detect_implicit_skill_invocation_for_command",
    "filter_skill_load_outcome_for_product",
    "config_rules",
    "core_skills",
    "injection",
    "invocation_utils",
    "mention_counts",
    "maybe_emit_implicit_skill_invocation",
    "model",
    "remote",
    "render",
    "render_available_skills_body",
    "skills_load_input_from_config",
]
