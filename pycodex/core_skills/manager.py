"""Skill manager aligned with ``codex-core-skills::manager``."""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from threading import RLock
from typing import Any

from pycodex.skills import install_system_skills

from .config_rules import resolve_disabled_skill_paths, skill_config_rules_from_stack
from .invocation_utils import SkillLoadOutcome, skill_load_outcome_with_implicit_indexes
from . import loader as _loader
from .system import uninstall_system_skills


@dataclass(frozen=True)
class SkillsLoadInput:
    cwd: Path
    effective_skill_roots: tuple[Any, ...] = ()
    config_layer_stack: Any = None
    bundled_skills_enabled: bool = True

    @classmethod
    def new(
        cls,
        cwd: Path | str,
        effective_skill_roots: tuple[Any, ...] | list[Any],
        config_layer_stack: Any,
        bundled_skills_enabled: bool,
    ) -> "SkillsLoadInput":
        return cls(
            Path(cwd),
            tuple(effective_skill_roots),
            config_layer_stack,
            bool(bundled_skills_enabled),
        )


class SkillsManager:
    def __init__(
        self,
        codex_home: Path | str,
        bundled_skills_enabled: bool = True,
        restriction_product: Any = "codex",
    ) -> None:
        self.codex_home = Path(codex_home)
        self.bundled_skills_enabled = bool(bundled_skills_enabled)
        self.restriction_product = restriction_product
        self._cache: dict[tuple[Any, ...], SkillLoadOutcome] = {}
        self._lock = RLock()
        try:
            if self.bundled_skills_enabled:
                install_system_skills(self.codex_home)
            else:
                uninstall_system_skills(self.codex_home)
        except OSError:
            pass

    @classmethod
    def new(cls, codex_home: Path | str, bundled_skills_enabled: bool = True) -> "SkillsManager":
        return cls(codex_home, bundled_skills_enabled)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    async def skills_for_config(self, input: Any, fs: Any = None) -> SkillLoadOutcome:
        roots = self.skill_roots_for_config(input, fs)
        rules = skill_config_rules_from_stack(getattr(input, "config_layer_stack", None))
        key = (
            tuple((str(root.path), root.scope, root.plugin_id) for root in roots),
            repr(rules),
        )
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached
        outcome = _loader.load_skills_from_roots(roots)
        disabled = resolve_disabled_skill_paths(outcome.skills, rules)
        outcome = skill_load_outcome_with_implicit_indexes(
            SkillLoadOutcome(
                skills=outcome.skills,
                errors=outcome.errors,
                disabled_paths=frozenset(disabled),
                skill_roots=outcome.skill_roots,
                skill_root_by_path=outcome.skill_root_by_path,
            )
        )
        with self._lock:
            self._cache[key] = outcome
        return outcome

    async def skills_for_cwd(self, input: Any, force_reload: bool = False, fs: Any = None) -> SkillLoadOutcome:
        if force_reload:
            self.clear_cache()
        return await self.skills_for_config(input, fs)

    def skill_roots_for_config(self, input: Any, fs: Any = None) -> tuple[_loader.SkillRoot, ...]:
        return _loader.skill_roots(
            self.codex_home,
            input,
            bundled_skills_enabled=self.bundled_skills_enabled,
            fs=fs,
        )


__all__ = ["SkillsLoadInput", "SkillsManager"]
