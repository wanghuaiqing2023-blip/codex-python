"""Rust-aligned implementation for codex-cli doctor::progress."""



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



from pycodex.cli.doctor.output import _doctor_json_status



def should_show_progress(*, json_output: bool, term: str | None, stderr_is_tty: bool) -> bool:
    return not json_output and stderr_is_tty and term != "dumb"

def _doctor_progress_status_label(check: Any) -> str:
    status = _doctor_json_status(
        check.get("status", "warning") if isinstance(check, Mapping) else getattr(check, "status", "warning")
    )
    return {"ok": "Ok", "warning": "Warning", "fail": "Fail"}[status]

def _doctor_run_sync_check(label: str, progress: Any, callback: Callable[[], Any]) -> Any:
    progress.begin(label)
    check = callback()
    progress.finish(label, _doctor_progress_status_label(check))
    return check

async def _doctor_run_async_check(label: str, progress: Any, awaitable: Any) -> Any:
    progress.begin(label)
    check = await awaitable
    progress.finish(label, _doctor_progress_status_label(check))
    return check

