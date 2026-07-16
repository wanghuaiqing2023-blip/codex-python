"""Skill manager aligned with ``codex-core-skills::manager``."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from threading import RLock
from typing import Any

from pycodex.skills import install_system_skills, uninstall_system_skills
from pycodex.utils.plugins import plugin_namespace_for_skill_path

from .config_rules import resolve_disabled_skill_paths, skill_config_rules_from_stack
from .invocation_utils import SkillLoadOutcome, skill_load_outcome_with_implicit_indexes
from .model import SkillError, SkillMetadata


_MAX_SCAN_DEPTH = 6
_MAX_SKILLS_DIRS_PER_ROOT = 2_000
_PROJECT_ROOT_MARKERS = (".git", ".jj", ".hg", ".svn")


@dataclass(frozen=True)
class SkillRoot:
    path: Path
    scope: str
    plugin_id: str | None = None
    plugin_root: Path | None = None


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
            # Rust logs installation failures and still constructs the manager.
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

        outcome = _load_skills_from_roots(roots)
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

    def skill_roots_for_config(self, input: Any, fs: Any = None) -> tuple[SkillRoot, ...]:
        cwd = Path(getattr(input, "cwd"))
        roots = list(
            _roots_from_config_layer_stack(
                getattr(input, "config_layer_stack", None),
                include_project=fs is not None,
            )
        )
        if not any(root.scope == "user" for root in roots):
            # Rust keeps this deprecated user root for backwards compatibility.
            roots.append(SkillRoot(self.codex_home / "skills", "user"))
            roots.append(SkillRoot(Path.home() / ".agents" / "skills", "user"))
        bundled_enabled = self.bundled_skills_enabled and bool(
            getattr(input, "bundled_skills_enabled", True)
        )
        if bundled_enabled and not any(root.scope == "system" for root in roots):
            roots.append(SkillRoot(self.codex_home / "skills" / ".system", "system"))
        if not bundled_enabled:
            roots = [root for root in roots if root.scope != "system"]

        for value in tuple(getattr(input, "effective_skill_roots", ()) or ()):
            root = _coerce_plugin_skill_root(value)
            if root is not None:
                roots.append(root)

        if fs is not None:
            project_root = _find_project_root(cwd)
            for directory in _dirs_between(project_root, cwd):
                roots.append(SkillRoot(directory / ".agents" / "skills", "repo"))
        return _dedupe_roots(roots)


def _load_skills_from_roots(roots: tuple[SkillRoot, ...]) -> SkillLoadOutcome:
    skills: list[SkillMetadata] = []
    errors: list[SkillError] = []
    root_by_path: dict[Path, Path] = {}
    used_roots: list[Path] = []
    seen_paths: set[Path] = set()
    for root in roots:
        if not root.path.is_dir():
            continue
        canonical_root = _canonical(root.path)
        root_used = False
        for path in _discover_skill_files(canonical_root, follow_symlinks=root.scope != "system"):
            canonical_path = _canonical(path)
            if canonical_path in seen_paths:
                continue
            try:
                skill = _parse_skill_file(canonical_path, root)
            except (OSError, ValueError) as exc:
                if root.scope != "system":
                    errors.append(SkillError(canonical_path, str(exc)))
                continue
            seen_paths.add(canonical_path)
            skills.append(skill)
            root_by_path[canonical_path] = canonical_root
            root_used = True
        if root_used:
            used_roots.append(canonical_root)
    return SkillLoadOutcome(
        skills=tuple(skills),
        errors=tuple(errors),
        skill_roots=tuple(used_roots),
        skill_root_by_path=root_by_path,
    )


def _discover_skill_files(root: Path, *, follow_symlinks: bool) -> tuple[Path, ...]:
    queue = deque([(root, 0)])
    visited = {_canonical(root)}
    found: list[Path] = []
    while queue and len(visited) <= _MAX_SKILLS_DIRS_PER_ROOT:
        directory, depth = queue.popleft()
        try:
            entries = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError:
            continue
        for path in entries:
            if path.name.startswith("."):
                continue
            try:
                is_symlink = path.is_symlink()
                is_directory = path.is_dir()
            except OSError:
                continue
            if is_directory:
                if is_symlink and not follow_symlinks:
                    continue
                if depth >= _MAX_SCAN_DEPTH:
                    continue
                resolved = _canonical(path)
                if resolved not in visited:
                    visited.add(resolved)
                    queue.append((resolved, depth + 1))
                continue
            if path.name == "SKILL.md" and path.is_file():
                found.append(path)
    return tuple(found)


def _parse_skill_file(path: Path, root: SkillRoot) -> SkillMetadata:
    text = path.read_text(encoding="utf-8")
    frontmatter = _frontmatter(text)
    name = _sanitize_single_line(_frontmatter_value(frontmatter, "name") or path.parent.name)
    description = _sanitize_single_line(_frontmatter_value(frontmatter, "description") or "")
    short_description = _frontmatter_value(frontmatter, "short-description")
    if short_description is not None:
        short_description = _sanitize_single_line(short_description) or None
    namespace = plugin_namespace_for_skill_path(path)
    if namespace:
        name = f"{namespace}:{name}"
    if len(name) > 64:
        raise ValueError("invalid name: exceeds 64 characters")
    if len(description) > 1024:
        raise ValueError("invalid description: exceeds 1024 characters")
    policy = _load_skill_policy(path)
    return SkillMetadata(
        name=name,
        description=description,
        short_description=short_description,
        policy=policy,
        path_to_skills_md=path,
        scope=root.scope,
        plugin_id=root.plugin_id,
    )


def _frontmatter(text: str) -> tuple[str, ...]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing YAML frontmatter delimited by ---")
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return tuple(lines[1:index])
    raise ValueError("missing YAML frontmatter delimited by ---")


def _frontmatter_value(lines: tuple[str, ...], key: str) -> str | None:
    candidates = (key, f"metadata.{key}")
    in_metadata = False
    for line in lines:
        stripped = line.strip()
        if stripped == "metadata:":
            in_metadata = True
            continue
        if line and not line[0].isspace():
            in_metadata = False
        for candidate in candidates:
            lookup = candidate.removeprefix("metadata.")
            if candidate.startswith("metadata.") and not in_metadata:
                continue
            prefix = f"{lookup}:"
            if stripped.startswith(prefix):
                return _yaml_scalar(stripped[len(prefix):].strip())
    return None


def _yaml_scalar(value: str) -> str:
    if value == "":
        return ""
    if value[0:1] in {'"', "'"}:
        try:
            return str(json.loads(value)) if value.startswith('"') else value[1:-1].replace("''", "'")
        except (json.JSONDecodeError, IndexError):
            return value.strip('"\'')
    return value.split(" #", 1)[0].strip()


def _load_skill_policy(skill_path: Path) -> Mapping[str, Any] | None:
    metadata = skill_path.parent / "agents" / "openai.yaml"
    if not metadata.is_file():
        return None
    try:
        value = _simple_yaml_mapping(metadata.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value.get("policy") if isinstance(value, Mapping) else None


def _roots_from_config_layer_stack(
    stack: Any,
    *,
    include_project: bool,
) -> tuple[SkillRoot, ...]:
    if stack is None:
        return ()
    get_layers = getattr(stack, "get_layers", None)
    if not callable(get_layers):
        return ()
    try:
        from pycodex.config import ConfigLayerStackOrdering

        layers = get_layers(ConfigLayerStackOrdering.HIGHEST_PRECEDENCE_FIRST, True)
    except (ImportError, TypeError, ValueError):
        try:
            layers = get_layers("highest_precedence_first", True)
        except (TypeError, ValueError):
            return ()

    roots: list[SkillRoot] = []
    for layer in layers:
        source = getattr(layer, "name", None)
        source_type = str(getattr(source, "type", source)).replace("-", "_").lower()
        folder_value = getattr(layer, "config_folder", None)
        folder_value = folder_value() if callable(folder_value) else folder_value
        if folder_value is None:
            continue
        folder = Path(folder_value)
        if source_type == "project" and include_project:
            roots.append(SkillRoot(folder / "skills", "repo"))
        elif source_type == "user":
            roots.extend(
                (
                    SkillRoot(folder / "skills", "user"),
                    SkillRoot(Path.home() / ".agents" / "skills", "user"),
                    SkillRoot(folder / "skills" / ".system", "system"),
                )
            )
        elif source_type == "system":
            roots.append(SkillRoot(folder / "skills", "admin"))
    return tuple(roots)


def _sanitize_single_line(value: str) -> str:
    return " ".join(str(value).split())


def _simple_yaml_mapping(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip().replace("-", "_")
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        target = stack[-1][1]
        raw_value = raw_value.strip()
        if not raw_value:
            child: dict[str, Any] = {}
            target[key] = child
            stack.append((indent, child))
            continue
        scalar = _yaml_scalar(raw_value)
        if scalar.lower() in {"true", "false"}:
            target[key] = scalar.lower() == "true"
        elif scalar.startswith("[") and scalar.endswith("]"):
            target[key] = tuple(
                part.strip().strip("\"'")
                for part in scalar[1:-1].split(",")
                if part.strip()
            )
        else:
            target[key] = scalar
    return root


def _coerce_plugin_skill_root(value: Any) -> SkillRoot | None:
    if isinstance(value, (str, Path)):
        return SkillRoot(Path(value), "user")
    path = getattr(value, "path", None)
    if path is None and isinstance(value, Mapping):
        path = value.get("path")
    if path is None:
        return None
    field = value.get if isinstance(value, Mapping) else lambda name, default=None: getattr(value, name, default)
    return SkillRoot(
        Path(path),
        str(field("scope", "user")),
        field("plugin_id", None),
        Path(field("plugin_root")) if field("plugin_root", None) is not None else None,
    )


def _find_project_root(cwd: Path) -> Path:
    for directory in (cwd, *cwd.parents):
        if any((directory / marker).exists() for marker in _PROJECT_ROOT_MARKERS):
            return directory
    return cwd


def _dirs_between(root: Path, cwd: Path) -> tuple[Path, ...]:
    directories: list[Path] = []
    for directory in (cwd, *cwd.parents):
        directories.append(directory)
        if directory == root:
            break
    return tuple(reversed(directories))


def _canonical(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def _dedupe_roots(roots: list[SkillRoot]) -> tuple[SkillRoot, ...]:
    seen: set[Path] = set()
    result: list[SkillRoot] = []
    for root in roots:
        path = _canonical(root.path)
        if path in seen:
            continue
        seen.add(path)
        result.append(SkillRoot(path, root.scope, root.plugin_id, root.plugin_root))
    return tuple(result)


__all__ = ["SkillRoot", "SkillsManager"]
