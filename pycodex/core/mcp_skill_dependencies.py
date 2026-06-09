"""MCP skill dependency helpers ported from ``core/src/mcp_skill_dependencies.rs``."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Mapping

from pycodex.core_skills.model import SkillMetadata, SkillToolDependency


DEFAULT_MCP_SERVER_ENVIRONMENT_ID = "local"
SKILL_MCP_DEPENDENCY_PROMPT_ID = "skill_mcp_dependency_install"
MCP_DEPENDENCY_OPTION_INSTALL = "Install"
MCP_DEPENDENCY_OPTION_SKIP = "Continue anyway"








@dataclass(frozen=True)
class McpServerTransportConfig:
    kind: str
    command: str | None = None
    args: tuple[str, ...] = ()
    env: Mapping[str, str] | None = None
    env_vars: tuple[str, ...] = ()
    cwd: str | None = None
    url: str | None = None
    bearer_token_env_var: str | None = None
    http_headers: Mapping[str, str] | None = None
    env_http_headers: Mapping[str, str] | None = None

    @classmethod
    def stdio(cls, command: str) -> "McpServerTransportConfig":
        return cls(kind="stdio", command=command)

    @classmethod
    def streamable_http(cls, url: str) -> "McpServerTransportConfig":
        return cls(kind="streamable_http", url=url)


@dataclass(frozen=True)
class McpServerConfig:
    transport: McpServerTransportConfig
    environment_id: str = DEFAULT_MCP_SERVER_ENVIRONMENT_ID
    enabled: bool = True
    required: bool = False
    supports_parallel_tool_calls: bool = False
    disabled_reason: str | None = None
    startup_timeout_sec: int | None = None
    tool_timeout_sec: int | None = None
    default_tools_approval_mode: str | None = None
    enabled_tools: tuple[str, ...] | None = None
    disabled_tools: tuple[str, ...] | None = None
    scopes: tuple[str, ...] | None = None
    oauth: object | None = None
    oauth_resource: str | None = None
    tools: Mapping[str, object] = field(default_factory=dict)


def format_missing_mcp_dependencies(missing: Mapping[str, McpServerConfig]) -> str:
    return ", ".join(sorted(missing.keys()))


def canonical_mcp_key(transport: str, identifier: str, fallback: str) -> str:
    identifier = identifier.strip()
    if not identifier:
        return fallback
    return f"mcp__{transport}__{identifier}"


def canonical_mcp_server_key(name: str, config: McpServerConfig) -> str:
    transport = config.transport
    if transport.kind == "stdio":
        return canonical_mcp_key("stdio", transport.command or "", name)
    if transport.kind == "streamable_http":
        return canonical_mcp_key("streamable_http", transport.url or "", name)
    return name


def canonical_mcp_dependency_key(dependency: SkillToolDependency) -> str:
    transport = dependency.transport or "streamable_http"
    if transport.lower() == "streamable_http":
        if dependency.url is None:
            raise ValueError("missing url for streamable_http dependency")
        return canonical_mcp_key("streamable_http", dependency.url, dependency.value)
    if transport.lower() == "stdio":
        if dependency.command is None:
            raise ValueError("missing command for stdio dependency")
        return canonical_mcp_key("stdio", dependency.command, dependency.value)
    raise ValueError(f"unsupported transport {transport}")


def mcp_dependency_to_server_config(dependency: SkillToolDependency) -> McpServerConfig:
    transport = dependency.transport or "streamable_http"
    if transport.lower() == "streamable_http":
        if dependency.url is None:
            raise ValueError("missing url for streamable_http dependency")
        return McpServerConfig(
            transport=McpServerTransportConfig.streamable_http(dependency.url),
        )
    if transport.lower() == "stdio":
        if dependency.command is None:
            raise ValueError("missing command for stdio dependency")
        return McpServerConfig(
            transport=McpServerTransportConfig.stdio(dependency.command),
        )
    raise ValueError(f"unsupported transport {transport}")


def collect_missing_mcp_dependencies(
    mentioned_skills: tuple[SkillMetadata, ...] | list[SkillMetadata],
    installed: Mapping[str, McpServerConfig],
) -> dict[str, McpServerConfig]:
    missing: dict[str, McpServerConfig] = {}
    installed_keys = {
        canonical_mcp_server_key(name, config)
        for name, config in installed.items()
    }
    seen_canonical_keys: set[str] = set()

    for skill in mentioned_skills:
        dependencies = skill.dependencies
        if dependencies is None:
            continue
        for tool in dependencies.tools:
            if tool.type.lower() != "mcp":
                continue
            try:
                dependency_key = canonical_mcp_dependency_key(tool)
            except ValueError:
                continue
            if dependency_key in installed_keys or dependency_key in seen_canonical_keys:
                continue
            try:
                config = mcp_dependency_to_server_config(tool)
            except ValueError:
                continue
            missing[tool.value] = config
            seen_canonical_keys.add(dependency_key)
    return missing


def filter_prompted_mcp_dependencies(
    missing: Mapping[str, McpServerConfig],
    prompted: set[str] | frozenset[str],
) -> dict[str, McpServerConfig]:
    if not prompted:
        return dict(missing)
    return {
        name: config
        for name, config in missing.items()
        if canonical_mcp_server_key(name, config) not in prompted
    }


async def maybe_prompt_and_install_mcp_dependencies(
    sess: object,
    turn_context: object,
    cancellation_token: object,
    mentioned_skills: tuple[SkillMetadata, ...] | list[SkillMetadata],
    elicitation_reviewer: object | None = None,
) -> None:
    """Prompt once and install MCP dependencies for mentioned skills.

    Rust source:
    ``codex-rs/core/src/mcp_skill_dependencies.rs::maybe_prompt_and_install_mcp_dependencies``.
    The concrete config persistence, OAuth, and MCP refresh operations are
    delegated to session/service facades; this module owns the orchestration
    and dependency decisions.
    """

    if not _is_first_party_session(sess, turn_context):
        return
    config = _turn_config(turn_context)
    if not mentioned_skills or not _feature_enabled(config, "SkillMcpDependencyInstall"):
        return

    installed = await _configured_servers(sess, config)
    missing = collect_missing_mcp_dependencies(mentioned_skills, installed)
    if not missing:
        return

    unprompted_missing = await filter_prompted_mcp_dependencies_for_session(sess, missing)
    if not unprompted_missing:
        return

    should_install = await should_install_mcp_dependencies(
        sess,
        turn_context,
        unprompted_missing,
        cancellation_token,
    )
    if should_install:
        await maybe_install_mcp_dependencies(
            sess,
            turn_context,
            config,
            mentioned_skills,
            elicitation_reviewer,
        )


async def maybe_install_mcp_dependencies(
    sess: object,
    turn_context: object,
    config: object,
    mentioned_skills: tuple[SkillMetadata, ...] | list[SkillMetadata],
    elicitation_reviewer: object | None = None,
) -> None:
    """Install missing skill MCP dependencies into global config and refresh MCP."""

    if not mentioned_skills or not _feature_enabled(config, "SkillMcpDependencyInstall"):
        return

    installed = await _configured_servers(sess, config)
    missing = collect_missing_mcp_dependencies(mentioned_skills, installed)
    if not missing:
        return

    servers = await _load_global_mcp_servers(sess, config)
    updated = False
    added: list[tuple[str, McpServerConfig]] = []
    for name, server_config in missing.items():
        if name in servers:
            continue
        servers[name] = server_config
        added.append((name, server_config))
        updated = True

    if not updated:
        return

    persisted = await _persist_global_mcp_servers(sess, config, servers)
    if not persisted:
        return

    for name, server_config in added:
        await _maybe_oauth_login_for_dependency(sess, config, name, server_config)

    refresh_servers = dict(await _configured_servers(sess, config))
    for name, server_config in servers.items():
        refresh_servers.setdefault(name, server_config)
    refresh = getattr(sess, "refresh_mcp_servers_now", None)
    if callable(refresh):
        await _maybe_await(
            refresh(
                turn_context,
                refresh_servers,
                _get_field(config, "mcp_oauth_credentials_store_mode", None),
                elicitation_reviewer,
            )
        )


async def should_install_mcp_dependencies(
    sess: object,
    turn_context: object,
    missing: Mapping[str, McpServerConfig],
    cancellation_token: object | None = None,
) -> bool:
    """Return whether the missing dependencies should be installed."""

    if _mcp_prompt_auto_approved(turn_context):
        return True

    server_list = format_missing_mcp_dependencies(missing)
    question = {
        "id": SKILL_MCP_DEPENDENCY_PROMPT_ID,
        "header": "Install MCP servers?",
        "question": (
            "The following MCP servers are required by the selected skills but are not "
            f"installed yet: {server_list}. Install them now?"
        ),
        "is_other": False,
        "is_secret": False,
        "options": [
            {
                "label": MCP_DEPENDENCY_OPTION_INSTALL,
                "description": "Install and enable the missing MCP servers in your global config.",
            },
            {
                "label": MCP_DEPENDENCY_OPTION_SKIP,
                "description": (
                    "Skip installation for now and do not show again for these MCP servers "
                    "in this session."
                ),
            },
        ],
    }
    args = {"questions": [question]}
    sub_id = str(_get_field(turn_context, "sub_id", ""))
    call_id = f"mcp-deps-{sub_id}"
    request_user_input = getattr(sess, "request_user_input", None)
    if callable(request_user_input) and not _cancellation_token_is_cancelled(cancellation_token):
        response = await _maybe_await(request_user_input(turn_context, call_id, args))
    else:
        response = {"answers": {}}
        notify = getattr(sess, "notify_user_input_response", None)
        if callable(notify) and sub_id:
            await _maybe_await(notify(sub_id, response))

    answers = _get_field(response, "answers", {}) or {}
    answer = answers.get(SKILL_MCP_DEPENDENCY_PROMPT_ID) if isinstance(answers, Mapping) else None
    selected = _answer_values(answer)
    install = MCP_DEPENDENCY_OPTION_INSTALL in selected

    prompted_keys = [
        canonical_mcp_server_key(name, server_config)
        for name, server_config in missing.items()
    ]
    record = getattr(sess, "record_mcp_dependency_prompted", None)
    if callable(record):
        await _maybe_await(record(prompted_keys))

    return install


async def filter_prompted_mcp_dependencies_for_session(
    sess: object,
    missing: Mapping[str, McpServerConfig],
) -> dict[str, McpServerConfig]:
    prompted_fn = getattr(sess, "mcp_dependency_prompted", None)
    if not callable(prompted_fn):
        return dict(missing)
    prompted = await _maybe_await(prompted_fn())
    return filter_prompted_mcp_dependencies(missing, set(prompted or ()))


def _is_first_party_session(sess: object, turn_context: object) -> bool:
    for source in (sess, turn_context, _turn_config(turn_context)):
        originator = _get_field(source, "originator", None)
        if originator is not None:
            return str(originator) in {"codex", "openai", "chatgpt", "first_party"}
    return True


def _turn_config(turn_context: object) -> object:
    return _get_field(turn_context, "config", turn_context)


def _feature_enabled(config: object, feature_name: str) -> bool:
    features = _get_field(config, "features", None)
    enabled = getattr(features, "enabled", None)
    if callable(enabled):
        return bool(enabled(feature_name))
    if isinstance(features, Mapping):
        return bool(features.get(feature_name, features.get("skill_mcp_dependency_install", False)))
    return bool(_get_field(config, "skill_mcp_dependency_install", True))


async def _configured_servers(sess: object, config: object) -> dict[str, McpServerConfig]:
    services = _get_field(sess, "services", None)
    manager = _get_field(services, "mcp_manager", None)
    configured = getattr(manager, "configured_servers", None)
    if callable(configured):
        return dict(await _maybe_await(configured(config)))
    return dict(_get_field(config, "mcp_servers", {}) or {})


async def _load_global_mcp_servers(sess: object, config: object) -> dict[str, McpServerConfig]:
    loader = getattr(sess, "load_global_mcp_servers", None) or getattr(config, "load_global_mcp_servers", None)
    if callable(loader):
        return dict(await _maybe_await(loader()))
    return dict(_get_field(config, "global_mcp_servers", {}) or {})


async def _persist_global_mcp_servers(
    sess: object,
    config: object,
    servers: Mapping[str, McpServerConfig],
) -> bool:
    for target in (sess, config):
        persist = getattr(target, "replace_mcp_servers", None) or getattr(target, "persist_global_mcp_servers", None)
        if callable(persist):
            await _maybe_await(persist(dict(servers)))
            return True
    existing = _get_field(config, "global_mcp_servers", None)
    if isinstance(existing, dict):
        existing.clear()
        existing.update(servers)
        return True
    return False


async def _maybe_oauth_login_for_dependency(
    sess: object,
    config: object,
    name: str,
    server_config: McpServerConfig,
) -> None:
    oauth = getattr(sess, "oauth_login_for_mcp_dependency", None) or getattr(config, "oauth_login_for_mcp_dependency", None)
    if callable(oauth):
        await _maybe_await(oauth(name, server_config))


def _mcp_prompt_auto_approved(turn_context: object) -> bool:
    value = _get_field(turn_context, "mcp_permission_prompt_auto_approved", None)
    if value is not None:
        return bool(value() if callable(value) else value)
    approval_policy = str(_get_field(turn_context, "approval_policy", "")).lower()
    return approval_policy in {"never", "auto", "trusted"}


def _answer_values(answer: object) -> set[str]:
    if answer is None:
        return set()
    if isinstance(answer, str):
        return {answer}
    values = _get_field(answer, "answers", None)
    if values is None and isinstance(answer, Mapping):
        values = answer.get("answers")
    if isinstance(values, str):
        return {values}
    if values is None:
        return set()
    return {str(value) for value in values}


def _cancellation_token_is_cancelled(token: object | None) -> bool:
    if token is None:
        return False
    for name in ("is_cancelled", "is_set", "cancelled"):
        value = getattr(token, name, None)
        if callable(value):
            return bool(value())
        if value is not None:
            return bool(value)
    return bool(token)


def _get_field(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


async def _maybe_await(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "DEFAULT_MCP_SERVER_ENVIRONMENT_ID",
    "MCP_DEPENDENCY_OPTION_INSTALL",
    "MCP_DEPENDENCY_OPTION_SKIP",
    "SKILL_MCP_DEPENDENCY_PROMPT_ID",
    "McpServerConfig",
    "McpServerTransportConfig",
    "canonical_mcp_dependency_key",
    "canonical_mcp_key",
    "canonical_mcp_server_key",
    "collect_missing_mcp_dependencies",
    "filter_prompted_mcp_dependencies",
    "filter_prompted_mcp_dependencies_for_session",
    "format_missing_mcp_dependencies",
    "maybe_install_mcp_dependencies",
    "maybe_prompt_and_install_mcp_dependencies",
    "mcp_dependency_to_server_config",
    "should_install_mcp_dependencies",
]
