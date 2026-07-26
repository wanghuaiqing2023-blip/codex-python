"""Rust-aligned implementation for codex-cli doctor::updates."""



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



import pycodex.cli.doctor as doctor
from pycodex.cli.doctor import CommandRunner, DoctorUpdateCheck, JsonGetter, NpmRootCheck



GITHUB_LATEST_RELEASE_URL = "https://api.github.com/repos/openai/codex/releases/latest"

HOMEBREW_CASK_API_URL = "https://formulae.brew.sh/api/cask/codex.json"

def update_action_label(action: UpdateAction | None) -> str:
    """Render the install-context label owned by doctor::updates."""

    if action is None:
        return "manual or unknown"
    if action is UpdateAction.NPM_GLOBAL_LATEST:
        return "npm install -g @openai/codex"
    if action is UpdateAction.BUN_GLOBAL_LATEST:
        return "bun install -g @openai/codex"
    if action is UpdateAction.BREW_UPGRADE:
        return "brew upgrade --cask codex"
    if action in {UpdateAction.STANDALONE_UNIX, UpdateAction.STANDALONE_WINDOWS}:
        return "standalone installer"
    raise ValueError(f"unknown update action: {action!r}")

@dataclass(frozen=True)
class VersionInfo:
    latest_version: str
    dismissed_version: str | None = None
    last_checked_at: str | None = None

    @classmethod
    def from_mapping(cls, value: Any) -> "VersionInfo":
        if not isinstance(value, dict):
            raise TypeError("version info must be an object")
        latest_version = value.get("latest_version")
        if not isinstance(latest_version, str):
            raise TypeError("latest_version must be a string")
        dismissed_version = value.get("dismissed_version")
        if dismissed_version is not None and not isinstance(dismissed_version, str):
            raise TypeError("dismissed_version must be a string or null")
        last_checked_at = value.get("last_checked_at")
        if last_checked_at is not None and not isinstance(last_checked_at, str):
            raise TypeError("last_checked_at must be a string or null")
        return cls(
            latest_version=latest_version,
            dismissed_version=dismissed_version,
            last_checked_at=last_checked_at,
        )

def cached_version_details(version_file: str | Path) -> list[str]:
    details: list[str] = []
    push_cached_version_details(details, version_file)
    return details

def push_cached_version_details(details: list[str], version_file: str | Path) -> None:
    if not isinstance(details, list):
        raise TypeError("details must be a list")
    path = Path(version_file)
    details.append(f"version cache: {path}")
    try:
        contents = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        details.append("version cache: missing")
        return
    except (OSError, UnicodeDecodeError) as exc:
        details.append(f"version cache read: {exc}")
        return

    try:
        info = VersionInfo.from_mapping(json.loads(contents))
    except (json.JSONDecodeError, TypeError) as exc:
        details.append(f"version cache parse: {exc}")
        return

    details.append(f"cached latest version: {info.latest_version}")
    if info.last_checked_at is not None:
        details.append(f"last checked at: {info.last_checked_at}")
    if info.dismissed_version is not None:
        details.append(f"dismissed version: {info.dismissed_version}")

def latest_version_details(latest_version: str, current_version: str) -> list[str]:
    details: list[str] = []
    push_latest_version_details(details, latest_version, current_version)
    return details

def push_latest_version_details(details: list[str], latest_version: str, current_version: str) -> None:
    if not isinstance(details, list):
        raise TypeError("details must be a list")
    if not isinstance(latest_version, str):
        raise TypeError("latest_version must be a string")
    if not isinstance(current_version, str):
        raise TypeError("current_version must be a string")
    details.append(f"latest version: {latest_version}")
    if is_newer(latest_version, current_version) is True:
        details.append("latest version status: newer version is available")
    else:
        details.append("latest version status: current version is not older")

def latest_version_probe_error_details(error: str) -> list[str]:
    details: list[str] = []
    push_latest_version_probe_error_details(details, error)
    return details

def push_latest_version_probe_error_details(details: list[str], error: str) -> None:
    if not isinstance(details, list):
        raise TypeError("details must be a list")
    if not isinstance(error, str):
        raise TypeError("error must be a string")
    details.append(f"latest version probe: {error}")

def http_get_json(url: str, *, command_runner: CommandRunner | None = None) -> Any:
    if not isinstance(url, str):
        raise TypeError("url must be a string")
    runner = doctor.run_command if command_runner is None else command_runner
    try:
        body = runner("curl", ("-fsSL", "--max-time", "5", url))
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(str(exc)) from exc

def fetch_latest_version(
    update_action: UpdateAction | None,
    *,
    json_getter: JsonGetter | None = None,
) -> str:
    if update_action is not None and not isinstance(update_action, UpdateAction):
        raise TypeError("update_action must be an UpdateAction or None")
    getter = http_get_json if json_getter is None else json_getter
    if update_action is UpdateAction.BREW_UPGRADE:
        return fetch_homebrew_cask_version(json_getter=getter)
    return fetch_latest_github_release_version(json_getter=getter)

def fetch_latest_github_release_version(*, json_getter: JsonGetter | None = None) -> str:
    getter = http_get_json if json_getter is None else json_getter
    info = getter(GITHUB_LATEST_RELEASE_URL)
    if not isinstance(info, dict):
        raise TypeError("release info must be an object")
    tag_name = info.get("tag_name")
    if not isinstance(tag_name, str):
        raise TypeError("tag_name must be a string")
    prefix = "rust-v"
    if not tag_name.startswith(prefix):
        raise ValueError(f"failed to parse latest tag {tag_name}")
    return tag_name[len(prefix) :]

