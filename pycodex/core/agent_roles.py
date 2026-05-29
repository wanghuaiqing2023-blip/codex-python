"""Agent role helpers ported from Codex core.

This module covers the dependency-free pieces of
``core/src/config/agent_roles.rs`` and ``core/src/agent/role.rs``: parsing role
files, normalizing role metadata, exposing built-in roles, and rendering the
spawn-agent tool description.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from collections.abc import Iterable, Mapping, MutableSequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex import _toml


DEFAULT_ROLE_NAME = "default"
AGENT_TYPE_UNAVAILABLE_ERROR = "agent type is currently not available"
UPSTREAM_AGENT_ROLES = "codex/codex-rs/core/src/config/agent_roles.rs"
UPSTREAM_AGENT_ROLE_SPEC = "codex/codex-rs/core/src/agent/role.rs"

EXPLORER_TOML = ""
AWAITER_TOML = """background_terminal_max_timeout = 3600000
model_reasoning_effort = "low"
developer_instructions=\"\"\"You are an awaiter.
Your role is to await the completion of a specific command or task and report its status only when it is finished.

Behavior rules:

1. When given a command or task identifier, you must:
   - Execute or await it using the appropriate tool
   - Continue awaiting until the task reaches a terminal state.

2. You must NOT:
   - Modify the task.
   - Interpret or optimize the task.
   - Perform unrelated actions.
   - Stop awaiting unless explicitly instructed.

3. Awaiting behavior:
   - If the task is still running, continue polling using tool calls.
   - Use repeated tool calls if necessary.
   - Do not hallucinate completion.
   - Use long timeouts when awaiting for something. If you need multiple awaits, increase the timeouts/yield times exponentially.

4. If asked for status:
   - Return the current known status.
   - Immediately resume awaiting afterward.

5. Termination:
   - Only exit awaiting when:
     - The task completes successfully, OR
     - The task fails, OR
     - You receive an explicit stop instruction.

You must behave deterministically and conservatively.
\"\"\"
"""


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


def built_in_agent_role_configs() -> dict[str, AgentRoleConfig]:
    """Return built-in role declarations in upstream ``BTreeMap`` order."""

    roles = {
        DEFAULT_ROLE_NAME: AgentRoleConfig(description="Default agent."),
        "explorer": AgentRoleConfig(
            description="""Use `explorer` for specific codebase questions.
Explorers are fast and authoritative.
They must be used to ask specific, well-scoped questions on the codebase.
Rules:
- In order to avoid redundant work, you should avoid exploring the same problem that explorers have already covered. Typically, you should trust the explorer results without additional verification. You are still allowed to inspect the code yourself to gain the needed context!
- You are encouraged to spawn up multiple explorers in parallel when you have multiple distinct questions to ask about the codebase that can be answered independently. This allows you to get more information faster without waiting for one question to finish before asking the next. While waiting for the explorer results, you can continue working on other local tasks that do not depend on those results. This parallelism is a key advantage of delegation, so use it whenever you have multiple questions to ask.
- Reuse existing explorers for related questions.""",
            config_file=Path("explorer.toml"),
        ),
        "worker": AgentRoleConfig(
            description="""Use for execution and production work.
Typical tasks:
- Implement part of a feature
- Fix tests or bugs
- Split large refactors into independent chunks
Rules:
- Explicitly assign **ownership** of the task (files / responsibility). When the subtask involves code changes, you should clearly specify which files or modules the worker is responsible for. This helps avoid merge conflicts and ensures accountability. For example, you can say "Worker 1 is responsible for updating the authentication module, while Worker 2 will handle the database layer." By defining clear ownership, you can delegate more effectively and reduce coordination overhead.
- Always tell workers they are **not alone in the codebase**, and they should not revert the edits made by others, and they should adjust their implementation to accommodate the changes made by others. This is important because there may be multiple workers making changes in parallel, and they need to be aware of each other's work to avoid conflicts and ensure a cohesive final product.""",
        ),
    }
    return OrderedDict((name, roles[name]) for name in sorted(roles))


def built_in_agent_role_config_file_contents(path: str | Path) -> str | None:
    """Resolve embedded built-in role config-file contents."""

    path_text = Path(path).as_posix()
    if path_text == "explorer.toml":
        return EXPLORER_TOML
    if path_text == "awaiter.toml":
        return AWAITER_TOML
    return None


def resolve_role_config(
    user_defined_agent_roles: Mapping[str, AgentRoleConfig],
    role_name: str,
) -> AgentRoleConfig | None:
    """Resolve a user-defined role before falling back to built-ins."""

    if not isinstance(user_defined_agent_roles, Mapping):
        raise TypeError("user_defined_agent_roles must be a mapping")
    if not isinstance(role_name, str):
        raise TypeError("role_name must be a string")
    return user_defined_agent_roles.get(role_name) or built_in_agent_role_configs().get(role_name)


