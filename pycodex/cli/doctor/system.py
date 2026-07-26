"""Rust-aligned implementation for codex-cli doctor::system."""



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



from pycodex.cli.doctor import DoctorUpdateCheck, LOCALE_ENV_VARS



@dataclass(frozen=True)
class SystemCheckInputs:
    os: str
    os_type: str
    os_version: str
    os_language: str | None = None
    locale_env: dict[str, str] | None = None

def system_check(
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    inputs: SystemCheckInputs | None = None,
) -> DoctorUpdateCheck:
    if inputs is None:
        environment = os.environ if env is None else env
        detected_language = locale.getlocale()[0]
        inputs = SystemCheckInputs(
            os=platform.platform(),
            os_type=platform.system().lower() or "unknown",
            os_version=platform.version() or "unknown",
            os_language=detected_language,
            locale_env={name: environment[name] for name in LOCALE_ENV_VARS if name in environment},
        )
    locale_env = inputs.locale_env or {}
    details = [
        f"os: {inputs.os}",
        f"os type: {inputs.os_type}",
        f"os version: {inputs.os_version}",
    ]
    if inputs.os_language is None:
        details.append("os language: unavailable")
        summary = "OS language unavailable"
    else:
        details.append(f"os language: {inputs.os_language}")
        summary = f"OS language {inputs.os_language}"
    for name in LOCALE_ENV_VARS:
        value = locale_env.get(name)
        if value is not None:
            details.append(f"{name}: {value}")
    return DoctorUpdateCheck(status="ok", summary=summary, details=tuple(details))

