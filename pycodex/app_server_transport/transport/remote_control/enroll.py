from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import Message
from typing import Any, Mapping

from pycodex.state import (
    RemoteControlEnrollmentRecord,
    delete_remote_control_enrollment,
    get_remote_control_enrollment,
    upsert_remote_control_enrollment,
)

from .protocol import (
    EnrollRemoteServerRequest,
    EnrollRemoteServerResponse,
    RemoteControlTarget,
)

REMOTE_CONTROL_ENROLL_TIMEOUT_SECONDS = 30.0
REMOTE_CONTROL_RESPONSE_BODY_MAX_BYTES = 4096
REMOTE_CONTROL_ACCOUNT_ID_HEADER = "chatgpt-account-id"
REMOTE_CONTROL_INSTALLATION_ID_HEADER = "x-codex-installation-id"


@dataclass(frozen=True)
class RemoteControlEnrollment:
    account_id: str
    environment_id: str
    server_id: str
    server_name: str


@dataclass(frozen=True)
class RemoteControlConnectionAuth:
    auth_provider: Any
    account_id: str


def _state_db(state_db: Any) -> Any:
    return getattr(state_db, "state_db", state_db)


async def load_persisted_remote_control_enrollment(
    state_db: Any | None,
    remote_control_target: RemoteControlTarget,
    account_id: str,
    app_server_client_name: str | None,
) -> RemoteControlEnrollment | None:
    if state_db is None:
        raise FileNotFoundError(
            "remote control enrollment cache unavailable because sqlite state db "
            "is disabled: "
            f"websocket_url={remote_control_target.websocket_url}, "
            f"account_id={account_id}, "
            f"app_server_client_name={app_server_client_name!r}"
        )
    record = await get_remote_control_enrollment(
        _state_db(state_db),
        remote_control_target.websocket_url,
        account_id,
        app_server_client_name,
    )
    if record is None:
        return None
    return RemoteControlEnrollment(
        account_id=record.account_id,
        environment_id=record.environment_id,
        server_id=record.server_id,
        server_name=record.server_name,
    )


async def update_persisted_remote_control_enrollment(
    state_db: Any | None,
    remote_control_target: RemoteControlTarget,
    account_id: str,
    app_server_client_name: str | None,
    enrollment: RemoteControlEnrollment | None,
) -> None:
    if state_db is None:
        raise FileNotFoundError(
            "remote control enrollment persistence unavailable because sqlite "
            "state db is disabled: "
            f"websocket_url={remote_control_target.websocket_url}, "
            f"account_id={account_id}, "
            f"app_server_client_name={app_server_client_name!r}, "
            f"has_enrollment={enrollment is not None}"
        )
    database = _state_db(state_db)
    if enrollment is not None and enrollment.account_id != account_id:
        raise OSError(
            "enrollment account_id does not match expected account_id "
            f"`{account_id}`"
        )
    if enrollment is None:
        await delete_remote_control_enrollment(
            database,
            remote_control_target.websocket_url,
            account_id,
            app_server_client_name,
        )
        return
    await upsert_remote_control_enrollment(
        database,
        RemoteControlEnrollmentRecord(
            websocket_url=remote_control_target.websocket_url,
            account_id=account_id,
            app_server_client_name=app_server_client_name,
            server_id=enrollment.server_id,
            environment_id=enrollment.environment_id,
            server_name=enrollment.server_name,
        ),
    )


def preview_remote_control_response_body(body: bytes) -> str:
    trimmed = body.decode("utf-8", errors="replace").strip()
    if not trimmed:
        return "<empty>"
    encoded = trimmed.encode("utf-8")
    if len(encoded) <= REMOTE_CONTROL_RESPONSE_BODY_MAX_BYTES:
        return trimmed
    prefix = encoded[:REMOTE_CONTROL_RESPONSE_BODY_MAX_BYTES]
    while prefix:
        try:
            return prefix.decode("utf-8") + "..."
        except UnicodeDecodeError:
            prefix = prefix[:-1]
    return "..."


