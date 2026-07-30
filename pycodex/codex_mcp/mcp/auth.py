"""OAuth status and scope resolution from ``codex-mcp/src/mcp/auth.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from pycodex.config.mcp_types import McpServerConfig, McpServerTransportConfig
@dataclass(frozen=True)
class McpOAuthLoginConfig:
    url: str
    http_headers: Mapping[str, str] | None = None
    env_http_headers: Mapping[str, str] | None = None
    discovered_scopes: tuple[str, ...] | None = None


class McpOAuthLoginSupportKind(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class McpOAuthLoginSupport:
    kind: McpOAuthLoginSupportKind
    config: McpOAuthLoginConfig | None = None
    error: Exception | None = None

    @classmethod
    def supported(cls, config: McpOAuthLoginConfig) -> "McpOAuthLoginSupport":
        return cls(McpOAuthLoginSupportKind.SUPPORTED, config=config)

    @classmethod
    def unsupported(cls) -> "McpOAuthLoginSupport":
        return cls(McpOAuthLoginSupportKind.UNSUPPORTED)

    @classmethod
    def unknown(cls, error: Exception) -> "McpOAuthLoginSupport":
        return cls(McpOAuthLoginSupportKind.UNKNOWN, error=error)


class McpOAuthScopesSource(str, Enum):
    EXPLICIT = "explicit"
    CONFIGURED = "configured"
    DISCOVERED = "discovered"
    EMPTY = "empty"


@dataclass(frozen=True)
class ResolvedMcpOAuthScopes:
    scopes: tuple[str, ...]
    source: McpOAuthScopesSource


@dataclass(frozen=True)
class McpAuthStatusEntry:
    config: McpServerConfig | None
    auth_status: Any


async def oauth_login_support(
    transport: McpServerTransportConfig,
) -> McpOAuthLoginSupport:
    from pycodex.rmcp_client import discover_streamable_http_oauth

    if transport.kind != "streamable_http" or transport.bearer_token_env_var is not None:
        return McpOAuthLoginSupport.unsupported()
    try:
        discovery = await discover_streamable_http_oauth(
            transport.url or "",
            transport.http_headers,
            transport.env_http_headers,
        )
    except Exception as exc:
        return McpOAuthLoginSupport.unknown(exc)
    if discovery is None:
        return McpOAuthLoginSupport.unsupported()
    scopes = getattr(discovery, "scopes_supported", None)
    return McpOAuthLoginSupport.supported(
        McpOAuthLoginConfig(
            transport.url or "",
            transport.http_headers,
            transport.env_http_headers,
            tuple(scopes) if scopes is not None else None,
        )
    )


async def discover_supported_scopes(
    transport: McpServerTransportConfig,
) -> tuple[str, ...] | None:
    support = await oauth_login_support(transport)
    return support.config.discovered_scopes if support.config is not None else None


def resolve_oauth_scopes(
    explicit_scopes: Iterable[str] | None,
    configured_scopes: Iterable[str] | None = None,
    discovered_scopes: Iterable[str] | None = None,
) -> ResolvedMcpOAuthScopes:
    if explicit_scopes is not None:
        return ResolvedMcpOAuthScopes(
            tuple(explicit_scopes),
            McpOAuthScopesSource.EXPLICIT,
        )
    if configured_scopes is not None:
        return ResolvedMcpOAuthScopes(
            tuple(configured_scopes),
            McpOAuthScopesSource.CONFIGURED,
        )
    discovered = tuple(discovered_scopes or ())
    if discovered:
        return ResolvedMcpOAuthScopes(discovered, McpOAuthScopesSource.DISCOVERED)
    return ResolvedMcpOAuthScopes((), McpOAuthScopesSource.EMPTY)


def should_retry_without_scopes(
    scopes: ResolvedMcpOAuthScopes,
    error: BaseException,
) -> bool:
    from pycodex.rmcp_client import OAuthProviderError

    return (
        scopes.source is McpOAuthScopesSource.DISCOVERED
        and isinstance(error, OAuthProviderError)
    )


async def compute_auth_statuses(
    servers: Iterable[tuple[str, Any]],
    store_mode: Any,
    auth: Any | None,
) -> dict[str, McpAuthStatusEntry]:
    from pycodex.rmcp_client import determine_streamable_http_auth_status

    entries: dict[str, McpAuthStatusEntry] = {}
    for name, server in servers:
        config = server.configured_config()
        status: Any = "unsupported"
        if config.enabled and config.transport.kind == "streamable_http":
            runtime_auth = (
                name == "codex_apps"
                and _uses_codex_backend(auth)
                and config.transport.bearer_token_env_var is None
            )
            if runtime_auth:
                status = "bearer_token"
            else:
                try:
                    status = await determine_streamable_http_auth_status(
                        name,
                        config.transport.url or "",
                        config.transport.bearer_token_env_var,
                        config.transport.http_headers,
                        config.transport.env_http_headers,
                        store_mode,
                    )
                except Exception:
                    status = "unsupported"
        entries[name] = McpAuthStatusEntry(config, status)
    return entries


def _uses_codex_backend(auth: Any | None) -> bool:
    if auth is None:
        return False
    value = getattr(auth, "uses_codex_backend", False)
    return bool(value() if callable(value) else value)


__all__ = [
    "McpAuthStatusEntry",
    "McpOAuthLoginConfig",
    "McpOAuthLoginSupport",
    "McpOAuthLoginSupportKind",
    "McpOAuthScopesSource",
    "ResolvedMcpOAuthScopes",
    "compute_auth_statuses",
    "discover_supported_scopes",
    "oauth_login_support",
    "resolve_oauth_scopes",
    "should_retry_without_scopes",
]
