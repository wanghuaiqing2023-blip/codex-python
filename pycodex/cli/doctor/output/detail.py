"""Rust-aligned implementation for codex-cli doctor::output::detail."""



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



from pycodex.cli.doctor import _DOCTOR_DETAIL_LIST_LIMIT, _DOCTOR_DETAIL_PATH_LIMIT



def format_bytes(byte_count: int) -> str:
    kib = 1024.0
    mib = kib * 1024.0
    gib = mib * 1024.0
    value = float(byte_count)
    if value >= gib:
        return f"{value / gib:.2f} GB"
    if value >= mib:
        return f"{value / mib:.2f} MB"
    if value >= kib:
        return f"{value / kib:.2f} KB"
    return f"{int(value)} B"

def _doctor_detail_format_count(count: int) -> str:
    return f"{count:,}"

def _doctor_detail_rollout_summary(value: str) -> str | None:
    try:
        files_text, rest = value.split(" files, ", 1)
        total_text, rest = rest.split(" total bytes, ", 1)
        average_text, _suffix = rest.split(" average bytes", 1)
        files = int(files_text.strip())
        total_bytes = int(total_text.strip())
        average_bytes = int(average_text.strip())
    except (ValueError, AttributeError):
        return None
    return (
        f"{_doctor_detail_format_count(files)} files "
        f"\u00b7 {format_bytes(total_bytes)} "
        f"(avg {format_bytes(average_bytes)})"
    )

def _doctor_detail_list_limit() -> int:
    return _DOCTOR_DETAIL_LIST_LIMIT

def _doctor_detail_path_limit() -> int:
    return _DOCTOR_DETAIL_PATH_LIMIT

def _doctor_detail_humanize_timestamp(value: str) -> str | None:
    if len(value) < 17 or not value.endswith("Z"):
        return None
    if "T" not in value:
        return None
    date, time_part = value.split("T", 1)
    hour_minute = time_part[:5]
    if len(hour_minute) < 5:
        return None
    return f"{date} {hour_minute} UTC"

def _doctor_detail_looks_like_path(value: str) -> bool:
    return (
        value.startswith("/")
        or value.startswith("~/")
        or value.startswith("./")
        or value.startswith("../")
    )

def _doctor_detail_middle_truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    head_len = max_chars // 2
    tail_len = max(max_chars - (head_len + 1), 0)
    head = value[:head_len]
    tail = value[len(value) - tail_len:] if tail_len else ""
    return f"{head}\u2026{tail}"

def _doctor_detail_home_shortened_path(path: str, home: str | None = None) -> str:
    resolved_home = os.environ.get("HOME") if home is None else home
    if not resolved_home:
        return path
    if path == resolved_home:
        return "~"
    prefix = f"{resolved_home}/"
    if path.startswith(prefix):
        return f"~/{path[len(prefix):]}"
    return path

def _doctor_detail_shorten_path_prefix(value: str, home: str | None = None) -> str:
    if " (" in value:
        path, suffix_tail = value.split(" (", 1)
        suffix = f" ({suffix_tail}"
    else:
        path = value
        suffix = ""
    shortened_home = _doctor_detail_home_shortened_path(path, home)
    shortened = _doctor_detail_middle_truncate(shortened_home, _DOCTOR_DETAIL_PATH_LIMIT)
    return f"{shortened}{suffix}"

def _doctor_detail_humanize_value(value: str, home: str | None = None) -> str:
    if _doctor_detail_looks_like_path(value):
        return _doctor_detail_shorten_path_prefix(value, home)
    timestamp = _doctor_detail_humanize_timestamp(value)
    if timestamp is not None:
        return timestamp
    return value

def _doctor_detail_display_label(label: str) -> str:
    if label == "codex-linux-sandbox helper":
        return "linux helper"
    if label == "optional reachability failed":
        return "optional reachability"
    if label == "check for update on startup":
        return "startup update check"
    return label

def _doctor_detail_yes_no(value: str) -> str:
    return "yes" if value == "true" else "no"

def _doctor_detail_is_falsy(value: str) -> bool:
    return value.strip().lower() in {
        "",
        "false",
        "none",
        "not set",
        "unknown",
        "missing",
        "absent",
        "no",
        "-",
    }

def _doctor_detail_list_items(value: str) -> list[str]:
    if _doctor_detail_is_falsy(value):
        return []
    return [item.strip() for item in value.split(",") if item.strip()]

def _doctor_detail_override_names(items: list[str]) -> list[str]:
    return [item.split("=", 1)[0] for item in items]

