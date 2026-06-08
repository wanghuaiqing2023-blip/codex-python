"""Source-verified public interface slice for ``codex-rmcp-client``.

Rust source:
- ``codex/codex-rs/rmcp-client/src/lib.rs``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class McpAuthStatus(str, Enum):
    UNKNOWN = "unknown"
    AUTHENTICATED = "authenticated"
    UNAUTHENTICATED = "unauthenticated"


@dataclass
class StreamableHttpOAuthDiscovery:
    authorization_url: str | None = None
    token_url: str | None = None
    scopes: list[str] = field(default_factory=list)


def supports_oauth_login(*_args: Any, **_kwargs: Any) -> bool:
    return False


async def determine_streamable_http_auth_status(*_args: Any, **_kwargs: Any) -> McpAuthStatus:
    return McpAuthStatus.UNKNOWN


async def discover_streamable_http_oauth(*_args: Any, **_kwargs: Any) -> StreamableHttpOAuthDiscovery | None:
    return None


@dataclass
class StoredOAuthTokens:
    access_token: str
    refresh_token: str | None = None


@dataclass
class WrappedOAuthTokenResponse:
    tokens: StoredOAuthTokens


def save_oauth_tokens(*_args: Any, **_kwargs: Any) -> None:
    return None


def delete_oauth_tokens(*_args: Any, **_kwargs: Any) -> None:
    return None


class OAuthProviderError(Exception):
    pass


@dataclass
class OauthLoginHandle:
    url: str | None = None


async def perform_oauth_login(*_args: Any, **_kwargs: Any) -> Any:
    raise OAuthProviderError("OAuth login runtime is not ported")


async def perform_oauth_login_return_url(*_args: Any, **_kwargs: Any) -> str:
    raise OAuthProviderError("OAuth login runtime is not ported")


async def perform_oauth_login_silent(*_args: Any, **_kwargs: Any) -> Any:
    raise OAuthProviderError("OAuth login runtime is not ported")


class ElicitationAction(str, Enum):
    ACCEPT = "accept"
    DECLINE = "decline"
    CANCEL = "cancel"


@dataclass
class Elicitation:
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class ElicitationResponse:
    action: ElicitationAction
    content: Any | None = None


@dataclass
class ToolWithConnectorId:
    tool: Any
    connector_id: str | None = None


@dataclass
class ListToolsWithConnectorIdResult:
    tools: list[ToolWithConnectorId] = field(default_factory=list)


class SendElicitation:
    pass


class RmcpClient:
    pass


class StdioServerLauncher:
    pass


class LocalStdioServerLauncher(StdioServerLauncher):
    pass


class ExecutorStdioServerLauncher(StdioServerLauncher):
    pass


class InProcessTransportFactory:
    pass


__all__ = [name for name in globals() if not name.startswith("_")]