def fetch_homebrew_cask_version(*, json_getter: JsonGetter | None = None) -> str:
    getter = http_get_json if json_getter is None else json_getter
    info = getter(HOMEBREW_CASK_API_URL)
    if not isinstance(info, dict):
        raise TypeError("homebrew cask info must be an object")
    version = info.get("version")
    if not isinstance(version, str):
        raise TypeError("version must be a string")
    return version

def build_doctor_update_check(
    *,
    check_for_update_on_startup: bool,
    update_action: UpdateAction | None,
    version_file: str | Path,
    current_version: str,
    current_exe: str | Path | None = None,
    env: dict[str, str] | os._Environ[str] | None = None,
    npm_root_check: NpmRootCheck | None = None,
    command_runner: CommandRunner | None = None,
    latest_version: str | None = None,
    latest_error: str | None = None,
) -> DoctorUpdateCheck:
    if not isinstance(check_for_update_on_startup, bool):
        raise TypeError("check_for_update_on_startup must be a bool")
    if not isinstance(current_version, str):
        raise TypeError("current_version must be a string")
    if latest_version is not None and not isinstance(latest_version, str):
        raise TypeError("latest_version must be a string or None")
    if latest_error is not None and not isinstance(latest_error, str):
        raise TypeError("latest_error must be a string or None")

    details = [
        f"check for update on startup: {'true' if check_for_update_on_startup else 'false'}",
        f"update action: {update_action_label(update_action)}",
    ]
    push_cached_version_details(details, version_file)
    status = "ok"
    summary = "update configuration is locally consistent"
    remediation = None
    if npm_root_check is None and doctor.doctor_managed_by_npm(current_exe, env=env):
        npm_root_check = doctor.npm_global_root_check(env=env, command_runner=command_runner)
    if npm_root_check is not None:
        if not isinstance(npm_root_check, NpmRootCheck):
            raise TypeError("npm_root_check must be an NpmRootCheck or None")
        if npm_root_check.kind == "match":
            details.append(f"npm update target: {npm_root_check.package_root}")
        elif npm_root_check.kind == "mismatch":
            status = "fail"
            summary = "update would target a different npm install"
            details.append(f"running package root: {npm_root_check.running_package_root}")
            details.append(f"npm package root: {npm_root_check.npm_package_root}")
            remediation = (
                "Fix PATH or npm prefix so the running package root "
                f"({npm_root_check.running_package_root}) matches the npm global package root "
                f"({npm_root_check.npm_package_root})."
            )
        elif npm_root_check.kind == "missing_package_root":
            status = "warn"
            summary = "npm update target could not be proven"
            remediation = "Reinstall or update Codex so the JS shim provides CODEX_MANAGED_PACKAGE_ROOT."
        elif npm_root_check.kind == "npm_unavailable":
            status = "warn"
            summary = "npm update target could not be inspected"
            details.append(f"npm root -g failed: {npm_root_check.error}")
        else:
            raise ValueError(f"unknown npm root check kind: {npm_root_check.kind}")
    if latest_version is None and latest_error is None:
        try:
            latest_version = fetch_latest_version(update_action)
        except Exception as exc:
            latest_error = str(exc)
    if latest_version is not None:
        push_latest_version_details(details, latest_version, current_version)
    elif latest_error is not None:
        if status == "ok":
            status = "warn"
        push_latest_version_probe_error_details(details, latest_error)
    return DoctorUpdateCheck(status=status, summary=summary, details=tuple(details), remediation=remediation)

def updates_check(
    *,
    check_for_update_on_startup: bool,
    codex_home: str | Path,
    current_version: str,
    current_exe: str | Path | None = None,
    env: dict[str, str] | os._Environ[str] | None = None,
    version_file: str | Path | None = None,
    npm_root_check: NpmRootCheck | None = None,
    command_runner: CommandRunner | None = None,
    latest_version: str | None = None,
    latest_error: str | None = None,
) -> DoctorUpdateCheck:
    resolved_version_file = Path(codex_home) / "version.json" if version_file is None else version_file
    update_action = doctor.detect_update_action(current_exe, env=env, codex_home=codex_home)
    return build_doctor_update_check(
        check_for_update_on_startup=check_for_update_on_startup,
        update_action=update_action,
        version_file=resolved_version_file,
        current_version=current_version,
        current_exe=current_exe,
        env=env,
        npm_root_check=npm_root_check,
        command_runner=command_runner,
        latest_version=latest_version,
        latest_error=latest_error,
    )

def updates_check_from_config(
    config: Mapping[str, Any],
    *,
    codex_home: str | Path,
    current_version: str,
    current_exe: str | Path | None = None,
    env: dict[str, str] | os._Environ[str] | None = None,
    version_file: str | Path | None = None,
    npm_root_check: NpmRootCheck | None = None,
    command_runner: CommandRunner | None = None,
    latest_version: str | None = None,
    latest_error: str | None = None,
) -> DoctorUpdateCheck:
    check_for_update = config.get("check_for_update_on_startup")
    if not isinstance(check_for_update, bool):
        check_for_update = True
    return updates_check(
        check_for_update_on_startup=check_for_update,
        codex_home=codex_home,
        current_version=current_version,
        current_exe=current_exe,
        env=env,
        version_file=version_file,
        npm_root_check=npm_root_check,
        command_runner=command_runner,
        latest_version=latest_version,
        latest_error=latest_error,
    )