def _doctor_detail_rollout_files_and_bytes(value: str) -> tuple[int, int] | None:
    try:
        files_text, rest = value.split(" files, ", 1)
        total_text, _rest = rest.split(" total bytes, ", 1)
        return (int(files_text.strip()), int(total_text.strip()))
    except (ValueError, AttributeError):
        return None

def _doctor_detail_parse_detail(detail: str) -> tuple[str, str]:
    if ": " in detail:
        label, value = detail.split(": ", 1)
        return (label, value)
    return ("", detail)

def _doctor_detail_numbered_values(parsed: list[tuple[str, str]], prefix: str) -> list[str]:
    return [value for label, value in parsed if label.startswith(prefix)]

def _doctor_detail_value(parsed: list[tuple[str, str]], label: str) -> str | None:
    for detail_label, value in parsed:
        if detail_label == label:
            return value
    return None

def _doctor_detail_push_list_row_value(items: list[str], *, show_all: bool) -> str:
    limit = len(items) if show_all else min(len(items), _DOCTOR_DETAIL_LIST_LIMIT)
    value = ", ".join(items[:limit])
    if limit < len(items):
        value += ", \u2026 (full list with --all)"
    return value

def _doctor_detail_database_row_value(path: str, integrity: str | None = None) -> str:
    if integrity is None:
        return path
    return f"{path} \u00b7 integrity {integrity}"

def _doctor_detail_feature_flags_summary_value(
    enabled_count_value: str | None,
    override_value: str | None,
    *,
    show_all: bool,
) -> str:
    try:
        enabled_count = int(enabled_count_value) if enabled_count_value is not None else 0
    except ValueError:
        enabled_count = 0
    overrides = _doctor_detail_list_items("none" if override_value is None else override_value)
    hint = " (full list with --all)" if not show_all and enabled_count > 0 else ""
    return f"{enabled_count} enabled \u00b7 {len(overrides)} overridden{hint}"

def _doctor_detail_managed_by_value(managed_by_npm: str, managed_by_bun: str, package_root: str) -> str:
    root = "\u2014" if _doctor_detail_is_falsy(package_root) else package_root
    return (
        f"npm: {_doctor_detail_yes_no(managed_by_npm)} "
        f"\u00b7 bun: {_doctor_detail_yes_no(managed_by_bun)} "
        f"\u00b7 package root {root}"
    )

def _doctor_detail_model_row_value(model: str, provider: str | None = None) -> str:
    if provider is None:
        return model
    return f"{model} \u00b7 {provider}"

