"""Migration helpers for importing Claude configuration into Codex.

Python port of ``codex-external-agent-migration/src/lib.rs``. The public
functions mirror the Rust crate's filesystem-facing behavior while returning
plain Python dictionaries for TOML/JSON-shaped values.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from pycodex.hooks import HOOK_EVENT_NAMES, HOOK_EVENT_NAMES_WITH_MATCHERS

SOURCE_EXTERNAL_AGENT_NAME = "claude"
EXTERNAL_AGENT_MCP_CONFIG_FILE = ".mcp.json"
EXTERNAL_AGENT_HOOKS_SUBDIR = "hooks"
EXTERNAL_AGENT_MIGRATED_HOOKS_SUBDIR = "hooks"
COMMAND_SKILL_PREFIX = "source-command"
MAX_SKILL_NAME_LEN = 64
MAX_SKILL_DESCRIPTION_LEN = 1024


@dataclass(frozen=True)
class ParsedDocument:
    frontmatter: dict[str, "_FrontmatterValue"]
    body: str
    frontmatter_error: str | None = None


@dataclass(frozen=True)
class _FrontmatterValue:
    value: str | None

    @classmethod
    def scalar(cls, value: str) -> "_FrontmatterValue":
        return cls(value.strip())

    @classmethod
    def other(cls) -> "_FrontmatterValue":
        return cls(None)

    def as_scalar(self) -> str | None:
        return self.value


@dataclass(frozen=True)
class _AgentMetadata:
    name: str
    description: str
    permission_mode: str | None = None
    effort: str | None = None


def build_mcp_config_from_external(
    source_root: Path | str,
    external_agent_home: Path | str | None = None,
    settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(source_root)
    home = Path(external_agent_home) if external_agent_home is not None else None
    servers = _read_external_mcp_servers(root, home)
    if not servers:
        return {}

    enabled_servers = _json_string_vec(settings.get("enabledMcpjsonServers")) if isinstance(settings, Mapping) else []
    disabled_servers = set(_json_string_vec(settings.get("disabledMcpjsonServers"))) if isinstance(settings, Mapping) else set()

    converted: dict[str, Any] = {}
    for server_name in sorted(servers):
        table = _mcp_server_toml_table(server_name, servers[server_name], enabled_servers, disabled_servers)
        if table is not None:
            converted[server_name] = table
    return {"mcp_servers": converted} if converted else {}


def hooks_migration_description(
    source_external_agent_dir: Path | str,
    target_hooks: Path | str,
) -> str | None:
    source = Path(source_external_agent_dir)
    target = Path(target_hooks)
    if not hook_migration_event_names(source, target):
        return None
    return f"Migrate hooks from {source} to {target}"


def hook_migration_event_names(
    source_external_agent_dir: Path | str,
    target_hooks: Path | str,
) -> list[str]:
    target = Path(target_hooks)
    migration = _hook_migration(Path(source_external_agent_dir), target.parent)
    return sorted(migration.keys())


def import_hooks(source_external_agent_dir: Path | str, target_hooks: Path | str) -> bool:
    source = Path(source_external_agent_dir)
    target = Path(target_hooks)
    parent = target.parent
    if str(parent) == "":
        raise ValueError("hooks target path has no parent")
    migration = _hook_migration(source, parent)
    if not migration:
        return False

    parent.mkdir(parents=True, exist_ok=True)
    if _is_missing_or_empty_text_file(target):
        _copy_hook_scripts(source, parent)
        target.write_text(json.dumps({"hooks": migration}, indent=2) + "\n", encoding="utf-8")
        return True
    return False


def count_missing_subagents(source_agents: Path | str, target_agents: Path | str) -> int:
    return len(missing_subagent_names(source_agents, target_agents))


def missing_subagent_names(source_agents: Path | str, target_agents: Path | str) -> list[str]:
    target_root = Path(target_agents)
    names: list[str] = []
    for source_file in _agent_source_files(Path(source_agents)):
        document = _parse_document(source_file)
        metadata = _agent_metadata(document)
        target = _subagent_target_file(source_file, target_root)
        if metadata is not None and target is not None and not target.exists():
            names.append(metadata.name)
    return names


def import_subagents(source_agents: Path | str, target_agents: Path | str) -> int:
    source_root = Path(source_agents)
    target_root = Path(target_agents)
    if not source_root.is_dir():
        return 0
    target_root.mkdir(parents=True, exist_ok=True)
    imported = 0
    for source_file in _agent_source_files(source_root):
        target = _subagent_target_file(source_file, target_root)
        if target is None or target.exists():
            continue
        document = _parse_document(source_file)
        metadata = _agent_metadata(document)
        if metadata is None:
            continue
        target.write_text(_render_agent_toml(document.body, metadata), encoding="utf-8")
        imported += 1
    return imported


def count_missing_commands(source_commands: Path | str, target_skills: Path | str) -> int:
    return len(missing_command_names(source_commands, target_skills))


def missing_command_names(source_commands: Path | str, target_skills: Path | str) -> list[str]:
    target_root = Path(target_skills)
    return [
        name
        for _source_file, name in _unique_supported_command_sources(Path(source_commands))
        if not (target_root / name).exists()
    ]


def import_commands(source_commands: Path | str, target_skills: Path | str) -> int:
    source_root = Path(source_commands)
    target_root = Path(target_skills)
    if not source_root.is_dir():
        return 0
    target_root.mkdir(parents=True, exist_ok=True)
    imported = 0
    for source_file, name in _unique_supported_command_sources(source_root):
        target_dir = target_root / name
        if target_dir.exists():
            continue
        document = _parse_document(source_file)
        source_name = _command_source_name(source_root, source_file)
        description = _command_skill_description(document, source_name)
        if description is None:
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "SKILL.md").write_text(
            _render_command_skill(document.body, name, description, source_name),
            encoding="utf-8",
        )
        imported += 1
    return imported


def rewrite_external_agent_terms(content: str) -> str:
    rewritten = _replace_case_insensitive_with_boundaries(content, _external_agent_doc_file_name(), "AGENTS.md")
    for source in _external_agent_term_variants():
        rewritten = _replace_case_insensitive_with_boundaries(rewritten, source, "Codex")
    return rewritten


def _read_external_mcp_servers(source_root: Path, external_agent_home: Path | None) -> dict[str, Any]:
    servers: dict[str, Any] = {}
    project_config_file = _external_agent_project_config_file()
    for relative_path in (EXTERNAL_AGENT_MCP_CONFIG_FILE, project_config_file):
        source_file = source_root / relative_path
        if not source_file.is_file():
            continue
        parsed = _read_json_file(source_file, "invalid MCP config")
        _append_mcp_servers_from_value(parsed, servers, overwrite=True)
        projects = parsed.get("projects") if isinstance(parsed, Mapping) else None
        if relative_path == project_config_file and isinstance(projects, Mapping):
            for project_path, project_config in projects.items():
                if _project_path_matches_source_root(str(project_path), source_root):
                    _append_mcp_servers_from_value(project_config, servers, overwrite=True)
    external_root = external_agent_home.parent if external_agent_home is not None else None
    if external_root is not None and external_root != source_root:
        _append_external_agent_project_mcp_servers(external_root / _external_agent_project_config_file(), source_root, servers)
    return servers


def _append_external_agent_project_mcp_servers(source_file: Path, source_root: Path, servers: dict[str, Any]) -> None:
    if not source_file.is_file():
        return
    parsed = _read_json_file(source_file, "invalid MCP config")
    projects = parsed.get("projects") if isinstance(parsed, Mapping) else None
    if not isinstance(projects, Mapping):
        return
    for project_path, project_config in projects.items():
        if _project_path_matches_source_root(str(project_path), source_root):
            _append_mcp_servers_from_value(project_config, servers, overwrite=False)


def _append_mcp_servers_from_value(value: Any, servers: dict[str, Any], *, overwrite: bool) -> None:
    mcp_servers = value.get("mcpServers") if isinstance(value, Mapping) else None
    if not isinstance(mcp_servers, Mapping):
        return
    for server_name, server_config in mcp_servers.items():
        if overwrite or str(server_name) not in servers:
            servers[str(server_name)] = server_config


def _project_path_matches_source_root(project_path: str, source_root: Path) -> bool:
    candidate = Path(project_path)
    if candidate == source_root:
        return True
    try:
        return candidate.resolve(strict=True) == source_root.resolve(strict=True)
    except OSError:
        return False


def _mcp_server_toml_table(
    server_name: str,
    server_config: Any,
    enabled_servers: list[str],
    disabled_servers: set[str],
) -> dict[str, Any] | None:
    if not isinstance(server_config, Mapping):
        return None
    transport_type = _json_string(server_config.get("type"))
    if _mcp_server_is_disabled(server_name, server_config, enabled_servers, disabled_servers):
        return None

    table: dict[str, Any] = {}
    command = _json_string(server_config.get("command"))
    url = _json_string(server_config.get("url"))
    if command is not None:
        if transport_type not in (None, "stdio") or _contains_env_placeholder(command):
            return None
        table["command"] = command
        args = _json_string_vec(server_config.get("args")) if "args" in server_config else []
        if any(_contains_env_placeholder(arg) for arg in args):
            return None
        if args:
            table["args"] = args
        env = server_config.get("env")
        if isinstance(env, Mapping) and not _append_env_config(table, env):
            return None
    elif url is not None:
        if transport_type not in (None, "http", "streamable_http") or _contains_env_placeholder(url):
            return None
        table["url"] = url
        headers = server_config.get("headers")
        if isinstance(headers, Mapping) and not _append_header_config(table, headers):
            return None
    else:
        return None
    return table


def _mcp_server_is_disabled(
    server_name: str,
    server_config: Mapping[str, Any],
    enabled_servers: list[str],
    disabled_servers: set[str],
) -> bool:
    return (
        server_config.get("enabled") is False
        or server_config.get("disabled") is True
        or (bool(enabled_servers) and server_name not in enabled_servers)
        or server_name in disabled_servers
    )


def _append_header_config(table: dict[str, Any], headers: Mapping[str, Any]) -> bool:
    static_headers: dict[str, str] = {}
    env_headers: dict[str, str] = {}
    for key, value in headers.items():
        header_key = str(key)
        header_value = _json_string(value)
        if header_value is None:
            header_value = json.dumps(value, separators=(",", ":"))
        if header_key.lower() == "authorization" and header_value.startswith("Bearer "):
            token_env = _parse_env_placeholder(header_value.removeprefix("Bearer "))
            if token_env is not None:
                table["bearer_token_env_var"] = token_env
                continue
        env_var = _parse_env_placeholder(header_value)
        if env_var is not None:
            env_headers[header_key] = env_var
        elif _contains_env_placeholder(header_value):
            return False
        else:
            static_headers[header_key] = header_value
    if static_headers:
        table["http_headers"] = static_headers
    if env_headers:
        table["env_http_headers"] = env_headers
    return True


def _append_env_config(table: dict[str, Any], env: Mapping[str, Any]) -> bool:
    static_env: dict[str, str] = {}
    env_vars: list[str] = []
    for key, value in env.items():
        env_key = str(key)
        env_value = _json_string(value)
        if env_value is None:
            env_value = json.dumps(value, separators=(",", ":"))
        if _parse_env_placeholder(env_value) == env_key:
            env_vars.append(env_key)
        elif _contains_env_placeholder(env_value):
            return False
        else:
            static_env[env_key] = env_value
    if env_vars:
        table["env_vars"] = env_vars
    if static_env:
        table["env"] = static_env
    return True


def _parse_env_placeholder(value: str) -> str | None:
    if not (value.startswith("${") and value.endswith("}")):
        return None
    name = value[2:-1].split(":-", 1)[0]
    if not name or not (name[0] == "_" or name[0].isalpha() and name[0].isascii()):
        return None
    if not all(ch == "_" or (ch.isalnum() and ch.isascii()) for ch in name[1:]):
        return None
    return name


def _contains_env_placeholder(value: str) -> bool:
    return "${" in value


def _hook_migration(source_external_agent_dir: Path, target_config_dir: Path | None) -> dict[str, Any]:
    settings_files: list[Any] = []
    disable_all_hooks: bool | None = None
    for settings_name in ("settings.json", "settings.local.json"):
        settings_file = source_external_agent_dir / settings_name
        if not settings_file.is_file():
            continue
        settings = _read_json_file(settings_file, "invalid hooks settings")
        if isinstance(settings, Mapping) and isinstance(settings.get("disableAllHooks"), bool):
            disable_all_hooks = settings["disableAllHooks"]
        settings_files.append(settings)
    if disable_all_hooks is True:
        return {}

    migration: dict[str, Any] = {}
    for settings in settings_files:
        _append_convertible_hook_groups(settings, migration, target_config_dir)
    return migration


def _append_convertible_hook_groups(settings: Any, hooks_payload: dict[str, Any], target_config_dir: Path | None) -> None:
    hooks_config = settings.get("hooks") if isinstance(settings, Mapping) else None
    if not isinstance(hooks_config, Mapping):
        return
    for event_name in HOOK_EVENT_NAMES:
        groups = hooks_config.get(event_name)
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, Mapping):
                continue
            if "if" in group or any(key not in {"matcher", "hooks"} for key in group):
                continue
            hook_commands: list[dict[str, Any]] = []
            hooks = group.get("hooks")
            if isinstance(hooks, list):
                for hook in hooks:
                    if not isinstance(hook, Mapping):
                        continue
                    hook_type = hook.get("type", "command")
                    if hook_type != "command":
                        continue
                    allowed = {"type", "command", "timeout", "timeoutSec", "statusMessage", "async"}
                    if any(key not in allowed for key in hook):
                        continue
                    if hook.get("async") is True or any(field in hook for field in ("asyncRewake", "shell", "once")):
                        continue
                    command = hook.get("command")
                    if not isinstance(command, str) or not command.strip():
                        continue
                    payload: dict[str, Any] = {
                        "type": "command",
                        "command": _rewrite_hook_command(command.strip(), target_config_dir),
                    }
                    timeout = _json_u64(hook.get("timeout", hook.get("timeoutSec")))
                    if timeout is not None:
                        payload["timeout"] = timeout
                    status_message = hook.get("statusMessage")
                    if isinstance(status_message, str):
                        payload["statusMessage"] = rewrite_external_agent_terms(status_message)
                    hook_commands.append(payload)
            if not hook_commands:
                continue
            group_payload: dict[str, Any] = {}
            if event_name in HOOK_EVENT_NAMES_WITH_MATCHERS and isinstance(group.get("matcher"), str):
                group_payload["matcher"] = group["matcher"]
            group_payload["hooks"] = hook_commands
            hooks_payload.setdefault(event_name, []).append(group_payload)


def _rewrite_hook_command(command: str, target_config_dir: Path | None) -> str:
    if target_config_dir is None or _looks_like_windows_hook_command(command):
        return command
    target_hooks_dir = target_config_dir / EXTERNAL_AGENT_MIGRATED_HOOKS_SUBDIR
    source_hooks_path = f"{_external_agent_config_dir()}/{EXTERNAL_AGENT_HOOKS_SUBDIR}/"
    command = _replace_quoted_hook_paths(command, "'", source_hooks_path, target_hooks_dir)
    command = _replace_quoted_hook_paths(command, '"', source_hooks_path, target_hooks_dir)
    return _replace_unquoted_hook_paths(command, source_hooks_path, target_hooks_dir)


def _replace_quoted_hook_paths(command: str, quote: str, source_hooks_path: str, target_hooks_dir: Path) -> str:
    rewritten = command
    search_start = 0
    while True:
        start = rewritten.find(quote, search_start)
        if start == -1:
            break
        content_start = start + len(quote)
        end = rewritten.find(quote, content_start)
        if end == -1:
            break
        content = rewritten[content_start:end]
        source_hooks_start = content.find(source_hooks_path)
        if source_hooks_start == -1:
            search_start = end + len(quote)
            continue
        suffix = content[source_hooks_start + len(source_hooks_path) :]
        replacement = _target_hook_path_replacement(target_hooks_dir, content, source_hooks_start, suffix)
        if replacement is None:
            search_start = end + len(quote)
            continue
        rewritten = rewritten[:start] + replacement + rewritten[end + len(quote) :]
        search_start = start + len(replacement)
    return rewritten


def _replace_unquoted_hook_paths(command: str, source_hooks_path: str, target_hooks_dir: Path) -> str:
    rewritten = command
    search_start = 0
    while True:
        source_hooks_start = _find_unquoted_source_hook_path(rewritten, source_hooks_path, search_start)
        if source_hooks_start is None:
            break
        path_start = _shell_path_start(rewritten, source_hooks_start)
        path_end = _shell_path_end(rewritten, source_hooks_start + len(source_hooks_path))
        if _is_assignment_value_start(rewritten, path_start):
            search_start = source_hooks_start + len(source_hooks_path)
            continue
        path = rewritten[path_start:path_end]
        suffix = rewritten[source_hooks_start + len(source_hooks_path) : path_end]
        replacement = _target_hook_path_replacement(target_hooks_dir, path, source_hooks_start - path_start, suffix)
        if replacement is None:
            search_start = source_hooks_start + len(source_hooks_path)
            continue
        rewritten = rewritten[:path_start] + replacement + rewritten[path_end:]
        search_start = path_start + len(replacement)
    return rewritten


def _find_unquoted_source_hook_path(command: str, source_hooks_path: str, start: int) -> int | None:
    in_single_quote = False
    in_double_quote = False
    escaped = False
    index = start
    while index < len(command):
        ch = command[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if not in_single_quote and ch == "\\":
            escaped = True
            index += 1
            continue
        if ch == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif ch == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif not in_single_quote and not in_double_quote and command.startswith(source_hooks_path, index):
            return index
        index += 1
    return None


def _is_pure_shell_path_content(content: str, source_hooks_start: int) -> bool:
    prefix = content[:source_hooks_start]
    return (not prefix or prefix == "./" or prefix.endswith("/")) and not any(_is_shell_path_boundary(ch) for ch in prefix)


def _shell_path_start(command: str, end: int) -> int:
    result = 0
    for index, ch in enumerate(command[:end]):
        if _is_shell_path_boundary(ch):
            result = index + 1
    return result


def _shell_path_end(command: str, start: int) -> int:
    escaped = False
    for offset, ch in enumerate(command[start:]):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if _is_shell_path_boundary(ch):
            return start + offset
    return len(command)


def _is_shell_path_boundary(ch: str) -> bool:
    return ch.isspace() or ch in "=;|&<>()"


def _is_assignment_value_start(command: str, path_start: int) -> bool:
    return path_start > 0 and command[path_start - 1] == "="


def _target_hook_path_replacement(target_hooks_dir: Path, path: str, source_hooks_start: int, suffix: str) -> str | None:
    if not _is_pure_shell_path_content(path, source_hooks_start) or not _is_static_hook_path_suffix(suffix):
        return None
    return _shell_single_quote(str(target_hooks_dir / suffix))


def _is_static_hook_path_suffix(suffix: str) -> bool:
    return bool(suffix) and not any(ch in "\\$`*?[{}" for ch in suffix)


def _looks_like_windows_hook_command(command: str) -> bool:
    project_dir_env_var = _external_agent_project_dir_env_var()
    source_hooks_backslash_path = f"{_external_agent_config_dir()}\\{EXTERNAL_AGENT_HOOKS_SUBDIR}\\"
    return (
        source_hooks_backslash_path in command
        or f"%{project_dir_env_var}%" in command
        or f"$env:{project_dir_env_var}" in command
    )


def _shell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _copy_hook_scripts(source_external_agent_dir: Path, target_config_dir: Path) -> None:
    source_hooks = source_external_agent_dir / EXTERNAL_AGENT_HOOKS_SUBDIR
    if not source_hooks.is_dir():
        return
    _copy_dir_recursive_skip_existing(source_hooks, target_config_dir / EXTERNAL_AGENT_MIGRATED_HOOKS_SUBDIR)


def _copy_dir_recursive_skip_existing(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for source_path in source.iterdir():
        target_path = target / source_path.name
        if source_path.is_dir():
            _copy_dir_recursive_skip_existing(source_path, target_path)
        elif source_path.is_file() and not target_path.exists():
            shutil.copyfile(source_path, target_path)


def _agent_source_files(source_agents: Path) -> list[Path]:
    if not source_agents.is_dir():
        return []
    return sorted(
        path
        for path in source_agents.iterdir()
        if path.is_file() and path.suffix == ".md" and path.stem != "README"
    )


def _subagent_target_file(source_file: Path, target_agents: Path) -> Path | None:
    return target_agents / f"{source_file.stem}.toml" if source_file.stem else None


def _command_source_files(source_commands: Path) -> list[Path]:
    files: list[Path] = []
    _collect_markdown_files(source_commands, files)
    return sorted(files)


def _unique_supported_command_sources(source_commands: Path) -> list[tuple[Path, str]]:
    by_name: dict[str, list[Path]] = {}
    for source_file in _command_source_files(source_commands):
        document = _parse_document(source_file)
        name = _command_skill_name_if_supported(source_commands, source_file, document)
        if name is not None:
            by_name.setdefault(name, []).append(source_file)
    return [(paths[0], name) for name, paths in sorted(by_name.items()) if len(paths) == 1]


def _collect_markdown_files(directory: Path, files: list[Path]) -> None:
    if not directory.is_dir():
        return
    for path in directory.iterdir():
        if path.is_dir():
            _collect_markdown_files(path, files)
        elif path.is_file() and path.suffix == ".md":
            files.append(path)


def _parse_document(source_file: Path) -> ParsedDocument:
    return _parse_document_content(source_file.read_text(encoding="utf-8"))


def _parse_document_content(content: str) -> ParsedDocument:
    if content.startswith("---\r\n"):
        rest = content[5:]
    elif content.startswith("---\n"):
        rest = content[4:]
    else:
        return ParsedDocument({}, content)
    end_info = _frontmatter_end(rest)
    if end_info is None:
        return ParsedDocument({}, content)
    end, body_start = end_info
    frontmatter, error = _parse_frontmatter(rest[:end])
    return ParsedDocument(frontmatter, rest[body_start:], error)


def _frontmatter_end(rest: str) -> tuple[int, int] | None:
    candidates = []
    for delimiter in ("\r\n---\r\n", "\r\n---\n", "\n---\r\n", "\n---\n", "\r\n---", "\n---"):
        index = rest.find(delimiter)
        if index != -1:
            candidates.append((index, index + len(delimiter)))
    return min(candidates, key=lambda item: item[0]) if candidates else None


def _parse_frontmatter(raw_frontmatter: str) -> tuple[dict[str, _FrontmatterValue], str | None]:
    frontmatter: dict[str, _FrontmatterValue] = {}
    lines = raw_frontmatter.splitlines()
    index = 0
    try:
        while index < len(lines):
            line = lines[index]
            index += 1
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if ":" not in line:
                return {}, "frontmatter is not a YAML mapping"
            key, raw_value = line.split(":", 1)
            key = key.strip()
            if not key:
                continue
            value = raw_value.strip()
            if not value:
                if index < len(lines) and (lines[index].startswith(" ") or lines[index].startswith("\t")):
                    frontmatter[key] = _FrontmatterValue.other()
                    while index < len(lines) and (lines[index].startswith(" ") or lines[index].startswith("\t")):
                        index += 1
                else:
                    frontmatter[key] = _FrontmatterValue.scalar("")
                continue
            frontmatter[key] = _frontmatter_scalar(value)
    except Exception as exc:  # pragma: no cover - defensive parity with Rust error storage
        return {}, str(exc)
    return frontmatter, None


def _frontmatter_scalar(value: str) -> _FrontmatterValue:
    if value in {"[]", "{}"} or value.startswith("[") or value.startswith("{"):
        return _FrontmatterValue.other()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return _FrontmatterValue.scalar(value[1:-1])
    if value in {"true", "false"} or value in {"null", "~"} or re.fullmatch(r"[-+]?\d+(\.\d+)?", value):
        return _FrontmatterValue.scalar(value if value not in {"null", "~"} else "")
    return _FrontmatterValue.scalar(value)


def _agent_metadata(document: ParsedDocument) -> _AgentMetadata | None:
    if document.frontmatter_error is not None or not document.body.strip():
        return None
    name = document.frontmatter.get("name").as_scalar() if "name" in document.frontmatter else None
    description = document.frontmatter.get("description").as_scalar() if "description" in document.frontmatter else None
    if not name or not description:
        return None
    return _AgentMetadata(
        name=name,
        description=description,
        permission_mode=_frontmatter_string(document.frontmatter, "permissionMode"),
        effort=_frontmatter_string(document.frontmatter, "effort"),
    )


def _render_agent_toml(body: str, metadata: _AgentMetadata) -> str:
    items: list[tuple[str, str, bool]] = [
        ("name", metadata.name, False),
        ("description", rewrite_external_agent_terms(metadata.description), False),
    ]
    if metadata.effort is not None:
        effort = _map_agent_reasoning_effort(metadata.effort)
        if effort is not None:
            items.append(("model_reasoning_effort", effort, False))
    if metadata.permission_mode is not None:
        sandbox = _map_agent_permission_mode(metadata.permission_mode)
        if sandbox is not None:
            items.append(("sandbox_mode", sandbox, False))
    items.append(("developer_instructions", _render_agent_body(body), True))
    lines = []
    for key, value, multiline in items:
        if multiline:
            lines.append(f'{key} = """\n{value}"""')
        else:
            lines.append(f'{key} = "{_toml_escape(value)}"')
    return "\n".join(lines).rstrip() + "\n"


def _render_agent_body(body: str) -> str:
    rewritten = rewrite_external_agent_terms(body.strip())
    return rewritten if rewritten else "No subagent instructions were found."


def _command_skill_name(source_commands: Path, source_file: Path) -> str:
    return _slugify_name(f"{COMMAND_SKILL_PREFIX}-{_command_source_name(source_commands, source_file)}")


def _command_skill_name_if_supported(source_commands: Path, source_file: Path, document: ParsedDocument) -> str | None:
    if source_file.stem == "README":
        return None
    source_name = _command_source_name(source_commands, source_file)
    description = _command_skill_description(document, source_name)
    if description is None:
        return None
    name = _command_skill_name(source_commands, source_file)
    if len(name) > MAX_SKILL_NAME_LEN or len(description) > MAX_SKILL_DESCRIPTION_LEN:
        return None
    if _has_unsupported_command_template_features(document.body):
        return None
    return name


def _command_skill_description(document: ParsedDocument, _source_name: str) -> str | None:
    description = document.frontmatter.get("description").as_scalar() if "description" in document.frontmatter else None
    return description if description and description.strip() else None


def _command_source_name(source_commands: Path, source_file: Path) -> str:
    try:
        relative = source_file.relative_to(source_commands)
    except ValueError:
        relative = source_file
    return "-".join(relative.with_suffix("").parts)


def _render_command_skill(body: str, name: str, description: str, source_name: str) -> str:
    rewritten_body = rewrite_external_agent_terms(body.strip())
    template_body = rewritten_body if rewritten_body else "No command template body was found."
    return (
        "---\n"
        f"name: {_yaml_string(name)}\n"
        f"description: {_yaml_string(rewrite_external_agent_terms(description))}\n"
        "---\n\n"
        f"# {name}\n\n"
        f"Use this skill when the user asks to run the migrated source command `{source_name}`.\n\n"
        "## Command Template\n\n"
        f"{template_body}\n"
    )


def _has_unsupported_command_template_features(template: str) -> bool:
    return (
        "$ARGUMENTS" in template
        or _contains_numbered_argument_placeholder(template)
        or ("{{" in template and "}}" in template)
        or "!`" in template
        or "! `" in template
        or any(token.startswith("@") and len(token) > 1 for token in template.split())
    )


def _contains_numbered_argument_placeholder(template: str) -> bool:
    data = template.encode()
    return any(data[index] == ord("$") and chr(data[index + 1]).isdigit() for index in range(len(data) - 1))


def _frontmatter_string(frontmatter: Mapping[str, _FrontmatterValue], key: str) -> str | None:
    return frontmatter[key].as_scalar() if key in frontmatter else None


def _map_agent_reasoning_effort(effort: str) -> str | None:
    mapped = "xhigh" if effort == "max" else effort
    return mapped if mapped in {"none", "minimal", "low", "medium", "high", "xhigh"} else None


def _map_agent_permission_mode(permission_mode: str) -> str | None:
    return {"acceptEdits": "workspace-write", "readOnly": "read-only"}.get(permission_mode)


def _json_string_vec(value: Any) -> list[str]:
    if isinstance(value, list):
        return [string for item in value if (string := _json_string(item)) is not None]
    string = _json_string(value)
    return [] if string is None else [string]


def _json_string(value: Any) -> str | None:
    if value is None or isinstance(value, (list, dict)):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _json_u64(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed >= 0 else None
    return None


def _yaml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _slugify_name(value: str) -> str:
    slug: list[str] = []
    last_was_dash = False
    for ch in value:
        if ch.isascii() and ch.isalnum():
            slug.append(ch.lower())
            last_was_dash = False
        elif not last_was_dash:
            slug.append("-")
            last_was_dash = True
    rendered = "".join(slug).strip("-")
    return rendered or "migrated"


def _is_missing_or_empty_text_file(path: Path) -> bool:
    if not path.exists():
        return True
    if not path.is_file():
        return False
    return not path.read_text(encoding="utf-8").strip()


def _replace_case_insensitive_with_boundaries(input_text: str, needle: str, replacement: str) -> str:
    needle_lower = needle.lower()
    if not needle_lower:
        return input_text
    haystack_lower = input_text.lower()
    output: list[str] = []
    last_emitted = 0
    search_start = 0
    matched = False
    while True:
        start = haystack_lower.find(needle_lower, search_start)
        if start == -1:
            break
        end = start + len(needle_lower)
        boundary_before = start == 0 or not _is_word_byte(input_text[start - 1])
        boundary_after = end == len(input_text) or not _is_word_byte(input_text[end])
        if boundary_before and boundary_after:
            output.append(input_text[last_emitted:start])
            output.append(replacement)
            last_emitted = end
            matched = True
        search_start = start + 1
    if not matched:
        return input_text
    output.append(input_text[last_emitted:])
    return "".join(output)


def _is_word_byte(ch: str) -> bool:
    return ch.isascii() and (ch.isalnum() or ch == "_")


def _external_agent_config_dir() -> str:
    return f".{SOURCE_EXTERNAL_AGENT_NAME}"


def _external_agent_project_config_file() -> str:
    return f".{SOURCE_EXTERNAL_AGENT_NAME}.json"


def _external_agent_project_dir_env_var() -> str:
    return f"{SOURCE_EXTERNAL_AGENT_NAME.upper()}_PROJECT_DIR"


def _external_agent_doc_file_name() -> str:
    return f"{SOURCE_EXTERNAL_AGENT_NAME}.md"


def _external_agent_term_variants() -> tuple[str, ...]:
    return (
        f"{SOURCE_EXTERNAL_AGENT_NAME} code",
        f"{SOURCE_EXTERNAL_AGENT_NAME}-code",
        f"{SOURCE_EXTERNAL_AGENT_NAME}_code",
        f"{SOURCE_EXTERNAL_AGENT_NAME}code",
        SOURCE_EXTERNAL_AGENT_NAME,
    )


def _read_json_file(path: Path, message: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{message}: {exc}") from exc


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


__all__ = [
    "COMMAND_SKILL_PREFIX",
    "EXTERNAL_AGENT_HOOKS_SUBDIR",
    "EXTERNAL_AGENT_MCP_CONFIG_FILE",
    "EXTERNAL_AGENT_MIGRATED_HOOKS_SUBDIR",
    "MAX_SKILL_DESCRIPTION_LEN",
    "MAX_SKILL_NAME_LEN",
    "SOURCE_EXTERNAL_AGENT_NAME",
    "build_mcp_config_from_external",
    "count_missing_commands",
    "count_missing_subagents",
    "hook_migration_event_names",
    "hooks_migration_description",
    "import_commands",
    "import_hooks",
    "import_subagents",
    "missing_command_names",
    "missing_subagent_names",
    "rewrite_external_agent_terms",
]
