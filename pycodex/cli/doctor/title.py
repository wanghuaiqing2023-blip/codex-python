"""Rust-aligned implementation for codex-cli doctor::title."""



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



from pycodex.cli.doctor.git import _git_repo_root

from pycodex.cli.doctor import DoctorUpdateCheck, _DEFAULT_TERMINAL_TITLE_ITEMS, _PROJECT_TITLE_MAX_CHARS, _TERMINAL_TITLE_ITEM_ALIASES, _bool_text, _display_list



@dataclass(frozen=True)
class TerminalTitleInputs:
    configured_items: tuple[str, ...] | None = None
    cwd: Path = Path(".")
    project_root: Path | None = None
    project_source: str | None = None

def terminal_title_check(
    *,
    cwd: str | Path | None = None,
    config: dict[str, Any] | None = None,
    inputs: TerminalTitleInputs | None = None,
    project_root: str | Path | None = None,
    project_source: str | None = None,
) -> DoctorUpdateCheck:
    cwd_path = Path.cwd() if cwd is None else Path(cwd)
    if inputs is None:
        configured_items = _configured_terminal_title_items(config or {})
        root = Path(project_root) if project_root is not None else _git_repo_root(cwd_path)
        source = project_source if project_source is not None else ("git repo root" if root is not None else None)
        inputs = TerminalTitleInputs(
            configured_items=configured_items,
            cwd=cwd_path,
            project_root=root,
            project_source=source,
        )
    if inputs.configured_items is None:
        source = "default"
        items = list(_DEFAULT_TERMINAL_TITLE_ITEMS)
        invalid_items: list[str] = []
    elif not inputs.configured_items:
        source = "disabled"
        items = []
        invalid_items = []
    else:
        source = "configured"
        items, invalid_items = _parse_terminal_title_items(inputs.configured_items)
    details = [
        f"terminal title source: {source}",
        f"terminal title items: {_display_list(items)}",
        f"terminal title activity: {_bool_text('activity' in items)}",
    ]
    if invalid_items:
        details.append(f"terminal title invalid items: {', '.join(invalid_items)}")
    if "project-name" in items:
        project_source_value, project_value = _terminal_title_project_candidate(
            inputs.project_root,
            inputs.cwd,
            inputs.project_source,
        )
        details.append(f"terminal title project source: {project_source_value}")
        details.append(f"terminal title project value: {project_value}")
    status = "warn" if invalid_items else "ok"
    summary = (
        f"terminal title {source} with invalid items"
        if invalid_items
        else f"terminal title {source}"
    )
    remediation = "Remove or replace the unknown entries in [tui].terminal_title." if invalid_items else None
    return DoctorUpdateCheck(status=status, summary=summary, details=tuple(details), remediation=remediation)

def _configured_terminal_title_items(config: dict[str, Any]) -> tuple[str, ...] | None:
    tui = config.get("tui")
    if isinstance(tui, dict):
        raw_items = tui.get("terminal_title")
    else:
        raw_items = config.get("terminal_title")
    if raw_items is None:
        return None
    if isinstance(raw_items, list):
        return tuple(str(item) for item in raw_items)
    return (str(raw_items),)

def _parse_terminal_title_items(raw_items: tuple[str, ...]) -> tuple[list[str], list[str]]:
    items: list[str] = []
    invalid: list[str] = []
    invalid_seen: set[str] = set()
    for item in raw_items:
        parsed = _TERMINAL_TITLE_ITEM_ALIASES.get(item)
        if parsed is None:
            if item not in invalid_seen:
                invalid_seen.add(item)
                invalid.append(f'"{item}"')
        else:
            items.append(parsed)
    return items, invalid

def _terminal_title_project_candidate(
    project_root: Path | None,
    cwd: Path,
    project_source: str | None,
) -> tuple[str, str]:
    if project_root is not None:
        return project_source or "git repo root", _truncate_title_part(_path_display_name(project_root))
    return "cwd", _truncate_title_part(_path_display_name(cwd))

def _path_display_name(path: Path) -> str:
    return path.name or str(path)

def _truncate_title_part(value: str) -> str:
    if len(value) <= _PROJECT_TITLE_MAX_CHARS:
        return value
    return value[: _PROJECT_TITLE_MAX_CHARS - 3] + "..."

