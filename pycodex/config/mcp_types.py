"""MCP server configuration types ported from ``codex-config``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from . import toml_compat as _toml
from .constraint import RequirementSource


DEFAULT_MCP_SERVER_ENVIRONMENT_ID = "local"


class AppToolApproval(str, Enum):
    AUTO = "auto"
    PROMPT = "prompt"
    APPROVE = "approve"

    @classmethod
    def from_value(cls, value: object) -> "AppToolApproval":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError as exc:
                raise ValueError(f"unsupported app tool approval mode: {value}") from exc
        raise TypeError("app tool approval mode must be a string")


@dataclass(frozen=True)
class McpServerDisabledReason:
    kind: str
    source: RequirementSource | None = None

    @classmethod
    def unknown(cls) -> "McpServerDisabledReason":
        return cls("unknown")

    @classmethod
    def requirements(cls, source: RequirementSource) -> "McpServerDisabledReason":
        return cls("requirements", source=source)

    def __str__(self) -> str:
        if self.kind == "unknown":
            return "unknown"
        if self.kind == "requirements" and self.source is not None:
            return f"requirements ({self.source})"
        return self.kind


@dataclass(frozen=True)
class McpServerToolConfig:
    approval_mode: AppToolApproval | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "McpServerToolConfig":
        unknown = set(value) - {"approval_mode"}
        if unknown:
            raise ValueError(f"unknown tool config field: {sorted(unknown)[0]}")
        approval = value.get("approval_mode")
        return cls(
            approval_mode=AppToolApproval.from_value(approval) if approval is not None else None,
        )

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.approval_mode is not None:
            result["approval_mode"] = self.approval_mode.value
        return result


@dataclass(frozen=True)
class McpServerEnvVar:
    name_value: str
    source_value: str | None = None

    @classmethod
    def from_value(cls, value: object) -> "McpServerEnvVar":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(value)
        if isinstance(value, Mapping):
            unknown = set(value) - {"name", "source"}
            if unknown:
                raise ValueError(f"unknown env_vars field: {sorted(unknown)[0]}")
            name = value.get("name")
            if not isinstance(name, str):
                raise TypeError("env_vars config requires string field `name`")
            source = value.get("source")
            if source is not None and not isinstance(source, str):
                raise TypeError("env_vars config field `source` must be a string")
            env_var = cls(name, source)
            env_var.validate_source()
            return env_var
        raise TypeError("env_vars entries must be strings or tables")

    def name(self) -> str:
        return self.name_value

    def source(self) -> str | None:
        return self.source_value

    def is_remote_source(self) -> bool:
        return self.source_value == "remote"

    def validate_source(self) -> None:
        if self.source_value in {None, "local", "remote"}:
            return
        raise ValueError(
            f"unsupported env_vars source `{self.source_value}`; expected `local` or `remote`"
        )

    def to_value(self) -> str | dict[str, str]:
        if self.source_value is None:
            return self.name_value
        return {"name": self.name_value, "source": self.source_value}


@dataclass(frozen=True)
class McpServerOAuthConfig:
    client_id: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "McpServerOAuthConfig":
        unknown = set(value) - {"client_id"}
        if unknown:
            raise ValueError(f"unknown oauth field: {sorted(unknown)[0]}")
        client_id = value.get("client_id")
        if client_id is not None and not isinstance(client_id, str):
            raise TypeError("oauth.client_id must be a string")
        return cls(client_id=client_id)

    def to_mapping(self) -> dict[str, Any]:
        return {"client_id": self.client_id} if self.client_id is not None else {}


@dataclass(frozen=True)
class McpServerTransportConfig:
    kind: str
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] | None = None
    env_vars: tuple[McpServerEnvVar, ...] = ()
    cwd: Path | None = None
    url: str | None = None
    bearer_token_env_var: str | None = None
    http_headers: dict[str, str] | None = None
    env_http_headers: dict[str, str] | None = None

    @classmethod
    def stdio(
        cls,
        *,
        command: str,
        args: tuple[str, ...] = (),
        env: Mapping[str, str] | None = None,
        env_vars: tuple[McpServerEnvVar, ...] = (),
        cwd: Path | str | None = None,
    ) -> "McpServerTransportConfig":
        return cls(
            kind="stdio",
            command=command,
            args=args,
            env=dict(env) if env is not None else None,
            env_vars=env_vars,
            cwd=Path(cwd) if cwd is not None else None,
        )

    @classmethod
    def streamable_http(
        cls,
        *,
        url: str,
        bearer_token_env_var: str | None = None,
        http_headers: Mapping[str, str] | None = None,
        env_http_headers: Mapping[str, str] | None = None,
    ) -> "McpServerTransportConfig":
        return cls(
            kind="streamable_http",
            url=url,
            bearer_token_env_var=bearer_token_env_var,
            http_headers=dict(http_headers) if http_headers is not None else None,
            env_http_headers=dict(env_http_headers) if env_http_headers is not None else None,
        )

    def to_mapping(self) -> dict[str, Any]:
        if self.kind == "stdio":
            result: dict[str, Any] = {"command": self.command, "args": list(self.args)}
            if self.env is not None:
                result["env"] = dict(self.env)
            if self.env_vars:
                result["env_vars"] = [env_var.to_value() for env_var in self.env_vars]
            if self.cwd is not None:
                result["cwd"] = str(self.cwd)
            return result

        result = {"url": self.url}
        if self.bearer_token_env_var is not None:
            result["bearer_token_env_var"] = self.bearer_token_env_var
        if self.http_headers is not None:
            result["http_headers"] = dict(self.http_headers)
        if self.env_http_headers is not None:
            result["env_http_headers"] = dict(self.env_http_headers)
        return result


@dataclass(frozen=True)
class McpServerConfig:
    transport: McpServerTransportConfig
    environment_id: str = DEFAULT_MCP_SERVER_ENVIRONMENT_ID
    enabled: bool = True
    required: bool = False
    supports_parallel_tool_calls: bool = False
    disabled_reason: McpServerDisabledReason | None = None
    startup_timeout_sec: float | None = None
    tool_timeout_sec: float | None = None
    default_tools_approval_mode: AppToolApproval | None = None
    enabled_tools: tuple[str, ...] | None = None
    disabled_tools: tuple[str, ...] | None = None
    scopes: tuple[str, ...] | None = None
    oauth: McpServerOAuthConfig | None = None
    oauth_resource: str | None = None
    tools: dict[str, McpServerToolConfig] = field(default_factory=dict)

    @classmethod
    def from_toml(cls, contents: str) -> "McpServerConfig":
        data = _toml.loads(contents)
        if not isinstance(data, Mapping):
            raise TypeError("MCP server TOML must be a table")
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "McpServerConfig":
        startup_timeout_sec = _duration_from_raw(data)
        environment_id = _optional_str(data, "environment_id") or DEFAULT_MCP_SERVER_ENVIRONMENT_ID
        oauth = _oauth_from_raw(data)

        if _present(data, "command"):
            transport = _stdio_transport(data, oauth=oauth)
        elif _present(data, "url"):
            transport = _http_transport(data)
        else:
            raise ValueError("invalid transport")

        _validate_remote_stdio_cwd(transport, environment_id)

        return cls(
            transport=transport,
            environment_id=environment_id,
            startup_timeout_sec=startup_timeout_sec,
            tool_timeout_sec=_optional_float(data, "tool_timeout_sec"),
            enabled=bool(data.get("enabled", True)),
            required=bool(data.get("required", False)),
            supports_parallel_tool_calls=bool(data.get("supports_parallel_tool_calls", False)),
            default_tools_approval_mode=_approval_or_none(data.get("default_tools_approval_mode")),
            enabled_tools=_optional_str_tuple(data, "enabled_tools"),
            disabled_tools=_optional_str_tuple(data, "disabled_tools"),
            scopes=_optional_str_tuple(data, "scopes"),
            oauth=oauth,
            oauth_resource=_optional_str(data, "oauth_resource"),
            tools=_tools_from_raw(data.get("tools")),
        )

    def is_local_environment(self) -> bool:
        return self.environment_id == DEFAULT_MCP_SERVER_ENVIRONMENT_ID

    def oauth_client_id(self) -> str | None:
        return self.oauth.client_id if self.oauth is not None else None

    def to_mapping(self) -> dict[str, Any]:
        result = self.transport.to_mapping()
        result["environment_id"] = self.environment_id
        result["enabled"] = self.enabled
        if self.required:
            result["required"] = self.required
        if self.supports_parallel_tool_calls:
            result["supports_parallel_tool_calls"] = self.supports_parallel_tool_calls
        if self.startup_timeout_sec is not None:
            result["startup_timeout_sec"] = self.startup_timeout_sec
        if self.tool_timeout_sec is not None:
            result["tool_timeout_sec"] = self.tool_timeout_sec
        if self.default_tools_approval_mode is not None:
            result["default_tools_approval_mode"] = self.default_tools_approval_mode.value
        if self.enabled_tools is not None:
            result["enabled_tools"] = list(self.enabled_tools)
        if self.disabled_tools is not None:
            result["disabled_tools"] = list(self.disabled_tools)
        if self.scopes is not None:
            result["scopes"] = list(self.scopes)
        if self.oauth is not None:
            result["oauth"] = self.oauth.to_mapping()
        if self.oauth_resource is not None:
            result["oauth_resource"] = self.oauth_resource
        if self.tools:
            result["tools"] = {name: cfg.to_mapping() for name, cfg in self.tools.items()}
        return result


def _present(data: Mapping[str, Any], key: str) -> bool:
    return key in data and data[key] is not None


def _throw_if_set(data: Mapping[str, Any], transport: str, field_name: str) -> None:
    if _present(data, field_name):
        raise ValueError(f"{field_name} is not supported for {transport}")


def _stdio_transport(data: Mapping[str, Any], *, oauth: McpServerOAuthConfig | None) -> McpServerTransportConfig:
    for field_name in (
        "url",
        "bearer_token_env_var",
        "bearer_token",
        "http_headers",
        "env_http_headers",
        "oauth_resource",
    ):
        _throw_if_set(data, "stdio", field_name)
    if oauth is not None:
        raise ValueError("oauth is not supported for stdio")

    command = _required_str(data, "command")
    env_vars = tuple(McpServerEnvVar.from_value(value) for value in data.get("env_vars", []))
    for env_var in env_vars:
        env_var.validate_source()
    return McpServerTransportConfig.stdio(
        command=command,
        args=_str_tuple(data.get("args", []), "args"),
        env=_optional_str_mapping(data, "env"),
        env_vars=env_vars,
        cwd=_optional_str(data, "cwd"),
    )


def _http_transport(data: Mapping[str, Any]) -> McpServerTransportConfig:
    for field_name in ("args", "env", "env_vars", "cwd", "bearer_token"):
        _throw_if_set(data, "streamable_http", field_name)
    return McpServerTransportConfig.streamable_http(
        url=_required_str(data, "url"),
        bearer_token_env_var=_optional_str(data, "bearer_token_env_var"),
        http_headers=_optional_str_mapping(data, "http_headers"),
        env_http_headers=_optional_str_mapping(data, "env_http_headers"),
    )


def _validate_remote_stdio_cwd(transport: McpServerTransportConfig, environment_id: str) -> None:
    if environment_id == DEFAULT_MCP_SERVER_ENVIRONMENT_ID or transport.kind != "stdio":
        return
    if transport.cwd is None:
        raise ValueError(
            "remote stdio MCP servers require an absolute cwd "
            f"when environment_id is `{environment_id}`"
        )
    if transport.cwd.is_absolute():
        return
    raise ValueError(
        "remote stdio MCP servers require an absolute cwd "
        f"when environment_id is `{environment_id}`, got `{transport.cwd}`"
    )


def _duration_from_raw(data: Mapping[str, Any]) -> float | None:
    if _present(data, "startup_timeout_sec"):
        return _duration_seconds(data["startup_timeout_sec"])
    if _present(data, "startup_timeout_ms"):
        millis = data["startup_timeout_ms"]
        if not isinstance(millis, int) or isinstance(millis, bool):
            raise TypeError("startup_timeout_ms must be an integer")
        if millis < 0:
            raise ValueError("startup_timeout_ms must be non-negative")
        return millis / 1000.0
    return None


def _duration_seconds(value: object) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError("duration must be numeric")
    seconds = float(value)
    if seconds < 0:
        raise ValueError("duration must be non-negative")
    return seconds


def _oauth_from_raw(data: Mapping[str, Any]) -> McpServerOAuthConfig | None:
    oauth = data.get("oauth")
    if oauth is None:
        return None
    if not isinstance(oauth, Mapping):
        raise TypeError("oauth must be a table")
    return McpServerOAuthConfig.from_mapping(oauth)


def _tools_from_raw(value: object) -> dict[str, McpServerToolConfig]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("tools must be a table")
    tools: dict[str, McpServerToolConfig] = {}
    for name, config in value.items():
        if not isinstance(name, str):
            raise TypeError("tool names must be strings")
        if not isinstance(config, Mapping):
            raise TypeError("tool config must be a table")
        tools[name] = McpServerToolConfig.from_mapping(config)
    return tools


def _approval_or_none(value: object) -> AppToolApproval | None:
    return AppToolApproval.from_value(value) if value is not None else None


def _optional_str(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _required_str(data: Mapping[str, Any], key: str) -> str:
    value = _optional_str(data, key)
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def _optional_float(data: Mapping[str, Any], key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    return _duration_seconds(value)


def _str_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise TypeError(f"{field_name} must be an array")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} entries must be strings")
    return tuple(value)


def _optional_str_tuple(data: Mapping[str, Any], key: str) -> tuple[str, ...] | None:
    value = data.get(key)
    if value is None:
        return None
    return _str_tuple(value, key)


def _optional_str_mapping(data: Mapping[str, Any], key: str) -> dict[str, str] | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be a table")
    result: dict[str, str] = {}
    for item_key, item_value in value.items():
        if not isinstance(item_key, str) or not isinstance(item_value, str):
            raise TypeError(f"{key} must map strings to strings")
        result[item_key] = item_value
    return result


__all__ = [
    "AppToolApproval",
    "DEFAULT_MCP_SERVER_ENVIRONMENT_ID",
    "McpServerConfig",
    "McpServerDisabledReason",
    "McpServerEnvVar",
    "McpServerOAuthConfig",
    "McpServerToolConfig",
    "McpServerTransportConfig",
]
