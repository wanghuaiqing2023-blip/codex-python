"""Personality migration helpers ported from ``core/src/personality_migration.rs``."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from pycodex import _toml
from pycodex.protocol import Personality

from .rollout import (
    ARCHIVED_SESSIONS_SUBDIR,
    SESSIONS_SUBDIR,
    ThreadListLayout,
    get_threads_in_root,
)


PERSONALITY_MIGRATION_FILENAME = ".personality_migration"


def _ensure_pathlike(value: object, field: str) -> str | Path:
    if isinstance(value, (str, Path)):
        return value
    raise TypeError(f"{field} must be path-like")


def _ensure_mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a mapping")
    return value


def _ensure_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


class PersonalityMigrationStatus(str, Enum):
    SKIPPED_MARKER = "skipped_marker"
    SKIPPED_EXPLICIT_PERSONALITY = "skipped_explicit_personality"
    SKIPPED_NO_SESSIONS = "skipped_no_sessions"
    APPLIED = "applied"


def maybe_migrate_personality(
    codex_home: str | Path,
    config_toml: Mapping[str, Any] | None = None,
    *,
    override_profile: str | None = None,
) -> PersonalityMigrationStatus:
    if override_profile is not None:
        _ensure_str(override_profile, "override_profile")
    home = Path(_ensure_pathlike(codex_home, "codex_home"))
    marker_path = home / PERSONALITY_MIGRATION_FILENAME
    if marker_path.exists():
        return PersonalityMigrationStatus.SKIPPED_MARKER

    config = dict(_ensure_mapping(config_toml, "config_toml")) if config_toml is not None else read_config_toml(home)
    if config.get("personality") is not None:
        create_personality_migration_marker(marker_path)
        return PersonalityMigrationStatus.SKIPPED_EXPLICIT_PERSONALITY

    model_provider_value = config.get("model_provider")
    model_provider_id = _ensure_str(model_provider_value, "model_provider") if model_provider_value is not None else "openai"
    if not has_recorded_sessions(home, model_provider_id):
        create_personality_migration_marker(marker_path)
        return PersonalityMigrationStatus.SKIPPED_NO_SESSIONS

    set_top_level_toml_string(home / "config.toml", "personality", Personality.PRAGMATIC.value)
    create_personality_migration_marker(marker_path)
    return PersonalityMigrationStatus.APPLIED


def read_config_toml(codex_home: str | Path) -> dict[str, Any]:
    path = Path(_ensure_pathlike(codex_home, "codex_home")) / "config.toml"
    if not path.exists():
        return {}
    with path.open("rb") as file:
        return dict(_toml.load(file))


def config_profile(
    config_toml: Mapping[str, Any],
    override_profile: str | None = None,
) -> dict[str, Any]:
    profile_name = _ensure_str(override_profile, "override_profile") if override_profile is not None else _optional_str(config_toml.get("profile"))
    profiles = config_toml.get("profiles")
    if not profile_name or not isinstance(profiles, Mapping):
        return {}
    profile = profiles.get(profile_name)
    return dict(profile) if isinstance(profile, Mapping) else {}


def has_recorded_sessions(codex_home: str | Path, default_provider: str = "openai") -> bool:
    home = Path(_ensure_pathlike(codex_home, "codex_home"))
    default_provider = _ensure_str(default_provider, "default_provider")
    active = get_threads_in_root(
        home / SESSIONS_SUBDIR,
        page_size=1,
        default_provider=default_provider,
        layout=ThreadListLayout.NESTED_BY_DATE,
    )
    if active.items:
        return True
    archived = get_threads_in_root(
        home / ARCHIVED_SESSIONS_SUBDIR,
        page_size=1,
        default_provider=default_provider,
        layout=ThreadListLayout.FLAT,
    )
    return bool(archived.items)


def create_personality_migration_marker(marker_path: str | Path) -> None:
    path = Path(_ensure_pathlike(marker_path, "marker_path"))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as file:
            file.write("v1\n")
    except FileExistsError:
        pass


def set_top_level_toml_string(path: str | Path, key: str, value: str) -> None:
    target = Path(_ensure_pathlike(path, "path"))
    target.parent.mkdir(parents=True, exist_ok=True)
    key = _ensure_str(key, "key")
    value = _ensure_str(value, "value")
    assignment = f'{key} = "{_escape_basic_toml_string(value)}"'
    if not target.exists():
        target.write_text(f"{assignment}\n", encoding="utf-8", newline="\n")
        return

    contents = target.read_text(encoding="utf-8")
    lines = contents.splitlines()
    insertion = len(lines)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            insertion = index
            break

    if insertion == 0:
        new_lines = [assignment, "", *lines]
    elif insertion == len(lines):
        new_lines = [*lines]
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append(assignment)
    else:
        new_lines = [*lines[:insertion]]
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.extend([assignment, "", *lines[insertion:]])
    target.write_text("\n".join(new_lines) + "\n", encoding="utf-8", newline="\n")


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _escape_basic_toml_string(value: str) -> str:
    value = _ensure_str(value, "value")
    return value.replace("\\", "\\\\").replace('"', '\\"')


__all__ = [
    "PERSONALITY_MIGRATION_FILENAME",
    "PersonalityMigrationStatus",
    "config_profile",
    "create_personality_migration_marker",
    "has_recorded_sessions",
    "maybe_migrate_personality",
    "read_config_toml",
    "set_top_level_toml_string",
]
