"""Rust-aligned implementation for codex-cli doctor::runtime."""



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



from pycodex.cli.doctor import CommandRunner, DoctorUpdateCheck, _package_layout_from_exe, _standalone_release_info, describe_install_context, detect_update_action, run_command



def runtime_check(
    *,
    current_version: str,
    current_exe: str | Path | None = None,
    env: dict[str, str] | os._Environ[str] | None = None,
    codex_home: str | Path | None = None,
) -> DoctorUpdateCheck:
    if not isinstance(current_version, str):
        raise TypeError("current_version must be a string")
    environment = os.environ if env is None else env
    exe = Path(sys.executable) if current_exe is None else Path(current_exe)
    platform_name = f"{_rust_os_name()}-{platform.machine().lower() or 'unknown'}"
    update_action = detect_update_action(exe, env=environment, codex_home=codex_home)
    install_method = _runtime_install_method_name(update_action)
    commit = environment.get("CODEX_BUILD_COMMIT") or environment.get("GIT_COMMIT") or "unknown"
    details = (
        f"version: {current_version}",
        f"platform: {platform_name}",
        f"install method: {describe_install_context(exe, env=environment, codex_home=codex_home)}",
        f"commit: {commit}",
        f"current executable: {exe}",
    )
    return DoctorUpdateCheck(
        status="ok",
        summary=f"running {install_method} on {platform_name}",
        details=details,
    )

def search_check(
    *,
    current_exe: str | Path | None = None,
    codex_home: str | Path | None = None,
    command_runner: CommandRunner | None = None,
    rg_command: str | Path | None = None,
    provider: str | None = None,
) -> DoctorUpdateCheck:
    exe = Path(sys.executable) if current_exe is None else Path(current_exe)
    selected_command, selected_provider = _select_rg_command_and_provider(exe, codex_home)
    command_path = Path(rg_command) if rg_command is not None else selected_command
    search_provider = selected_provider if provider is None else provider
    details = [
        f"search command: {command_path}",
        f"search provider: {search_provider}",
    ]
    status = "ok"
    if len(command_path.parts) > 1:
        if command_path.is_file():
            details.append("search command readiness: file exists")
        elif command_path.exists():
            status = "warn"
            details.append("search command readiness: path is not a file")
        else:
            status = "warn"
            details.append(f"search command readiness: {command_path} not found")
    else:
        runner = run_command if command_runner is None else command_runner
        try:
            output = runner(str(command_path), ("--version",))
        except Exception as exc:
            status = "warn"
            details.append(f"search command readiness: {exc}")
        else:
            first_line = next((line for line in output.splitlines() if line), "rg version unknown")
            details.append(f"search command readiness: {first_line}")
    summary = f"search is OK ({search_provider})" if status == "ok" else "search command could not be verified"
    remediation = None if status == "ok" else "Install ripgrep or repair the bundled Codex package."
    return DoctorUpdateCheck(status=status, summary=summary, details=tuple(details), remediation=remediation)

def _select_rg_command_and_provider(current_exe: Path, codex_home: str | Path | None) -> tuple[Path, str]:
    package_layout = _package_layout_from_exe(current_exe)
    if package_layout is not None:
        _package_dir, _bin_dir, _resources_dir, path_dir = package_layout
        if path_dir is not None:
            bundled_rg = path_dir / _default_rg_command()
            if bundled_rg.is_file():
                return bundled_rg, "bundled"
    standalone = _standalone_release_info(current_exe, codex_home)
    if standalone is not None:
        _release_dir, resources_dir, _layout = standalone
        if resources_dir is not None:
            bundled_rg = resources_dir / _default_rg_command()
            if bundled_rg.is_file():
                return bundled_rg, "bundled"
    return Path(_default_rg_command()), "system"

def _default_rg_command() -> str:
    return "rg.exe" if os.name == "nt" else "rg"

def _runtime_install_method_name(update_action: UpdateAction | None) -> str:
    if update_action is UpdateAction.NPM_GLOBAL_LATEST:
        return "npm"
    if update_action is UpdateAction.BUN_GLOBAL_LATEST:
        return "bun"
    if update_action is UpdateAction.BREW_UPGRADE:
        return "brew"
    if update_action in {UpdateAction.STANDALONE_UNIX, UpdateAction.STANDALONE_WINDOWS}:
        return "standalone"
    return "local build"

def _rust_os_name() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform

