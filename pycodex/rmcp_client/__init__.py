"""Source-verified public interface slice for ``codex-rmcp-client``.

Rust source:
- ``codex/codex-rs/rmcp-client/src/lib.rs``
- ``codex/codex-rs/core/tests/suite/rmcp_client.rs``
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.protocol import CallToolResult, McpInvocation, McpToolCallBeginEvent, McpToolCallEndEvent


class McpAuthStatus(str, Enum):
    UNKNOWN = "unknown"
    AUTHENTICATED = "authenticated"
    UNAUTHENTICATED = "unauthenticated"


@dataclass
class StreamableHttpOAuthDiscovery:
    authorization_url: str | None = None
    token_url: str | None = None
    scopes: list[str] = field(default_factory=list)


MCP_SANDBOX_STATE_META_CAPABILITY = "codex/sandbox-state"
REMOTE_MCP_ENVIRONMENT = "remote"
DEFAULT_MCP_SERVER_ENVIRONMENT_ID = "local"
REMOTE_EXEC_SERVER_URL_ENV_VAR = "CODEX_TEST_REMOTE_EXEC_SERVER_URL"
STREAMABLE_HTTP_METADATA_PATH = "/.well-known/oauth-authorization-server/mcp"
TEXT_ONLY_IMAGE_OMISSION_TEXT = "<image content omitted because you do not support image input>"

_OAUTH_TOKEN_STORE: dict[tuple[str, str], "StoredOAuthTokens"] = {}


def supports_oauth_login(*_args: Any, **_kwargs: Any) -> bool:
    return False


async def determine_streamable_http_auth_status(
    server_name: str | None = None,
    server_url: str | None = None,
    **_kwargs: Any,
) -> McpAuthStatus:
    if server_name is None or server_url is None:
        return McpAuthStatus.UNKNOWN
    return McpAuthStatus.AUTHENTICATED if load_oauth_tokens(server_name, server_url) is not None else McpAuthStatus.UNAUTHENTICATED


async def discover_streamable_http_oauth(*_args: Any, **_kwargs: Any) -> StreamableHttpOAuthDiscovery | None:
    return None


@dataclass
class StoredOAuthTokens:
    access_token: str
    refresh_token: str | None = None


@dataclass
class WrappedOAuthTokenResponse:
    tokens: StoredOAuthTokens


def mcp_namespace(server_name: str) -> str:
    if not isinstance(server_name, str) or not server_name:
        raise ValueError("server_name must be a non-empty string")
    return f"mcp__{server_name}"


def streamable_http_metadata_url(server_url: str) -> str:
    return f"{str(server_url).removesuffix('/mcp')}{STREAMABLE_HTTP_METADATA_PATH}"


def remote_aware_environment_id(env: dict[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    return REMOTE_MCP_ENVIRONMENT if source.get("CODEX_TEST_REMOTE_ENV") else DEFAULT_MCP_SERVER_ENVIRONMENT_ID


def select_stdio_cwd(configured_cwd: str | Path | None, runtime_cwd: str | Path) -> Path:
    return Path(configured_cwd) if configured_cwd is not None else Path(runtime_cwd)


def resolved_env_value(
    name: str,
    *,
    explicit_env: dict[str, str] | None = None,
    env_vars: list[str | dict[str, Any]] | tuple[str | dict[str, Any], ...] = (),
    local_env: dict[str, str] | None = None,
    remote_env: bool = False,
) -> str | None:
    if explicit_env is not None and name in explicit_env:
        return explicit_env[name]
    source = local_env or os.environ
    for item in env_vars:
        if isinstance(item, str):
            if item == name:
                return source.get(name)
            continue
        if not isinstance(item, dict) or item.get("name") != name:
            continue
        env_source = item.get("source")
        if env_source == "remote":
            return None if remote_env else source.get(name)
        if env_source in (None, "local"):
            return source.get(name)
    return None


def sandbox_state_meta(sandbox_policy: Any, cwd: str | Path, *, use_legacy_landlock: bool = False) -> dict[str, Any]:
    return {
        MCP_SANDBOX_STATE_META_CAPABILITY: {
            "sandboxPolicy": sandbox_policy,
            "sandboxCwd": str(cwd),
            "useLegacyLandlock": bool(use_legacy_landlock),
        }
    }


def should_run_mcp_tool_calls_concurrently(
    *,
    supports_parallel_tool_calls: bool = False,
    tool_read_only: bool = False,
) -> bool:
    return bool(supports_parallel_tool_calls or tool_read_only)


def mcp_call_begin_event(call_id: str, server_name: str, tool_name: str, arguments: Any | None = None) -> McpToolCallBeginEvent:
    return McpToolCallBeginEvent(call_id, McpInvocation(server_name, tool_name, arguments))


def mcp_call_end_event(
    call_id: str,
    server_name: str,
    tool_name: str,
    result: CallToolResult,
    arguments: Any | None = None,
    *,
    duration: Any = None,
) -> McpToolCallEndEvent:
    return McpToolCallEndEvent(call_id, McpInvocation(server_name, tool_name, arguments), duration, result)


def echo_tool_result(message: str, env_value: str | None = None) -> CallToolResult:
    structured: dict[str, Any] = {"echo": f"ECHOING: {message}"}
    if env_value is not None:
        structured["env"] = env_value
    return CallToolResult(content=(), structured_content=structured, is_error=False)


def sync_tool_result() -> CallToolResult:
    return CallToolResult(content=(), structured_content={"result": "ok"}, is_error=False)


def wrap_mcp_output(payload: Any, *, wall_time_seconds: float = 0) -> str:
    wall = str(int(wall_time_seconds)) if wall_time_seconds == int(wall_time_seconds) else str(wall_time_seconds)
    return f"Wall time: {wall} seconds\nOutput:\n{json.dumps(payload, separators=(',', ':'))}"


def unwrap_mcp_output(text: str) -> Any:
    marker = "\nOutput:\n"
    if marker not in text:
        raise ValueError("wrapped MCP output missing Output marker")
    _wall, payload = text.split(marker, 1)
    return json.loads(payload)


def image_result_from_data_url(data_url: str) -> CallToolResult:
    prefix, encoded = data_url.split(",", 1)
    if not prefix.startswith("data:") or ";base64" not in prefix:
        raise ValueError("image data URL must be base64 encoded")
    mime_type = prefix.removeprefix("data:").split(";", 1)[0]
    base64.b64decode(encoded, validate=True)
    return CallToolResult(
        content=({"type": "image", "mimeType": mime_type, "data": encoded},),
        structured_content=None,
        is_error=False,
    )


def responses_output_from_mcp_result(
    result: CallToolResult,
    *,
    model_supports_images: bool = True,
    detail: str = "high",
) -> Any:
    image_items = [item for item in result.content if isinstance(item, dict) and item.get("type") == "image"]
    if not image_items:
        return wrap_mcp_output(result.structured_content if result.structured_content is not None else list(result.content))
    if not model_supports_images:
        return wrap_mcp_output([{"type": "text", "text": TEXT_ONLY_IMAGE_OMISSION_TEXT}])
    output: list[dict[str, Any]] = [{"type": "input_text", "text": "Wall time: 0 seconds\nOutput:"}]
    for item in image_items:
        output.append(
            {
                "type": "input_image",
                "image_url": f"data:{item['mimeType']};base64,{item['data']}",
                "detail": detail,
            }
        )
    return output


def save_oauth_tokens(server_name: str, server_url: str, tokens: StoredOAuthTokens | WrappedOAuthTokenResponse) -> None:
    if isinstance(tokens, WrappedOAuthTokenResponse):
        tokens = tokens.tokens
    _OAUTH_TOKEN_STORE[(server_name, server_url)] = tokens


def delete_oauth_tokens(server_name: str, server_url: str) -> None:
    _OAUTH_TOKEN_STORE.pop((server_name, server_url), None)


def load_oauth_tokens(server_name: str, server_url: str) -> StoredOAuthTokens | None:
    return _OAUTH_TOKEN_STORE.get((server_name, server_url))


def write_fallback_oauth_tokens(
    home: str | Path,
    server_name: str,
    server_url: str,
    client_id: str,
    access_token: str,
    refresh_token: str | None = None,
) -> Path:
    path = Path(home) / ".credentials.json"
    path.write_text(
        json.dumps(
            {
                "stub": {
                    "server_name": server_name,
                    "server_url": server_url,
                    "client_id": client_id,
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "scopes": ["profile"],
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def read_fallback_oauth_tokens(home: str | Path, server_name: str, server_url: str) -> StoredOAuthTokens | None:
    path = Path(home) / ".credentials.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data.values():
        if item.get("server_name") == server_name and item.get("server_url") == server_url:
            return StoredOAuthTokens(item["access_token"], item.get("refresh_token"))
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
