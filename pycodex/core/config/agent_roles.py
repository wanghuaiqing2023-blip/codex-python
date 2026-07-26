"""Agent role helpers ported from Codex core.

This module covers ``core/src/config/agent_roles.rs``: parsing role files and
normalizing role metadata. Runtime role selection and spawn-tool rendering are
owned by ``core::agent::role``.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, MutableSequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.config import toml_compat as _toml


UPSTREAM_AGENT_ROLES = "codex/codex-rs/core/src/config/agent_roles.rs"
class AgentRoleError(ValueError):
    """Raised when an agent role declaration is malformed."""


@dataclass(frozen=True)
class AgentRoleConfig:
    """Resolved role metadata used by the spawn-agent layer."""

    description: str | None = None
    config_file: Path | None = None
    nickname_candidates: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.description is not None and not isinstance(self.description, str):
            raise TypeError("description must be a string")
        if self.config_file is not None and not isinstance(self.config_file, Path):
            raise TypeError("config_file must be a Path")
        if self.nickname_candidates is not None:
            if isinstance(self.nickname_candidates, (str, bytes)) or not isinstance(
                self.nickname_candidates,
                Iterable,
            ):
                raise TypeError("nickname_candidates must be an iterable of strings")
            if not all(isinstance(candidate, str) for candidate in self.nickname_candidates):
                raise TypeError("nickname_candidates must contain only strings")
            object.__setattr__(self, "nickname_candidates", tuple(self.nickname_candidates))


@dataclass(frozen=True)
class ResolvedAgentRoleFile:
    """Parsed agent role file with metadata removed from ``config``."""

    role_name: str
    description: str | None
    nickname_candidates: tuple[str, ...] | None
    config: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.role_name, str):
            raise TypeError("role_name must be a string")
        if self.description is not None and not isinstance(self.description, str):
            raise TypeError("description must be a string")
        if self.nickname_candidates is not None:
            if isinstance(self.nickname_candidates, (str, bytes)) or not isinstance(
                self.nickname_candidates,
                Iterable,
            ):
                raise TypeError("nickname_candidates must be an iterable of strings")
            if not all(isinstance(candidate, str) for candidate in self.nickname_candidates):
                raise TypeError("nickname_candidates must contain only strings")
            object.__setattr__(self, "nickname_candidates", tuple(self.nickname_candidates))
        if not isinstance(self.config, dict):
            raise TypeError("config must be a dict")


def normalize_agent_role_description(field_label: str, description: str | None) -> str | None:
    """Trim an optional role description and reject blank values."""

    if not isinstance(field_label, str):
        raise TypeError("field_label must be a string")
    if description is None:
        return None
    if not isinstance(description, str):
        raise TypeError("description must be a string")
    normalized = description.strip()
    if not normalized:
        raise AgentRoleError(f"{field_label} cannot be blank")
    return normalized


def validate_required_agent_role_description(role_name: str, description: str | None) -> None:
    """Require a role description after config-layer merging."""

    if not isinstance(role_name, str):
        raise TypeError("role_name must be a string")
    if description is not None and not isinstance(description, str):
        raise TypeError("description must be a string")
    if description is None:
        raise AgentRoleError(f"agent role `{role_name}` must define a description")


def validate_agent_role_file_developer_instructions(
    role_file_label: str | Path,
    developer_instructions: str | None,
    require_present: bool,
) -> None:
    """Validate the developer instructions metadata in a role file."""

    label = Path(role_file_label)
    if developer_instructions is not None and not isinstance(developer_instructions, str):
        raise TypeError("developer_instructions must be a string")
    if not isinstance(require_present, bool):
        raise TypeError("require_present must be a bool")
    if developer_instructions is not None:
        if not developer_instructions.strip():
            raise AgentRoleError(f"agent role file at {label}.developer_instructions cannot be blank")
        return
    if require_present:
        raise AgentRoleError(f"agent role file at {label} must define `developer_instructions`")


def normalize_agent_role_nickname_candidates(
    field_label: str,
    nickname_candidates: Iterable[str] | None,
) -> tuple[str, ...] | None:
    """Normalize and validate optional nickname candidates."""

    if not isinstance(field_label, str):
        raise TypeError("field_label must be a string")
    if nickname_candidates is None:
        return None
    if isinstance(nickname_candidates, (str, bytes)) or not isinstance(nickname_candidates, Iterable):
        raise TypeError("nickname_candidates must be an iterable of strings")

    normalized_candidates: list[str] = []
    seen_candidates: set[str] = set()
    for nickname in nickname_candidates:
        if not isinstance(nickname, str):
            raise TypeError("nickname_candidates must contain only strings")
        normalized = nickname.strip()
        if not normalized:
            raise AgentRoleError(f"{field_label} cannot contain blank names")
        if normalized in seen_candidates:
            raise AgentRoleError(f"{field_label} cannot contain duplicates")
        if not all(char.isascii() and (char.isalnum() or char in " -_") for char in normalized):
            raise AgentRoleError(
                f"{field_label} may only contain ASCII letters, digits, spaces, hyphens, and underscores"
            )
        seen_candidates.add(normalized)
        normalized_candidates.append(normalized)

    if not normalized_candidates:
        raise AgentRoleError(f"{field_label} must contain at least one name")
    return tuple(normalized_candidates)


def parse_agent_role_file_contents(
    contents: str,
    role_file_label: str | Path,
    config_base_dir: str | Path | None = None,
    role_name_hint: str | None = None,
) -> ResolvedAgentRoleFile:
    """Parse a TOML role file into metadata plus config-layer contents."""
    if not isinstance(contents, str):
        raise TypeError("contents must be a string")
    if role_name_hint is not None and not isinstance(role_name_hint, str):
        raise TypeError("role_name_hint must be a string")
    label = Path(role_file_label)
    _ = Path(config_base_dir) if config_base_dir is not None else label.parent

    try:
        role_file_toml = _toml.loads(contents)
    except _toml.TOMLDecodeError as exc:
        raise AgentRoleError(f"failed to parse agent role file at {label}: {exc}") from exc

    if not isinstance(role_file_toml, dict):
        raise AgentRoleError(f"agent role file at {label} must contain a TOML table")

    description = normalize_agent_role_description(
        f"agent role file {label}.description",
        _metadata_str(role_file_toml, "description", f"agent role file {label}.description"),
    )
    validate_agent_role_file_developer_instructions(
        label,
        _metadata_str(
            role_file_toml,
            "developer_instructions",
            f"agent role file {label}.developer_instructions",
        ),
        role_name_hint is None,
    )

    role_name = _metadata_str(role_file_toml, "name", f"agent role file {label}.name")
    if role_name is not None:
        role_name = role_name.strip() or None
    role_name = role_name or role_name_hint
    if role_name is None:
        raise AgentRoleError(f"agent role file at {label} must define a non-empty `name`")

    raw_candidates = role_file_toml.get("nickname_candidates")
    if raw_candidates is not None and not _is_string_list(raw_candidates):
        raise AgentRoleError(f"agent role file {label}.nickname_candidates must be a list of strings")
    nickname_candidates = normalize_agent_role_nickname_candidates(
        f"agent role file {label}.nickname_candidates",
        raw_candidates,
    )

    config = dict(role_file_toml)
    config.pop("name", None)
    config.pop("description", None)
    config.pop("nickname_candidates", None)

    return ResolvedAgentRoleFile(
        role_name=role_name,
        description=description,
        nickname_candidates=nickname_candidates,
        config=config,
    )


def load_agent_roles_from_layers(
    layers: Iterable[Any],
    startup_warnings: MutableSequence[str] | None = None,
) -> dict[str, AgentRoleConfig]:
    """Load agent roles from config layers in Rust precedence order."""

    warnings = startup_warnings if startup_warnings is not None else []
    roles: dict[str, AgentRoleConfig] = {}
    for layer in layers:
        if getattr(layer, "enabled", True) is False:
            continue
        layer_roles: dict[str, AgentRoleConfig] = {}
        declared_role_files: set[Path] = set()
        config = getattr(layer, "config", None)
        if config is None:
            config = layer.get("config", {}) if isinstance(layer, Mapping) else {}
        if not isinstance(config, Mapping):
            push_agent_role_warning(warnings, AgentRoleError("agent role layer config must be a mapping"))
            continue

        config_folder = _layer_config_folder(layer)
        agents_toml = config.get("agents")
        if agents_toml is not None:
            if not isinstance(agents_toml, Mapping):
                push_agent_role_warning(warnings, AgentRoleError("agents must be a mapping"))
            else:
                declared_roles = agents_toml.get("roles", agents_toml)
                if not isinstance(declared_roles, Mapping):
                    push_agent_role_warning(warnings, AgentRoleError("agents.roles must be a mapping"))
                else:
                    for declared_role_name, role_toml in declared_roles.items():
                        try:
                            role_name, role = read_declared_role_from_mapping(
                                str(declared_role_name),
                                role_toml,
                                config_folder,
                            )
                        except (OSError, AgentRoleError, TypeError) as exc:
                            push_agent_role_warning(warnings, exc)
                            continue
                        if role.config_file is not None:
                            declared_role_files.add(role.config_file.resolve())
                        if role_name in layer_roles:
                            push_agent_role_warning(
                                warnings,
                                AgentRoleError(
                                    f"duplicate agent role name `{role_name}` declared in the same config layer"
                                ),
                            )
                            continue
                        layer_roles[role_name] = role

        if config_folder is not None:
            for role_name, role in discover_agent_roles_in_dir(
                config_folder / "agents",
                declared_role_files=declared_role_files,
                startup_warnings=warnings,
            ).items():
                if role_name in layer_roles:
                    push_agent_role_warning(
                        warnings,
                        AgentRoleError(
                            f"duplicate agent role name `{role_name}` declared in the same config layer"
                        ),
                    )
                    continue
                layer_roles[role_name] = role

        for role_name, role in layer_roles.items():
            merged_role = merge_missing_role_fields(role, roles[role_name]) if role_name in roles else role
            try:
                validate_required_agent_role_description(role_name, merged_role.description)
            except AgentRoleError as exc:
                push_agent_role_warning(warnings, exc)
                continue
            roles[role_name] = merged_role
    return roles


def load_agent_roles_from_config(config: Mapping[str, Any]) -> dict[str, AgentRoleConfig]:
    """Load declared agent roles without layer warning recovery."""

    if not isinstance(config, Mapping):
        raise TypeError("config must be a mapping")
    roles: dict[str, AgentRoleConfig] = {}
    agents_toml = config.get("agents")
    if agents_toml is None:
        return roles
    if not isinstance(agents_toml, Mapping):
        raise AgentRoleError("agents must be a mapping")
    declared_roles = agents_toml.get("roles", agents_toml)
    if not isinstance(declared_roles, Mapping):
        raise AgentRoleError("agents.roles must be a mapping")
    for declared_role_name, role_toml in declared_roles.items():
        role_name, role = read_declared_role_from_mapping(str(declared_role_name), role_toml, None)
        validate_required_agent_role_description(role_name, role.description)
        if role_name in roles:
            raise AgentRoleError(f"duplicate agent role name `{role_name}` declared in config")
        roles[role_name] = role
    return roles


def read_declared_role_from_mapping(
    declared_role_name: str,
    role_toml: Mapping[str, Any],
    config_base_dir: str | Path | None = None,
) -> tuple[str, AgentRoleConfig]:
    """Resolve one declared role, optionally loading its config file."""

    role = agent_role_config_from_mapping(declared_role_name, role_toml, config_base_dir)
    role_name = declared_role_name
    if role.config_file is not None:
        parsed = parse_agent_role_file_contents(
            role.config_file.read_text(encoding="utf-8"),
            role.config_file,
            role.config_file.parent,
            role_name_hint=declared_role_name,
        )
        role_name = parsed.role_name
        role = AgentRoleConfig(
            description=parsed.description or role.description,
            config_file=role.config_file,
            nickname_candidates=parsed.nickname_candidates or role.nickname_candidates,
        )
    return role_name, role


def agent_role_config_from_mapping(
    role_name: str,
    role_toml: Mapping[str, Any],
    config_base_dir: str | Path | None = None,
) -> AgentRoleConfig:
    """Normalize a declared ``[agents.roles.<name>]`` mapping."""

    if not isinstance(role_name, str):
        raise TypeError("role_name must be a string")
    if not isinstance(role_toml, Mapping):
        raise TypeError("role_toml must be a mapping")
    config_file = role_toml.get("config_file")
    if config_file is not None:
        if not isinstance(config_file, str):
            raise AgentRoleError(f"agents.{role_name}.config_file must be a string")
        path = Path(config_file)
        if not path.is_absolute() and config_base_dir is not None:
            path = Path(config_base_dir) / path
        if not path.exists():
            raise AgentRoleError(
                f"agents.{role_name}.config_file must point to an existing file at {path}: file not found"
            )
        if not path.is_file():
            raise AgentRoleError(f"agents.{role_name}.config_file must point to a file: {path}")
        config_file_path = path
    else:
        config_file_path = None

    description = normalize_agent_role_description(
        f"agents.{role_name}.description",
        _metadata_str(role_toml, "description", f"agents.{role_name}.description"),
    )
    raw_candidates = role_toml.get("nickname_candidates")
    if raw_candidates is not None and not _is_string_list(raw_candidates):
        raise AgentRoleError(f"agents.{role_name}.nickname_candidates must be a list of strings")
    nickname_candidates = normalize_agent_role_nickname_candidates(
        f"agents.{role_name}.nickname_candidates",
        raw_candidates,
    )
    return AgentRoleConfig(
        description=description,
        config_file=config_file_path,
        nickname_candidates=nickname_candidates,
    )


def merge_missing_role_fields(role: AgentRoleConfig, fallback: AgentRoleConfig) -> AgentRoleConfig:
    """Fill missing metadata fields from a lower-precedence role."""

    if not isinstance(role, AgentRoleConfig):
        raise TypeError("role must be an AgentRoleConfig")
    if not isinstance(fallback, AgentRoleConfig):
        raise TypeError("fallback must be an AgentRoleConfig")
    return AgentRoleConfig(
        description=role.description or fallback.description,
        config_file=role.config_file or fallback.config_file,
        nickname_candidates=role.nickname_candidates or fallback.nickname_candidates,
    )


def collect_agent_role_files(agents_dir: str | Path) -> list[Path]:
    """Recursively collect ``.toml`` role files in sorted order."""

    root = Path(agents_dir)
    if not root.exists():
        return []

    files: list[Path] = []
    for current_root, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for filename in sorted(filenames):
            path = Path(current_root) / filename
            if path.is_file() and path.suffix == ".toml":
                files.append(path)
    files.sort()
    return files


def discover_agent_roles_in_dir(
    agents_dir: str | Path,
    declared_role_files: Iterable[str | Path] = (),
    startup_warnings: MutableSequence[str] | None = None,
) -> dict[str, AgentRoleConfig]:
    """Discover role files under ``agents_dir`` and return valid role configs."""

    warnings = startup_warnings if startup_warnings is not None else []
    declared = {Path(path).resolve() for path in declared_role_files}
    roles: dict[str, AgentRoleConfig] = {}
    for role_file in collect_agent_role_files(agents_dir):
        if role_file.resolve() in declared:
            continue
        try:
            parsed = parse_agent_role_file_contents(
                role_file.read_text(encoding="utf-8"),
                role_file,
                role_file.parent,
                role_name_hint=None,
            )
            validate_required_agent_role_description(parsed.role_name, parsed.description)
        except (OSError, AgentRoleError) as exc:
            push_agent_role_warning(warnings, exc)
            continue

        if parsed.role_name in roles:
            push_agent_role_warning(
                warnings,
                AgentRoleError(f"duplicate agent role name `{parsed.role_name}` discovered in {Path(agents_dir)}"),
            )
            continue
        roles[parsed.role_name] = AgentRoleConfig(
            description=parsed.description,
            config_file=role_file,
            nickname_candidates=parsed.nickname_candidates,
        )
    return roles


def push_agent_role_warning(startup_warnings: MutableSequence[str], err: BaseException) -> None:
    """Append the upstream warning prefix for malformed role declarations."""

    startup_warnings.append(f"Ignoring malformed agent role definition: {err}")


def _metadata_str(data: Mapping[str, Any], key: str, field_label: str) -> str | None:
    if key not in data:
        return None
    value = data[key]
    if not isinstance(value, str):
        raise AgentRoleError(f"{field_label} must be a string")
    return value


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _layer_config_folder(layer: Any) -> Path | None:
    name = getattr(layer, "name", None)
    if isinstance(layer, Mapping):
        name = layer.get("name", name)
    if name is None:
        return None
    dot_codex_folder = getattr(name, "dot_codex_folder", None)
    if dot_codex_folder is not None:
        return Path(dot_codex_folder)
    file = getattr(name, "file", None)
    if file is not None:
        return Path(file).parent
    config_folder = getattr(layer, "config_folder", None)
    if callable(config_folder):
        value = config_folder()
        return None if value is None else Path(value)
    return None


__all__ = [
    "AgentRoleConfig",
    "AgentRoleError",
    "ResolvedAgentRoleFile",
    "agent_role_config_from_mapping",
    "collect_agent_role_files",
    "discover_agent_roles_in_dir",
    "load_agent_roles_from_config",
    "load_agent_roles_from_layers",
    "merge_missing_role_fields",
    "normalize_agent_role_description",
    "normalize_agent_role_nickname_candidates",
    "parse_agent_role_file_contents",
    "push_agent_role_warning",
    "read_declared_role_from_mapping",
    "validate_agent_role_file_developer_instructions",
    "validate_required_agent_role_description",
]

