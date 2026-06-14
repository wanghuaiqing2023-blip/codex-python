"""Behavior port slice for Rust ``codex-tui::debug_config``.

Upstream source: ``codex/codex-rs/tui/src/debug_config.rs``.

The Rust module returns ratatui ``Line`` values wrapped in ``PlainHistoryCell``.
Python exposes the same user-visible text contract as a list of strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="debug_config", source="codex/codex-rs/tui/src/debug_config.rs")


class ConfigLayerSourceKind(str, Enum):
    MDM = "mdm"
    SYSTEM = "system"
    USER = "user"
    PROJECT = "project"
    SESSION_FLAGS = "session_flags"
    LEGACY_MANAGED_FILE = "legacy_managed_file"
    LEGACY_MANAGED_MDM = "legacy_managed_mdm"


@dataclass(frozen=True)
class ConfigLayerSource:
    kind: ConfigLayerSourceKind
    file: str | None = None
    dot_codex_folder: str | None = None
    domain: str | None = None
    key: str | None = None


@dataclass(frozen=True)
class ConfigLayerEntry:
    name: ConfigLayerSource
    config: Any = field(default_factory=dict)
    disabled_reason: str | None = None
    raw_toml_text: str | None = None

    def is_disabled(self) -> bool:
        return self.disabled_reason is not None

    def raw_toml(self) -> str | None:
        return self.raw_toml_text


@dataclass(frozen=True)
class ConfigLayerStack:
    layers: tuple[ConfigLayerEntry, ...] = ()
    requirements: Any = field(default_factory=dict)
    requirements_toml: Any = field(default_factory=dict)

    def get_layers(self, ordering: str = "lowest_precedence_first", include_disabled: bool = True) -> list[ConfigLayerEntry]:
        layers = list(self.layers)
        if not include_disabled:
            layers = [layer for layer in layers if not layer.is_disabled()]
        if ordering == "highest_precedence_first":
            layers.reverse()
        return layers


@dataclass(frozen=True)
class PlainHistoryCell:
    lines: tuple[str, ...]

    @classmethod
    def new(cls, lines: Iterable[str]) -> "PlainHistoryCell":
        return cls(tuple(lines))

    def text(self) -> str:
        return "\n".join(self.lines)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _as_bool_string(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def new_debug_config_output(config: Any, session_network_proxy: Any | None = None) -> PlainHistoryCell:
    stack = _get(config, "config_layer_stack", config)
    lines = render_debug_config_lines(stack)

    if session_network_proxy is not None:
        http_addr = _get(session_network_proxy, "http_addr")
        socks_addr = _get(session_network_proxy, "socks_addr")
        network = _get(_get(_get(config, "permissions", {}), "network", None), "socks_enabled", False)
        socks_enabled = network() if callable(network) else bool(network)
        lines.extend(
            [
                "",
                "Session runtime:",
                "  - network_proxy",
                f"    - HTTP_PROXY  = http://{http_addr}",
                f"    - ALL_PROXY   = {session_all_proxy_url(http_addr, socks_addr, socks_enabled)}",
            ]
        )

    return PlainHistoryCell.new(lines)


def session_all_proxy_url(http_addr: str, socks_addr: str, socks_enabled: bool) -> str:
    if socks_enabled:
        return f"socks5h://{socks_addr}"
    return f"http://{http_addr}"


def render_debug_config_lines(stack: ConfigLayerStack | Any) -> list[str]:
    lines = ["/debug-config", "", "Config layer stack (lowest precedence first):"]
    layers = _call_or_default(stack, "get_layers", [])
    if not layers:
        lines.append("  <none>")
    else:
        for index, layer in enumerate(layers, start=1):
            source = format_config_layer_source(_get(layer, "name"))
            status = "disabled" if _call_or_default(layer, "is_disabled", False) else "enabled"
            lines.append(f"  {index}. {source} ({status})")
            lines.extend(render_non_file_layer_details(layer))
            reason = _get(layer, "disabled_reason")
            if reason:
                lines.append(f"     reason: {reason}")

    requirements = _call_or_attr(stack, "requirements", {})
    requirements_toml = _call_or_attr(stack, "requirements_toml", {})
    lines.extend(["", "Requirements:"])
    requirement_lines = _render_requirement_lines(requirements, requirements_toml)
    lines.extend(requirement_lines or ["  <none>"])
    return lines


def _call_or_default(obj: Any, name: str, default: Any) -> Any:
    member = getattr(obj, name, None)
    if callable(member):
        try:
            return member("lowest_precedence_first", True)
        except TypeError:
            return member()
    return default


def _call_or_attr(obj: Any, name: str, default: Any) -> Any:
    member = getattr(obj, name, None)
    return member() if callable(member) else _get(obj, name, default)


def _render_requirement_lines(requirements: Any, requirements_toml: Any) -> list[str]:
    rows: list[str] = []
    specs = [
        ("allowed_approval_policies", "approval_policy"),
        ("allowed_approvals_reviewers", "approvals_reviewer"),
        ("allowed_sandbox_modes", "permission_profile"),
        ("allow_managed_hooks_only", "allow_managed_hooks_only"),
        ("allow_appshots", "allow_appshots"),
        ("enforce_residency", "enforce_residency"),
    ]
    for toml_key, requirement_key in specs:
        value = _get(requirements_toml, toml_key)
        if value is None:
            continue
        if toml_key == "allowed_sandbox_modes":
            rendered = join_or_empty([format_sandbox_mode_requirement(item) for item in value])
        elif toml_key == "allowed_approval_policies":
            rendered = join_or_empty([format_approval_policy(item) for item in value])
        elif toml_key == "allowed_approvals_reviewers":
            rendered = join_or_empty([format_approvals_reviewer(item) for item in value])
        elif toml_key == "enforce_residency":
            rendered = format_residency_requirement(value)
        elif isinstance(value, (list, tuple, set)):
            rendered = join_or_empty([str(item) for item in value])
        else:
            rendered = _as_bool_string(value)
        rows.append(requirement_line(toml_key, rendered, _source_for(requirements, requirement_key)))

    web_modes = _get(requirements_toml, "allowed_web_search_modes")
    if web_modes is not None:
        normalized = normalize_allowed_web_search_modes(list(web_modes))
        rows.append(
            requirement_line(
                "allowed_web_search_modes",
                join_or_empty([format_web_search_mode_requirement(item) for item in normalized]),
                _source_for(requirements, "web_search_mode"),
            )
        )

    if _get(requirements_toml, "guardian_policy_config") is not None:
        rows.append(requirement_line("guardian_policy_config", "configured", _get(requirements, "guardian_policy_config_source")))

    features = _get(requirements, "feature_requirements")
    feature_value = _get(_get(features, "value", features), "entries")
    if feature_value:
        rows.append(
            requirement_line(
                "features",
                join_or_empty([f"{key}={_as_bool_string(value)}" for key, value in sorted(dict(feature_value).items())]),
                _source_for(requirements, "feature_requirements"),
            )
        )

    hooks = _get(requirements_toml, "hooks")
    if hooks is not None:
        rows.append(requirement_line("hooks", format_managed_hooks_requirements(hooks), _source_for(requirements, "managed_hooks")))

    mcp_servers = _get(requirements_toml, "mcp_servers")
    if mcp_servers is not None:
        rows.append(requirement_line("mcp_servers", join_or_empty(list(dict(mcp_servers).keys())), _source_for(requirements, "mcp_servers")))

    if _get(requirements_toml, "rules") is not None:
        source = _call_or_attr(requirements, "exec_policy_source", None)
        rows.append(requirement_line("rules", "configured", source))

    network = _get(requirements, "network")
    if network is not None:
        rows.append(requirement_line("experimental_network", format_network_constraints(_get(network, "value", network)), _source_for(requirements, "network")))

    filesystem = _get(requirements, "filesystem")
    deny_read = _get(_get(filesystem, "value", filesystem), "deny_read")
    if deny_read is not None:
        rows.append(
            requirement_line(
                "permissions.filesystem.deny_read",
                join_or_empty([str(item) for item in deny_read]),
                _source_for(requirements, "filesystem"),
            )
        )
    return rows


def _source_for(requirements: Any, key: str) -> Any:
    item = _get(requirements, key)
    return _get(item, "source", item if key.endswith("_source") else None)


def render_non_file_layer_details(layer: ConfigLayerEntry | Any) -> list[str]:
    source = _get(layer, "name")
    kind = _source_kind(source)
    if kind is ConfigLayerSourceKind.SESSION_FLAGS:
        return render_session_flag_details(_get(layer, "config", {}))
    if kind in {ConfigLayerSourceKind.MDM, ConfigLayerSourceKind.LEGACY_MANAGED_MDM}:
        return render_mdm_layer_details(layer)
    return []


def render_session_flag_details(config: Any) -> list[str]:
    pairs: list[tuple[str, str]] = []
    flatten_toml_key_values(config, None, pairs)
    if not pairs:
        return ["     - <none>"]
    return [f"     - {key} = {value}" for key, value in pairs]


def format_managed_hooks_requirements(hooks: Any) -> str:
    parts = []
    managed_dir = _get(hooks, "managed_dir")
    windows_managed_dir = _get(hooks, "windows_managed_dir")
    if managed_dir is not None:
        parts.append(f"managed_dir={managed_dir}")
    if windows_managed_dir is not None:
        parts.append(f"windows_managed_dir={windows_managed_dir}")
    handler_count = _get(hooks, "handler_count")
    if callable(handler_count):
        count = handler_count()
    else:
        count = _get(hooks, "handlers", 0)
    parts.append(f"handlers={count}")
    return join_or_empty(parts)


def render_mdm_layer_details(layer: ConfigLayerEntry | Any) -> list[str]:
    raw = _call_or_attr(layer, "raw_toml", None)
    value = raw if raw is not None else format_toml_value(_get(layer, "config", {}))
    if value == "":
        return ["     MDM value: <empty>"]
    if "\n" in value:
        return ["     MDM value:"] + [f"       {line}" for line in value.splitlines()]
    return [f"     MDM value: {value}"]


def flatten_toml_key_values(value: Any, prefix: str | None, out: list[tuple[str, str]]) -> None:
    if isinstance(value, Mapping):
        for key in sorted(value):
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            flatten_toml_key_values(value[key], next_prefix, out)
        return
    key = prefix or "<value>"
    out.append((key, format_toml_value(value)))


def format_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(format_toml_value(item) for item in value) + "]"
    if isinstance(value, Mapping):
        return "\n".join(f"{key} = {format_toml_value(value[key])}" for key in sorted(value))
    return str(value)


def requirement_line(name: str, value: str, source: Any | None) -> str:
    rendered_source = format_requirement_source(source) if source is not None else "<unspecified>"
    return f"  - {name}: {value} (source: {rendered_source})"


def join_or_empty(values: Iterable[str]) -> str:
    values = list(values)
    return "<empty>" if not values else ", ".join(values)


def normalize_allowed_web_search_modes(modes: list[Any]) -> list[Any]:
    if not modes:
        return ["disabled"]
    if "disabled" not in [str(mode) for mode in modes]:
        return [*modes, "disabled"]
    return modes


def format_config_layer_source(source: Any) -> str:
    kind = _source_kind(source)
    if kind is ConfigLayerSourceKind.MDM:
        return f"MDM ({_get(source, 'domain')}:{_get(source, 'key')})"
    if kind is ConfigLayerSourceKind.SYSTEM:
        return f"system ({_get(source, 'file')})"
    if kind is ConfigLayerSourceKind.USER:
        return f"user ({_get(source, 'file')})"
    if kind is ConfigLayerSourceKind.PROJECT:
        return f"project ({_get(source, 'dot_codex_folder')}/config.toml)"
    if kind is ConfigLayerSourceKind.SESSION_FLAGS:
        return "session-flags"
    if kind is ConfigLayerSourceKind.LEGACY_MANAGED_FILE:
        return f"legacy managed_config.toml ({_get(source, 'file')})"
    if kind is ConfigLayerSourceKind.LEGACY_MANAGED_MDM:
        return "legacy managed_config.toml (MDM)"
    return str(source)


def _source_kind(source: Any) -> ConfigLayerSourceKind | None:
    kind = _get(source, "kind", source)
    if isinstance(kind, ConfigLayerSourceKind):
        return kind
    raw = str(kind)
    for candidate in ConfigLayerSourceKind:
        if raw in {candidate.value, candidate.name, candidate.name.lower()}:
            return candidate
    return None


def format_sandbox_mode_requirement(mode: Any) -> str:
    raw = str(mode)
    mapping = {
        "ReadOnly": "read-only",
        "read_only": "read-only",
        "WorkspaceWrite": "workspace-write",
        "workspace_write": "workspace-write",
        "DangerFullAccess": "danger-full-access",
        "danger_full_access": "danger-full-access",
        "ExternalSandbox": "external-sandbox",
        "external_sandbox": "external-sandbox",
    }
    return mapping.get(raw, raw)


def format_approval_policy(policy: Any) -> str:
    raw = str(policy)
    mapping = {
        "OnRequest": "on-request",
        "on_request": "on-request",
        "on-request": "on-request",
        "OnFailure": "on-failure",
        "on_failure": "on-failure",
        "on-failure": "on-failure",
        "UnlessTrusted": "unless-trusted",
        "unless_trusted": "unless-trusted",
        "unless-trusted": "unless-trusted",
        "Never": "never",
        "never": "never",
    }
    return mapping.get(raw, raw)


def format_approvals_reviewer(reviewer: Any) -> str:
    raw = str(reviewer)
    mapping = {
        "AutoReview": "guardian_subagent",
        "auto_review": "guardian_subagent",
        "guardian_subagent": "guardian_subagent",
    }
    return mapping.get(raw, raw)


def format_web_search_mode_requirement(mode: Any) -> str:
    raw = str(mode)
    mapping = {
        "Cached": "cached",
        "cached": "cached",
        "Enabled": "enabled",
        "enabled": "enabled",
        "Disabled": "disabled",
        "disabled": "disabled",
    }
    return mapping.get(raw, raw)


def format_requirement_source(source: Any) -> str:
    raw = str(source)
    mapping = {
        "CloudRequirements": "cloud requirements",
        "cloud_requirements": "cloud requirements",
        "cloud requirements": "cloud requirements",
        "LegacyManagedConfigTomlFromMdm": "MDM managed_config.toml (legacy)",
        "legacy_managed_config_toml_from_mdm": "MDM managed_config.toml (legacy)",
        "MDM managed_config.toml (legacy)": "MDM managed_config.toml (legacy)",
    }
    return mapping.get(raw, raw)


def format_residency_requirement(requirement: Any) -> str:
    return "us" if str(requirement).lower() in {"us", "residencyrequirement.us"} else str(requirement)


def format_network_constraints(network: Any) -> str:
    parts: list[str] = []
    for key in [
        "enabled",
        "http_port",
        "socks_port",
        "allow_upstream_proxy",
        "dangerously_allow_non_loopback_proxy",
        "dangerously_allow_all_unix_sockets",
    ]:
        value = _get(network, key)
        if value is not None:
            parts.append(f"{key}={_as_bool_string(value)}")
    domains = _get(network, "domains")
    if domains is not None:
        entries = _get(domains, "entries", domains)
        parts.append(f"domains={format_network_permission_entries(entries, format_network_domain_permission)}")
    value = _get(network, "managed_allowed_domains_only")
    if value is not None:
        parts.append(f"managed_allowed_domains_only={_as_bool_string(value)}")
    unix_sockets = _get(network, "unix_sockets")
    if unix_sockets is not None:
        entries = _get(unix_sockets, "entries", unix_sockets)
        parts.append(f"unix_sockets={format_network_permission_entries(entries, format_network_unix_socket_permission)}")
    value = _get(network, "allow_local_binding")
    if value is not None:
        parts.append(f"allow_local_binding={_as_bool_string(value)}")
    return join_or_empty(parts)


def format_network_permission_entries(entries: Mapping[str, Any], format_value: Callable[[Any], str]) -> str:
    parts = [f"{key}={format_value(entries[key])}" for key in sorted(entries)]
    return "{" + ", ".join(parts) + "}"


def format_network_domain_permission(permission: Any) -> str:
    return "allow" if str(permission).lower().endswith("allow") else "deny"


def format_network_unix_socket_permission(permission: Any) -> str:
    return "allow" if str(permission).lower().endswith("allow") else "none"


def empty_toml_table() -> dict[str, Any]:
    return {}


def absolute_path(path: str) -> str:
    return str(Path(path))


def render_to_text(lines: Iterable[str]) -> str:
    return "\n".join(str(line) for line in lines)


__all__ = [
    "ConfigLayerEntry",
    "ConfigLayerSource",
    "ConfigLayerSourceKind",
    "ConfigLayerStack",
    "PlainHistoryCell",
    "RUST_MODULE",
    "absolute_path",
    "empty_toml_table",
    "flatten_toml_key_values",
    "format_approval_policy",
    "format_approvals_reviewer",
    "format_config_layer_source",
    "format_managed_hooks_requirements",
    "format_network_constraints",
    "format_network_domain_permission",
    "format_network_permission_entries",
    "format_network_unix_socket_permission",
    "format_residency_requirement",
    "format_requirement_source",
    "format_sandbox_mode_requirement",
    "format_toml_value",
    "format_web_search_mode_requirement",
    "join_or_empty",
    "new_debug_config_output",
    "normalize_allowed_web_search_modes",
    "render_debug_config_lines",
    "render_mdm_layer_details",
    "render_non_file_layer_details",
    "render_session_flag_details",
    "render_to_text",
    "requirement_line",
    "session_all_proxy_url",
]
