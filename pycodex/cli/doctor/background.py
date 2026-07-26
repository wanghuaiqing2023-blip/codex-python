"""Rust-aligned implementation for codex-cli doctor::background."""



from __future__ import annotations

import ctypes

from dataclasses import dataclass

import gc

import json

import locale

import os

import platform

import socket

import stat

from pathlib import Path

import shutil

import sqlite3

import subprocess

import sys

import time

import tomllib

from typing import Any, Callable, Mapping

from urllib.error import HTTPError, URLError

from urllib.request import Request, urlopen

from urllib.parse import parse_qsl

from urllib.parse import urlparse

from contextlib import suppress

from pycodex.exec.session import UDS_WEBSOCKET_HANDSHAKE_URL

from pycodex.codex_api.error import ApiError

from pycodex.codex_api.endpoint.responses_websocket import (
    ResponsesWebsocketClient,
    connect_websocket as responses_connect_websocket,
)

from pycodex.codex_api.provider import Provider, RetryConfig

from pycodex.core import OPENAI_BETA_HEADER, RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE

from pycodex.exec.websocket import (
    StdlibWebSocket,
    websocket_frame_event,
)

from pycodex.model_provider.auth import unauthenticated_auth_provider

from pycodex.model_provider.bearer_auth_provider import BearerAuthProvider

from pycodex.tui.update_action import UpdateAction

from pycodex.tui.update_versions import is_newer



from pycodex.cli.doctor import AppServerVersionProbe, DoctorUpdateCheck, _WEBSOCKET_IMMEDIATE_CLOSE_GRACE_SECONDS



def background_server_check(
    *,
    codex_home: str | Path,
    socket_path: str | Path | None = None,
    version_probe: AppServerVersionProbe | None = None,
) -> DoctorUpdateCheck:
    home = Path(codex_home)
    state_dir = home / "app-server-daemon"
    details = [f"daemon state dir: {state_dir}"]
    _push_file_detail(details, "settings", state_dir / "settings.json")
    _push_file_detail(details, "pid file", state_dir / "app-server.pid")
    _push_file_detail(details, "update-loop pid file", state_dir / "app-server-updater.pid")

    control_socket = Path(socket_path) if socket_path is not None else home / "app-server-control" / "app-server-control.sock"
    details.append(f"control socket: {control_socket}")
    if not control_socket.exists():
        details.append("status: not running")
        details.append(f"mode: {_background_server_mode(state_dir)}")
        return DoctorUpdateCheck(
            status="ok",
            summary="background server is not running",
            details=tuple(details),
        )

    probe = version_probe or _default_app_server_version_probe
    try:
        app_server_version = probe(control_socket)
    except Exception as exc:
        details.append("status: stale or unreachable")
        details.append(f"app-server version: unavailable ({_concise_probe_error(exc, control_socket)})")
        details.append(f"mode: {_background_server_mode(state_dir)}")
        return DoctorUpdateCheck(
            status="warn",
            summary="background server socket is stale or unreachable",
            details=tuple(details),
            remediation="Run codex app-server daemon version for more details.",
        )
    details.append("status: running")
    details.append(f"app-server version: {app_server_version}")
    details.append(f"mode: {_background_server_mode(state_dir)}")
    return DoctorUpdateCheck(
        status="ok",
        summary="background server is running",
        details=tuple(details),
    )

def _push_file_detail(details: list[str], label: str, path: Path) -> None:
    try:
        if path.is_file():
            details.append(f"{label}: {path} (file)")
        elif path.exists():
            details.append(f"{label}: {path} (not a file)")
        else:
            details.append(f"{label}: {path} (missing)")
    except OSError as exc:
        details.append(f"{label}: {path} ({exc})")

def _background_server_mode(state_dir: Path) -> str:
    return "persistent" if (state_dir / "settings.json").is_file() else "ephemeral"

def _default_app_server_version_probe(_socket_path: Path) -> str:
    websocket = StdlibWebSocket.connect_unix_socket(
        _socket_path,
        websocket_url=UDS_WEBSOCKET_HANDSHAKE_URL,
        timeout=10.0,
    )
    try:
        websocket.send_text(
            json.dumps(
                {
                    "id": 1,
                    "method": "initialize",
                    "params": {"clientInfo": {"name": "codex", "title": "Codex Python", "version": "0.0.0"}},
                }
            )
        )
        frames = 0
        while True:
            if frames > 32:
                raise RuntimeError("timed out waiting for app-server initialize response")
            frames += 1
            response = websocket.recv_text(expect_masked=False)
            message = json.loads(response)
            if not isinstance(message, dict):
                raise RuntimeError(f"invalid initialize response: {type(message).__name__}")
            if "id" in message and message["id"] != 1:
                continue
            if "error" in message:
                error = message["error"]
                if isinstance(error, Mapping) and "message" in error:
                    raise RuntimeError(f"initialize failed: {error['message']}")
                raise RuntimeError(f"initialize failed: {error}")
            if "result" not in message:
                raise RuntimeError(f"invalid initialize response: {message!r}")
            result = message["result"]
            if not isinstance(result, Mapping):
                raise RuntimeError(f"invalid initialize result: {type(result).__name__}")
            user_agent = _extract_user_agent(result)
            if not user_agent:
                raise RuntimeError("initialize response missing user-agent")
            version = _parse_version_from_user_agent(user_agent)
            if not version:
                raise RuntimeError(f"invalid app-server user-agent: {user_agent}")
            return version
    finally:
        with suppress(Exception):
            websocket.close()

def _extract_user_agent(result: Mapping[str, Any]) -> str | None:
    value = result.get("userAgent")
    if value is None:
        value = result.get("user_agent")
    if isinstance(value, str):
        return value
    return None

def _parse_version_from_user_agent(user_agent: str) -> str:
    parts = user_agent.split("/", 1)
    if len(parts) != 2:
        raise RuntimeError(f"invalid app-server user-agent: {user_agent}")
    _, rest = parts
    version = rest.split()[0].strip()
    if not version:
        raise RuntimeError(f"invalid app-server user-agent: {user_agent}")
    return version

def _probe_websocket_immediate_close(websocket: StdlibWebSocket) -> tuple[int, str] | None:
    sock = getattr(websocket, "_sock", None)
    if sock is None or not hasattr(sock, "settimeout"):
        return None
    sock.settimeout(_WEBSOCKET_IMMEDIATE_CLOSE_GRACE_SECONDS)
    try:
        frame = websocket.recv_frame(expect_masked=False)
    except (socket.timeout, TimeoutError, EOFError):
        return None
    event = websocket_frame_event(frame)
    if event.kind != "close":
        return None
    if event.close_code is None:
        return None
    return event.close_code, event.close_reason or "connection closed"

def _concise_probe_error(exc: BaseException, socket_path: Path) -> str:
    message = str(exc).replace(str(socket_path), "control socket")
    message = " ".join(message.split())
    if not message:
        message = "unknown error"
    if len(message) > 120:
        return message[:120] + "..."
    return message