def _header_value(headers: Mapping[str, Any] | Message, name: str) -> str | None:
    value = headers.get(name)
    if value is not None:
        return str(value)
    lower_name = name.lower()
    for key, candidate in headers.items():
        if str(key).lower() == lower_name:
            return str(candidate)
    return None


def format_headers(headers: Mapping[str, Any] | Message) -> str:
    request_id = (
        _header_value(headers, "x-request-id")
        or _header_value(headers, "x-oai-request-id")
        or "<none>"
    )
    cf_ray = _header_value(headers, "cf-ray") or "<none>"
    return f"request-id: {request_id}, cf-ray: {cf_ray}"


async def _auth_headers(provider: Any) -> dict[str, str]:
    headers: dict[str, str] = {}
    add_headers = getattr(provider, "add_auth_headers", None)
    if callable(add_headers):
        result = add_headers(headers)
        if hasattr(result, "__await__"):
            result = await result
        if isinstance(result, Mapping):
            headers.update({str(key): str(value) for key, value in result.items()})
        return headers
    token = getattr(provider, "token", None) or getattr(provider, "access_token", None)
    if callable(token):
        token = token()
        if hasattr(token, "__await__"):
            token = await token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _send_enrollment_request(
    url: str,
    body: bytes,
    headers: Mapping[str, str],
) -> tuple[int, Message, bytes]:
    request = urllib.request.Request(
        url,
        data=body,
        headers=dict(headers),
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=REMOTE_CONTROL_ENROLL_TIMEOUT_SECONDS,
        ) as response:
            return int(response.status), response.headers, response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.headers, exc.read()


async def enroll_remote_control_server(
    remote_control_target: RemoteControlTarget,
    auth: RemoteControlConnectionAuth,
    installation_id: str,
    server_name: str,
) -> RemoteControlEnrollment:
    request_body = json.dumps(
        EnrollRemoteServerRequest(
            name=server_name,
            installation_id=installation_id,
        ).to_mapping(),
        separators=(",", ":"),
    ).encode()
    headers = await _auth_headers(auth.auth_provider)
    headers.update(
        {
            "Content-Type": "application/json",
            REMOTE_CONTROL_ACCOUNT_ID_HEADER: auth.account_id,
            REMOTE_CONTROL_INSTALLATION_ID_HEADER: installation_id,
        }
    )
    try:
        status, response_headers, body = await asyncio.to_thread(
            _send_enrollment_request,
            remote_control_target.enroll_url,
            request_body,
            headers,
        )
    except Exception as exc:
        raise OSError(
            "failed to enroll remote control server at "
            f"`{remote_control_target.enroll_url}`: {exc}"
        ) from exc

    preview = preview_remote_control_response_body(body)
    if not 200 <= status < 300:
        message = (
            "remote control server enrollment failed at "
            f"`{remote_control_target.enroll_url}`: HTTP {status}, "
            f"{format_headers(response_headers)}, body: {preview}"
        )
        if status in {401, 403}:
            raise PermissionError(message)
        raise OSError(message)
    try:
        payload = json.loads(body)
        response = EnrollRemoteServerResponse(
            server_id=str(payload["server_id"]),
            environment_id=str(payload["environment_id"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise OSError(
            "failed to parse remote control enrollment response from "
            f"`{remote_control_target.enroll_url}`: HTTP {status}, "
            f"{format_headers(response_headers)}, body: {preview}, "
            f"decode error: {exc}"
        ) from exc
    return RemoteControlEnrollment(
        account_id=auth.account_id,
        environment_id=response.environment_id,
        server_id=response.server_id,
        server_name=server_name,
    )


__all__ = [
    "REMOTE_CONTROL_ACCOUNT_ID_HEADER",
    "REMOTE_CONTROL_INSTALLATION_ID_HEADER",
    "RemoteControlConnectionAuth",
    "RemoteControlEnrollment",
    "enroll_remote_control_server",
    "format_headers",
    "load_persisted_remote_control_enrollment",
    "preview_remote_control_response_body",
    "update_persisted_remote_control_enrollment",
]
