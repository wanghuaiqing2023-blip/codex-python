from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pycodex import __version__
from pycodex.app_server_protocol import InitializeResponse


CONTROL_SOCKET_RESPONSE_TIMEOUT = 2.0
CLIENT_NAME = "codex_app_server_daemon"
INITIALIZE_REQUEST_ID = 1


class ProbeInfo:
    def __init__(self, app_server_version: str) -> None:
        self.app_server_version = app_server_version

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, ProbeInfo)
            and self.app_server_version == other.app_server_version
        )


async def probe(socket_path: Path) -> ProbeInfo:
    try:
        return await asyncio.wait_for(
            _probe_inner(socket_path),
            timeout=CONTROL_SOCKET_RESPONSE_TIMEOUT,
        )
    except TimeoutError as exc:
        raise RuntimeError(
            f"timed out probing app-server control socket {socket_path}"
        ) from exc


async def _probe_inner(socket_path: Path) -> ProbeInfo:
    websocket = await connect(socket_path)
    try:
        response = await initialize(websocket, experimental_api=False)
        await send_message(websocket, {"method": "initialized"})
    finally:
        await _close(websocket)
    return ProbeInfo(parse_version_from_user_agent(response.user_agent))


async def connect(socket_path: Path) -> Any:
    try:
        from websockets.asyncio.client import unix_connect

        return await unix_connect(path=str(socket_path), uri="ws://localhost/")
    except Exception as exc:
        raise RuntimeError(f"failed to connect to {socket_path}: {exc}") from exc


async def initialize(websocket: Any, experimental_api: bool) -> InitializeResponse:
    capabilities: dict[str, object] | None
    if experimental_api:
        capabilities = {
            "experimentalApi": True,
            "requestAttestation": False,
            "optOutNotificationMethods": None,
        }
    else:
        capabilities = None
    params: dict[str, object] = {
        "clientInfo": {
            "name": CLIENT_NAME,
            "title": "Codex App Server Daemon",
            "version": __version__,
        }
    }
    if capabilities is not None:
        params["capabilities"] = capabilities
    await send_message(
        websocket,
        {
            "id": INITIALIZE_REQUEST_ID,
            "method": "initialize",
            "params": params,
        },
    )

    while True:
        try:
            message = await asyncio.wait_for(
                read_message(websocket),
                timeout=CONTROL_SOCKET_RESPONSE_TIMEOUT,
            )
        except TimeoutError as exc:
            raise RuntimeError("timed out waiting for initialize response") from exc
        if message.get("id") != INITIALIZE_REQUEST_ID or "result" not in message:
            continue
        result = message["result"]
        if not isinstance(result, dict):
            raise RuntimeError("failed to parse initialize response")
        try:
            return InitializeResponse.from_mapping(result)
        except (TypeError, ValueError, KeyError) as exc:
            raise RuntimeError(f"failed to parse initialize response: {exc}") from exc


async def send_message(websocket: Any, message: dict[str, object]) -> None:
    await websocket.send(json.dumps(message, separators=(",", ":")))


async def read_message(websocket: Any) -> dict[str, object]:
    while True:
        try:
            payload = await websocket.recv()
        except Exception as exc:
            raise RuntimeError(f"app-server closed the control socket: {exc}") from exc
        if isinstance(payload, bytes):
            try:
                payload = payload.decode("utf-8")
            except UnicodeDecodeError:
                continue
        if not isinstance(payload, str):
            continue
        try:
            message = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"failed to parse app-server JSON-RPC message: {exc}"
            ) from exc
        if not isinstance(message, dict):
            raise RuntimeError("failed to parse app-server JSON-RPC message: expected object")
        return message


def parse_version_from_user_agent(user_agent: str) -> str:
    if "/" not in user_agent:
        raise ValueError("app-server user-agent omitted version separator")
    _originator, rest = user_agent.split("/", 1)
    parts = rest.split()
    if not parts or not parts[0]:
        raise ValueError("app-server user-agent omitted version")
    return parts[0]


async def _close(websocket: Any) -> None:
    try:
        result = websocket.close()
        if hasattr(result, "__await__"):
            await result
    except Exception:
        pass


__all__ = [
    "CLIENT_NAME",
    "CONTROL_SOCKET_RESPONSE_TIMEOUT",
    "INITIALIZE_REQUEST_ID",
    "ProbeInfo",
    "connect",
    "initialize",
    "parse_version_from_user_agent",
    "probe",
    "read_message",
    "send_message",
]
