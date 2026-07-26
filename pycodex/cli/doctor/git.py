"""Rust-aligned implementation for codex-cli doctor::git."""



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



from pycodex.cli.doctor import DoctorUpdateCheck, GitCommandRunner, _doctor_path_text



@dataclass(frozen=True)
class GitCheckInputs:
    selected_git: Path | None = None
    git_candidates: tuple[Path, ...] = ()
    git_version: str | None = None
    git_exec_path: str | None = None
    git_build_options: str | None = None
    repo_root: Path | None = None
    git_entry: str | None = None
    branch: str | None = None
    core_fsmonitor: str | None = None

def git_check(
    *,
    cwd: str | Path | None = None,
    inputs: GitCheckInputs | None = None,
    selected_git: str | Path | None = None,
    git_candidates: tuple[str | Path, ...] | None = None,
    command_runner: GitCommandRunner | None = None,
    is_windows: bool | None = None,
) -> DoctorUpdateCheck:
    cwd_path = Path.cwd() if cwd is None else Path(cwd)
    if inputs is None:
        selected_git_path = Path(selected_git) if selected_git is not None else _selected_git()
        candidates = (
            tuple(Path(path) for path in git_candidates)
            if git_candidates is not None
            else tuple(_git_candidates())
        )
        runner = _run_git_output if command_runner is None else command_runner
        if selected_git_path is None:
            git_version = None
            git_exec_path = None
            git_build_options = None
            branch = None
            core_fsmonitor = None
        else:
            git_version = runner(selected_git_path, ("--version",), cwd_path)
            git_exec_path = runner(selected_git_path, ("--exec-path",), cwd_path)
            git_build_options = runner(selected_git_path, ("version", "--build-options"), cwd_path)
            branch = runner(selected_git_path, ("rev-parse", "--abbrev-ref", "HEAD"), cwd_path)
            core_fsmonitor = runner(selected_git_path, ("config", "--get", "core.fsmonitor"), cwd_path)
        repo_root = _git_repo_root(cwd_path)
        inputs = GitCheckInputs(
            selected_git=selected_git_path,
            git_candidates=candidates,
            git_version=git_version,
            git_exec_path=git_exec_path,
            git_build_options=git_build_options,
            repo_root=repo_root,
            git_entry=_git_entry_summary(repo_root) if repo_root is not None else None,
            branch=branch,
            core_fsmonitor=core_fsmonitor,
        )
    details: list[str] = []
    details.append(
        f"selected git: {_doctor_path_text(inputs.selected_git)}"
        if inputs.selected_git is not None
        else "selected git: not found"
    )
    details.append(f"PATH git entries: {len(inputs.git_candidates)}")
    for index, path in enumerate(inputs.git_candidates, start=1):
        details.append(f"PATH git #{index}: {_doctor_path_text(path)}")
    _push_optional_detail(details, "git version", inputs.git_version)
    _push_optional_detail(details, "git exec path", inputs.git_exec_path)
    _push_optional_detail(details, "git build options", inputs.git_build_options)
    if inputs.repo_root is None:
        details.append("repo detected: false")
    else:
        details.append("repo detected: true")
        details.append(f"repo root: {_doctor_path_text(inputs.repo_root)}")
    _push_optional_detail(details, ".git entry", inputs.git_entry)
    _push_optional_detail(details, "git branch", _normalized_git_branch(inputs.branch))
    _push_optional_detail(details, "core.fsmonitor", inputs.core_fsmonitor or None)

    status = "ok"
    summary = _git_summary(inputs)
    remediation = None
    if inputs.selected_git is not None and inputs.git_version is None:
        status = "warn"
        summary = "Git executable found but could not be run"
        remediation = "Fix the selected Git executable or PATH so Codex can inspect Git metadata."
    elif inputs.selected_git is None and inputs.repo_root is not None:
        status = "warn"
        summary = "Git repository detected but git executable was not found"
        remediation = "Install Git or fix PATH so Codex can inspect repository metadata."
    else:
        warning = _old_windows_git_warning(inputs.git_version, os.name == "nt" if is_windows is None else is_windows)
        if warning is not None:
            status = "warn"
            summary = warning
            remediation = "Update Git for Windows or the bundled Git executable Codex resolves first."
    return DoctorUpdateCheck(status=status, summary=summary, details=tuple(details), remediation=remediation)

def _push_optional_detail(details: list[str], label: str, value: str | None) -> None:
    if value is not None:
        details.append(f"{label}: {value}")

def _selected_git() -> Path | None:
    selected = shutil.which("git")
    return Path(selected) if selected else None

def _git_candidates() -> list[Path]:
    seen: set[Path] = set()
    candidates: list[Path] = []
    path_exts = [""]
    if os.name == "nt":
        path_exts = [ext.lower() for ext in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(os.pathsep) if ext]
    for raw_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not raw_dir:
            continue
        directory = Path(raw_dir)
        names = ["git"] if os.name != "nt" else [f"git{ext}" for ext in path_exts]
        for name in names:
            candidate = directory / name
            if candidate.exists() and candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
    return candidates

def _run_git_output(git_path: Path, args: tuple[str, ...], cwd: Path) -> str | None:
    try:
        output = subprocess.run(
            [str(git_path), *args],
            cwd=cwd,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if output.returncode != 0:
        return None
    normalized = "; ".join(
        line.strip()
        for line in output.stdout.decode("utf-8", errors="replace").splitlines()
        if line.strip()
    )
    return normalized or None

def _git_repo_root(cwd: Path) -> Path | None:
    current = cwd if cwd.is_dir() else cwd.parent
    while True:
        if (current / ".git").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent

def _git_entry_summary(repo_root: Path) -> str:
    entry = repo_root / ".git"
    try:
        if entry.is_dir():
            return "directory"
        if entry.is_file():
            try:
                contents = entry.read_text(encoding="utf-8")
            except OSError:
                return "file"
            if contents.startswith("gitdir:"):
                return f"file -> {contents.removeprefix('gitdir:').strip()}"
            return "file"
        if entry.exists():
            return "other"
        return "missing"
    except OSError as exc:
        return f"unreadable ({exc})"

def _normalized_git_branch(branch: str | None) -> str | None:
    if branch == "HEAD":
        return "detached HEAD"
    if branch:
        return branch
    return None

def _git_summary(inputs: GitCheckInputs) -> str:
    if inputs.git_version is not None:
        return inputs.git_version
    if inputs.selected_git is not None:
        return "git executable found; version unavailable"
    return "git executable not found"

def _old_windows_git_warning(version: str | None, is_windows: bool) -> str | None:
    if not is_windows or version is None:
        return None
    if "msysgit" in version.lower():
        return "old msysgit installation may corrupt Windows TUI rendering"
    parsed = _parse_git_version(version)
    if parsed is not None:
        major, minor, _patch = parsed
        if major < 2 or (major == 2 and minor <= 34):
            return "old Git for Windows may corrupt Windows TUI rendering"
    return None

def _parse_git_version(version: str) -> tuple[int, int, int] | None:
    if not version.startswith("git version "):
        return None
    numeric = version.removeprefix("git version ").split()[0].split(".windows.")[0]
    parts = numeric.split(".")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2] if len(parts) > 2 else "0")
    except ValueError:
        return None