def _doctor_detail_issue_remedies(remedies: list[str | None]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for remedy in remedies:
        if remedy is None or remedy in seen:
            continue
        seen.add(remedy)
        out.append(remedy)
    return out

def _doctor_detail_issue_expected_for_label(
    issues: list[dict[str, object]],
    label: str,
) -> str | None:
    for issue in issues:
        fields = issue.get("fields", [])
        if not isinstance(fields, list):
            continue
        for field in fields:
            field_text = str(field)
            if _doctor_detail_display_label(field_text) == label or field_text == label:
                expected = issue.get("expected")
                return None if expected is None else str(expected)
    return None

def _doctor_detail_attach_issue_expected(
    label: str,
    expected: str | None,
    issues: list[dict[str, object]],
) -> str | None:
    if expected is not None:
        return expected
    return _doctor_detail_issue_expected_for_label(issues, label)

def _doctor_detail_generic_kind_and_label(label: str, value: str) -> tuple[str, str | None, str]:
    if label == "":
        return ("bullet", None, value)
    return ("row", _doctor_detail_display_label(label), value)

def _doctor_detail_remaining_details(
    parsed: list[tuple[str, str]],
    consumed_labels: list[str],
    consumed_prefixes: list[str],
) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    for label, value in parsed:
        if value == "ignored inherited package-manager launch env for cargo-built binary":
            continue
        if label in consumed_labels:
            continue
        if any(label.startswith(prefix) for prefix in consumed_prefixes):
            continue
        out.append(_doctor_detail_generic_kind_and_label(label, value))
    return out

def _doctor_detail_path_entry_values(entries: list[str], *, show_all: bool) -> list[tuple[str, str]]:
    if not entries:
        return []
    total = len(entries)
    shown = total if show_all else min(total, 3)
    out: list[tuple[str, str]] = [(f"PATH entries ({total})", entries[0])]
    out.extend(("continuation", entry) for entry in entries[1:shown])
    if shown < total:
        out.append(("continuation", "\u2026 (full list with --all)"))
    return out

def _doctor_detail_system_rows(parsed: list[tuple[str, str]]) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    for source_label, display in (
        ("os", "os"),
        ("os language", "OS language"),
        ("LC_ALL", "LC_ALL"),
        ("LC_CTYPE", "LC_CTYPE"),
        ("LANG", "LANG"),
    ):
        value = _doctor_detail_value(parsed, source_label)
        if value is not None:
            out.append(("row", display, value))
    out.extend(
        _doctor_detail_remaining_details(
            parsed,
            ["os", "os type", "os version", "os language", "LC_ALL", "LC_CTYPE", "LANG"],
            [],
        )
    )
    return out

def _doctor_detail_runtime_rows(parsed: list[tuple[str, str]]) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    for source_label, display in (
        ("version", "version"),
        ("install method", "install method"),
        ("commit", "commit"),
        ("current executable", "executable"),
    ):
        value = _doctor_detail_value(parsed, source_label)
        if value is not None:
            out.append(("row", display, value))
    out.extend(
        _doctor_detail_remaining_details(
            parsed,
            ["version", "platform", "install method", "commit", "current executable"],
            [],
        )
    )
    return out

def _doctor_detail_title_rows(parsed: list[tuple[str, str]]) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    for source_label, display in (
        ("terminal title source", "title source"),
        ("terminal title items", "title items"),
        ("terminal title activity", "activity item"),
        ("terminal title project source", "project source"),
        ("terminal title project value", "project value"),
    ):
        value = _doctor_detail_value(parsed, source_label)
        if value is not None:
            out.append(("row", display, value))
    out.extend(
        _doctor_detail_remaining_details(
            parsed,
            [
                "terminal title source",
                "terminal title items",
                "terminal title activity",
                "terminal title project source",
                "terminal title project value",
            ],
            [],
        )
    )
    return out

def _doctor_detail_state_rows(parsed: list[tuple[str, str]]) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    for source_label, display in (
        ("CODEX_HOME", "CODEX_HOME"),
        ("log dir", "log dir"),
        ("sqlite home", "sqlite home"),
    ):
        value = _doctor_detail_value(parsed, source_label)
        if value is not None:
            out.append(("row", display, value))
    for label in ("state DB", "log DB", "goals DB", "memories DB"):
        path = _doctor_detail_value(parsed, label)
        if path is not None:
            out.append(("row", label, _doctor_detail_database_row_value(path, _doctor_detail_value(parsed, f"{label} integrity"))))
    for source_label, display in (
        ("active rollout files", "active rollouts"),
        ("archived rollout files", "archived rollouts"),
    ):
        value = _doctor_detail_value(parsed, source_label)
        if value is not None:
            out.append(("row", display, _doctor_detail_rollout_summary(value) or value))
    out.extend(
        _doctor_detail_remaining_details(
            parsed,
            [
                "CODEX_HOME",
                "log dir",
                "sqlite home",
                "state DB",
                "log DB",
                "goals DB",
                "state DB integrity",
                "log DB integrity",
                "goals DB integrity",
                "memories DB",
                "memories DB integrity",
                "active rollout files",
                "archived rollout files",
            ],
            [],
        )
    )
    return out

def _doctor_detail_git_rows(parsed: list[tuple[str, str]], *, show_all: bool) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    for source_label, display in (
        ("selected git", "selected git"),
        ("git version", "version"),
        ("git exec path", "exec path"),
        ("repo detected", "repo detected"),
        ("repo root", "repo root"),
        (".git entry", ".git entry"),
        ("git branch", "branch"),
        ("core.fsmonitor", "core.fsmonitor"),
    ):
        value = _doctor_detail_value(parsed, source_label)
        if value is not None:
            out.append(("row", display, value))
    out.extend(("row", label, value) if label.startswith("PATH entries") else (label, None, value) for label, value in _doctor_detail_path_entry_values(_doctor_detail_numbered_values(parsed, "PATH git #"), show_all=show_all))
    out.extend(
        _doctor_detail_remaining_details(
            parsed,
            [
                "selected git",
                "PATH git entries",
                "git version",
                "git exec path",
                "git build options",
                "repo detected",
                "repo root",
                ".git entry",
                "git branch",
                "core.fsmonitor",
            ],
            ["PATH git #"],
        )
    )
    return out

def _doctor_detail_install_rows(parsed: list[tuple[str, str]], *, show_all: bool) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    context = _doctor_detail_value(parsed, "install context")
    if context is not None:
        out.append(("row", "context", context))
    if any(value == "ignored inherited package-manager launch env for cargo-built binary" for _label, value in parsed):
        out.append(("bullet", None, "ignored inherited package-manager launch env for cargo-built binary"))
    npm = _doctor_detail_value(parsed, "managed by npm") or "false"
    bun = _doctor_detail_value(parsed, "managed by bun") or "false"
    package_root = _doctor_detail_value(parsed, "managed package root") or "not set"
    out.append(("row", "managed by", _doctor_detail_managed_by_value(npm, bun, package_root)))
    out.extend(("row", label, value) if label.startswith("PATH entries") else (label, None, value) for label, value in _doctor_detail_path_entry_values(_doctor_detail_numbered_values(parsed, "PATH codex #"), show_all=show_all))
    out.extend(
        _doctor_detail_remaining_details(
            parsed,
            [
                "current executable",
                "install context",
                "managed by npm",
                "managed by bun",
                "managed package root",
                "PATH codex entries",
            ],
            ["PATH codex #"],
        )
    )
    return out

def _doctor_detail_config_rows(parsed: list[tuple[str, str]], *, show_all: bool) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    model = _doctor_detail_value(parsed, "model")
    if model is not None:
        out.append(("row", "model", _doctor_detail_model_row_value(model, _doctor_detail_value(parsed, "model provider"))))
    for source_label, display in (
        ("cwd", "cwd"),
        ("config.toml", "config.toml"),
        ("config.toml parse", "config.toml parse"),
        ("config.toml read", "config.toml read"),
        ("mcp servers", "MCP servers"),
    ):
        value = _doctor_detail_value(parsed, source_label)
        if value is not None:
            out.append(("row", display, value))
    out.append(("row", "feature flags", _doctor_detail_feature_flags_summary_value(
        _doctor_detail_value(parsed, "feature flags enabled"),
        _doctor_detail_value(parsed, "feature flag overrides"),
        show_all=show_all,
    )))
    for label, value in parsed:
        if label == "legacy feature flag":
            out.append(("row", "legacy alias", value))
    out.extend(
        _doctor_detail_remaining_details(
            parsed,
            [
                "CODEX_HOME",
                "cwd",
                "model",
                "model provider",
                "log dir",
                "sqlite home",
                "mcp servers",
                "feature flags enabled",
                "enabled feature flags",
                "feature flag overrides",
                "legacy feature flag",
                "config.toml",
                "config.toml parse",
                "config.toml read",
            ],
            [],
        )
    )
    return out

def _doctor_detail_rows_for_category(
    category: str,
    parsed: list[tuple[str, str]],
    *,
    show_all: bool = False,
) -> list[tuple[str, str | None, str]]:
    if category == "system":
        return _doctor_detail_system_rows(parsed)
    if category == "runtime":
        return _doctor_detail_runtime_rows(parsed)
    if category == "install":
        return _doctor_detail_install_rows(parsed, show_all=show_all)
    if category == "git":
        return _doctor_detail_git_rows(parsed, show_all=show_all)
    if category == "title":
        return _doctor_detail_title_rows(parsed)
    if category == "config":
        return _doctor_detail_config_rows(parsed, show_all=show_all)
    if category == "state":
        return _doctor_detail_state_rows(parsed)
    return [_doctor_detail_generic_kind_and_label(label, value) for label, value in parsed]

def _doctor_detail_value_from_details(details: list[str], label: str) -> str | None:
    from pycodex.cli.doctor.output import redact_detail

    parsed = [_doctor_detail_parse_detail(redact_detail(detail)) for detail in details]
    return _doctor_detail_value(parsed, label)

def _doctor_detail_humanize_detail(kind: str, label: str | None, value: str, home: str | None = None) -> tuple[str, str | None, str]:
    if kind == "remedy":
        return (kind, label, value)
    return (kind, label, _doctor_detail_humanize_value(value, home))

def _doctor_detail_lines_for_check(
    category: str,
    details: list[str],
    issues: list[dict[str, object]],
    *,
    show_all: bool = False,
    home: str | None = None,
) -> list[tuple[str, str | None, str | None, str]]:
    from pycodex.cli.doctor.output import redact_detail

    parsed = [_doctor_detail_parse_detail(redact_detail(detail)) for detail in details]
    rows = _doctor_detail_rows_for_category(category, parsed, show_all=show_all)
    out: list[tuple[str, str | None, str | None, str]] = []
    for kind, label, value in rows:
        expected = _doctor_detail_attach_issue_expected(label or "", None, issues) if kind == "row" else None
        humanized_kind, humanized_label, humanized_value = _doctor_detail_humanize_detail(kind, label, value, home)
        out.append((humanized_kind, humanized_label, humanized_value, expected))
    for remedy in _doctor_detail_issue_remedies([issue.get("remedy") if isinstance(issue.get("remedy"), str) else None for issue in issues]):
        out.append(("remedy", None, remedy, None))
    return out

