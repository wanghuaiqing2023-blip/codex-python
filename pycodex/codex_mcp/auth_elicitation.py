"""Connector auth elicitation from ``codex-mcp/src/auth_elicitation.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


MCP_TOOL_CODEX_APPS_META_KEY = "_codex_apps"
CONNECTOR_AUTH_FAILURE_META_KEY = "connector_auth_failure"


@dataclass(frozen=True)
class CodexAppsConnectorAuthFailure:
    connector_id: str
    connector_name: str
    install_url: str
    auth_reason: str | None = None
    link_id: str | None = None
    error_code: str | None = None
    error_http_status_code: int | None = None
    error_action: str | None = None


@dataclass(frozen=True)
class CodexAppsAuthElicitation:
    meta: Mapping[str, Any]
    message: str
    url: str
    elicitation_id: str


@dataclass(frozen=True)
class CodexAppsAuthElicitationPlan:
    auth_failure: CodexAppsConnectorAuthFailure
    elicitation: CodexAppsAuthElicitation


def connector_auth_failure_from_tool_result(
    result: Any,
    connector_id: str | None,
    connector_name: str | None,
    install_url: str | None,
) -> CodexAppsConnectorAuthFailure | None:
    if _field(result, "is_error", "isError") is not True:
        return None
    meta = _field(result, "meta", "_meta")
    failure = _nested_mapping(
        meta,
        MCP_TOOL_CODEX_APPS_META_KEY,
        CONNECTOR_AUTH_FAILURE_META_KEY,
    )
    if failure is None or failure.get("is_auth_failure") is not True:
        return None
    normalized_id = _nonempty(connector_id)
    if normalized_id is None or install_url is None:
        return None
    declared_id = _nonempty(failure.get("connector_id"))
    if declared_id is not None and declared_id != normalized_id:
        return None
    return CodexAppsConnectorAuthFailure(
        normalized_id,
        _nonempty(connector_name) or normalized_id,
        install_url,
        _nonempty(failure.get("auth_reason")),
        _nonempty(failure.get("link_id")),
        _nonempty(failure.get("error_code")),
        (
            int(failure["error_http_status_code"])
            if isinstance(failure.get("error_http_status_code"), int)
            else None
        ),
        _nonempty(failure.get("error_action")),
    )


def build_auth_elicitation_plan(
    call_id: str,
    result: Any,
    connector_id: str | None,
    connector_name: str | None,
    install_url: str | None,
) -> CodexAppsAuthElicitationPlan | None:
    failure = connector_auth_failure_from_tool_result(
        result,
        connector_id,
        connector_name,
        install_url,
    )
    if failure is None:
        return None
    return CodexAppsAuthElicitationPlan(
        failure,
        build_auth_elicitation(call_id, failure),
    )


def build_auth_elicitation(
    call_id: str,
    auth_failure: CodexAppsConnectorAuthFailure,
) -> CodexAppsAuthElicitation:
    failure_meta: dict[str, Any] = {
        "is_auth_failure": True,
        "connector_id": auth_failure.connector_id,
        "connector_name": auth_failure.connector_name,
        "install_url": auth_failure.install_url,
    }
    for key in (
        "auth_reason",
        "link_id",
        "error_code",
        "error_http_status_code",
        "error_action",
    ):
        value = getattr(auth_failure, key)
        if value is not None:
            failure_meta[key] = value
    return CodexAppsAuthElicitation(
        {
            MCP_TOOL_CODEX_APPS_META_KEY: {
                CONNECTOR_AUTH_FAILURE_META_KEY: failure_meta
            }
        },
        _auth_elicitation_message(auth_failure),
        auth_failure.install_url,
        auth_elicitation_id(call_id),
    )


def auth_elicitation_completed_result(
    auth_failure: CodexAppsConnectorAuthFailure,
    meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Authentication for {auth_failure.connector_name} was requested "
                    "and accepted. Retry this tool call now."
                ),
            }
        ],
        "structuredContent": None,
        "isError": True,
        "_meta": dict(meta) if meta is not None else None,
    }


def auth_elicitation_id(call_id: str) -> str:
    return f"codex_apps_auth_{call_id}"


def _auth_elicitation_message(failure: CodexAppsConnectorAuthFailure) -> str:
    messages = {
        "oauth_upgrade_required": (
            f"Reconnect {failure.connector_name} on ChatGPT to grant the "
            "permissions needed for this request."
        ),
        "reauthentication_required": (
            f"Reconnect {failure.connector_name} on ChatGPT to restore access "
            "for this request."
        ),
        "missing_link": (
            f"Sign in to {failure.connector_name} on ChatGPT to use it in Codex."
        ),
    }
    return messages.get(
        failure.auth_reason,
        f"Sign in to {failure.connector_name} on ChatGPT to continue.",
    )


def _field(value: Any, *names: str) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _nested_mapping(value: Any, *keys: str) -> Mapping[str, Any] | None:
    current = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current if isinstance(current, Mapping) else None


def _nonempty(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


__all__ = [
    "CodexAppsAuthElicitation",
    "CodexAppsAuthElicitationPlan",
    "CodexAppsConnectorAuthFailure",
    "MCP_TOOL_CODEX_APPS_META_KEY",
    "auth_elicitation_completed_result",
    "auth_elicitation_id",
    "build_auth_elicitation",
    "build_auth_elicitation_plan",
    "connector_auth_failure_from_tool_result",
]