def build_spawn_agent_tool_description(user_defined_agent_roles: Mapping[str, AgentRoleConfig]) -> str:
    """Build the spawn-agent ``agent_type`` description text."""

    if not isinstance(user_defined_agent_roles, Mapping):
        raise TypeError("user_defined_agent_roles must be a mapping")
    formatted_roles: list[str] = []
    seen: set[str] = set()
    for name, declaration in sorted(user_defined_agent_roles.items()):
        if not isinstance(name, str):
            raise TypeError("agent role names must be strings")
        if not isinstance(declaration, AgentRoleConfig):
            raise TypeError("agent role declarations must be AgentRoleConfig values")
        if name not in seen:
            seen.add(name)
            formatted_roles.append(format_role_for_spawn_tool(name, declaration))
    for name, declaration in built_in_agent_role_configs().items():
        if name not in seen:
            seen.add(name)
            formatted_roles.append(format_role_for_spawn_tool(name, declaration))

    return (
        f"Optional type name for the new agent. If omitted, `{DEFAULT_ROLE_NAME}` is used.\n"
        "Available roles:\n"
        + "\n".join(formatted_roles)
    )


def format_role_for_spawn_tool(name: str, declaration: AgentRoleConfig) -> str:
    """Format a single role declaration for the spawn-agent tool spec."""

    if not isinstance(name, str):
        raise TypeError("name must be a string")
    if not isinstance(declaration, AgentRoleConfig):
        raise TypeError("declaration must be an AgentRoleConfig")
    if declaration.description is None:
        return f"{name}: no description"

    locked_settings_note = locked_settings_note_for_role(declaration)
    return f"{name}: {{\n{declaration.description}{locked_settings_note}\n}}"


def locked_settings_note_for_role(declaration: AgentRoleConfig) -> str:
    """Return the upstream note for role config fields that lock spawn settings."""

    if declaration.config_file is None:
        return ""

    contents = built_in_agent_role_config_file_contents(declaration.config_file)
    if contents is None:
        try:
            contents = Path(declaration.config_file).read_text(encoding="utf-8")
        except OSError:
            return ""
    if not contents.strip():
        return ""

    try:
        role_toml = _toml.loads(contents)
    except _toml.TOMLDecodeError:
        return ""

    model = _optional_str(role_toml.get("model"))
    reasoning_effort = _optional_str(role_toml.get("model_reasoning_effort"))
    service_tier = _optional_str(role_toml.get("service_tier"))

    if model is not None and reasoning_effort is not None:
        model_and_reasoning_note = (
            f"\n- This role's model is set to `{model}` and its reasoning effort is set to "
            f"`{reasoning_effort}`. These settings cannot be changed."
        )
    elif model is not None:
        model_and_reasoning_note = f"\n- This role's model is set to `{model}` and cannot be changed."
    elif reasoning_effort is not None:
        model_and_reasoning_note = (
            f"\n- This role's reasoning effort is set to `{reasoning_effort}` and cannot be changed."
        )
    else:
        model_and_reasoning_note = ""

    service_tier_note = (
        f"\n- This role's service tier is set to `{service_tier}`. If it is supported by the resolved model, "
        "it takes precedence over a valid spawn request service tier."
        if service_tier is not None
        else ""
    )
    return model_and_reasoning_note + service_tier_note


def format_agent_nickname(name: str, nickname_reset_count: int) -> str:
    """Format a nickname after the available name pool has been reset."""

    if not isinstance(name, str):
        raise TypeError("name must be a string")
    if isinstance(nickname_reset_count, bool) or not isinstance(nickname_reset_count, int):
        raise TypeError("nickname_reset_count must be an integer")
    if nickname_reset_count == 0:
        return name
    value = nickname_reset_count + 1
    if value % 100 in (11, 12, 13):
        suffix = "th"
    elif value % 10 == 1:
        suffix = "st"
    elif value % 10 == 2:
        suffix = "nd"
    elif value % 10 == 3:
        suffix = "rd"
    else:
        suffix = "th"
    return f"{name} the {value}{suffix}"


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _metadata_str(data: Mapping[str, Any], key: str, field_label: str) -> str | None:
    if key not in data:
        return None
    value = data[key]
    if not isinstance(value, str):
        raise AgentRoleError(f"{field_label} must be a string")
    return value


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


__all__ = [
    "AGENT_TYPE_UNAVAILABLE_ERROR",
    "AWAITER_TOML",
    "DEFAULT_ROLE_NAME",
    "EXPLORER_TOML",
    "AgentRoleConfig",
    "AgentRoleError",
    "ResolvedAgentRoleFile",
    "build_spawn_agent_tool_description",
    "built_in_agent_role_config_file_contents",
    "built_in_agent_role_configs",
    "collect_agent_role_files",
    "discover_agent_roles_in_dir",
    "format_agent_nickname",
    "format_role_for_spawn_tool",
    "locked_settings_note_for_role",
    "merge_missing_role_fields",
    "normalize_agent_role_description",
    "normalize_agent_role_nickname_candidates",
    "parse_agent_role_file_contents",
    "push_agent_role_warning",
    "resolve_role_config",
    "validate_agent_role_file_developer_instructions",
    "validate_required_agent_role_description",
]
