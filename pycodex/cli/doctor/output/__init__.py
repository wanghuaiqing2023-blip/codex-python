"""Rust-aligned implementation for codex-cli doctor::output."""



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



from pycodex.cli.doctor.output.detail import format_bytes, _doctor_detail_format_count, _doctor_detail_is_falsy, _doctor_detail_rollout_files_and_bytes, _doctor_detail_value_from_details

from pycodex.cli.doctor import U64_MAX, _doctor_check_identity, _doctor_generated_at, _redact_urls, _structured_redacted_details



def _doctor_output_ascii_status_marker(status: str) -> str:
    normalized = status.replace("-", "_").lower()
    if normalized == "ok":
        return "[ok]"
    if normalized == "update":
        return "[up]"
    if normalized in {"note", "warning", "warn"}:
        return "[!!]"
    if normalized == "fail":
        return "[XX]"
    if normalized == "idle":
        return "[--]"
    raise ValueError(f"Unknown doctor output status: {status}")

def separator() -> str:
    return "-" * 61

def _doctor_output_column_widths() -> dict[str, int]:
    return {"name": 12, "detail_label": 24}

def redact_detail(detail: str) -> str:
    lower = detail.lower()
    label = lower.split(":", 1)[0]
    if "env var" in label:
        return _redact_urls(detail)
    if ": " in detail:
        name, value = detail.split(": ", 1)
        normalized_name = name.strip().lower()
        secret_keys = (
            "openai_api_key",
            "codex_api_key",
            "codex_access_token",
            "authorization",
            "bearer_token",
            "token",
            "secret",
        )
        if any(key in normalized_name for key in secret_keys):
            return f"{name}: <redacted>"
        if value.strip().lower() in {"true", "false", "yes", "no", "present", "absent", "missing", "not set"}:
            return _redact_urls(detail)
    return _redact_urls(detail)

def _doctor_json_status(status: Any) -> str:
    value = str(status)
    normalized = value.strip().lower()
    if normalized == "warn":
        return "warning"
    if normalized in {"ok", "warning", "fail"}:
        return normalized
    return "warning"

def _doctor_overall_status(checks: Any) -> str:
    statuses: list[str] = []
    for check in checks if isinstance(checks, list | tuple) else []:
        if isinstance(check, Mapping):
            statuses.append(_doctor_json_status(check.get("status", "warning")))
        else:
            statuses.append(_doctor_json_status(getattr(check, "status", "warning")))
    if any(status == "fail" for status in statuses):
        return "fail"
    if any(status == "warning" for status in statuses):
        return "warning"
    return "ok"

def _doctor_duration_ms(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return min(max(value, 0), U64_MAX)
    if isinstance(value, str):
        try:
            return min(max(int(value), 0), U64_MAX)
        except ValueError:
            return 0
    return 0

def _doctor_json_string(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)

def _redacted_doctor_issue_mapping(issue: Mapping[str, Any]) -> dict[str, Any]:
    fields = issue.get("fields", [])
    if not isinstance(fields, list):
        fields = []
    return {
        "severity": _doctor_json_status(issue.get("severity", "warn")),
        "cause": redact_detail(str(issue.get("cause", ""))),
        "measured": redact_detail(str(issue["measured"])) if issue.get("measured") is not None else None,
        "expected": redact_detail(str(issue["expected"])) if issue.get("expected") is not None else None,
        "remedy": redact_detail(str(issue["remedy"])) if issue.get("remedy") is not None else None,
        "fields": [redact_detail(str(field)) for field in fields],
    }

def _redacted_doctor_issues(issues: Any) -> list[dict[str, Any]]:
    if not isinstance(issues, list):
        return []
    return [_redacted_doctor_issue_mapping(issue) for issue in issues if isinstance(issue, Mapping)]

def redacted_doctor_check_mapping(check: dict[str, Any], *, check_key: str | None = None) -> dict[str, Any]:
    details, notes = _structured_redacted_details(check.get("details", []))
    default_id, default_category = _doctor_check_identity(check_key)
    mapping: dict[str, Any] = {
        "id": _doctor_json_string(check.get("id"), default_id),
        "category": _doctor_json_string(check.get("category"), default_category),
        "status": _doctor_json_status(check.get("status", "warn")),
        "summary": _doctor_json_string(check.get("summary")),
        "details": details,
    }
    issues = _redacted_doctor_issues(check.get("issues"))
    if issues:
        mapping["issues"] = issues
    if notes:
        mapping["notes"] = notes
    remediation = check.get("remediation")
    if isinstance(remediation, str):
        mapping["remediation"] = redact_detail(remediation)
    else:
        mapping["remediation"] = None
    mapping["durationMs"] = _doctor_duration_ms(check.get("durationMs", check.get("duration_ms", 0)))
    return mapping

def redacted_doctor_checks_mapping(checks: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    redacted: dict[str, dict[str, Any]] = {}
    for key, value in checks.items():
        check = redacted_doctor_check_mapping(value, check_key=key)
        redacted[str(check.get("id", key))] = check
    return dict(sorted(redacted.items()))

def redacted_doctor_report_mapping(
    *,
    checks: dict[str, dict[str, Any]],
    overall_status: str,
    codex_version: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "generatedAt": _doctor_json_string(generated_at, _doctor_generated_at()),
        "overallStatus": _doctor_json_status(overall_status),
        "codexVersion": _doctor_json_string(codex_version),
        "checks": redacted_doctor_checks_mapping(checks),
    }

def _doctor_output_groups() -> list[tuple[str, tuple[str, ...]]]:
    return [
        ("Environment", ("system", "runtime", "install", "search", "git", "terminal", "title", "state", "threads")),
        ("Configuration", ("config", "auth", "mcp", "sandbox")),
        ("Updates", ("updates",)),
        ("Connectivity", ("network", "websocket", "reachability")),
        ("Background Server", ("app-server",)),
    ]

def _doctor_output_display_status(category: str, status: str, details: list[str]) -> str:
    normalized = status.strip().lower()
    if category == "app-server" and normalized == "ok" and "status: not running" in details:
        return "idle"
    if normalized in {"ok", "warning", "fail"}:
        return normalized
    if normalized == "warn":
        return "warning"
    return "warning"

def _doctor_output_overall_status_label(status: str) -> str:
    normalized = status.strip().lower()
    if normalized == "ok":
        return "ok"
    if normalized in {"warning", "warn"}:
        return "degraded"
    if normalized == "fail":
        return "failed"
    return "degraded"

def _doctor_output_issue_summary(check_summary: str, issue_causes: list[str]) -> str:
    if not issue_causes:
        return check_summary
    if len(issue_causes) == 1:
        return issue_causes[0]
    return f"{len(issue_causes)} issues - {'; '.join(issue_causes[:2])}"

def _doctor_output_row_description(
    status: str,
    summary: str,
    issue_causes: list[str],
    remediation: str | None = None,
    *,
    ascii_output: bool = False,
) -> str:
    normalized = status.strip().lower()
    is_problem = normalized in {"warning", "warn", "fail"}
    if is_problem and issue_causes:
        return _doctor_output_issue_summary(summary, issue_causes)
    if is_problem and remediation is not None:
        dash = " - " if ascii_output else " \u2014 "
        return f"{summary}{dash}{remediation}"
    return summary

def _doctor_output_update_note_summary(details: list[str], codex_version: str) -> str | None:
    latest_status = _doctor_detail_value_from_details(details, "latest version status")
    if latest_status is None or "newer version is available" not in latest_status:
        return None
    latest = (
        _doctor_detail_value_from_details(details, "latest version")
        or _doctor_detail_value_from_details(details, "cached latest version")
        or "newer version"
    )
    parenthetical = f"current {codex_version}"
    dismissed = _doctor_detail_value_from_details(details, "dismissed version")
    if dismissed is not None and not _doctor_detail_is_falsy(dismissed):
        parenthetical += f", dismissed {dismissed}"
    return f"{latest} available ({parenthetical})"

def _doctor_output_rollout_note_summary(details: list[str]) -> str | None:
    active = _doctor_detail_value_from_details(details, "active rollout files")
    if active is None:
        return None
    parsed = _doctor_detail_rollout_files_and_bytes(active)
    if parsed is None:
        return None
    files, bytes_on_disk = parsed
    if files < 1000 and bytes_on_disk < 1024 * 1024 * 1024:
        return None
    return f"{_doctor_detail_format_count(files)} active files \u00b7 {format_bytes(bytes_on_disk)} on disk"

def _doctor_output_sandbox_note_summary(details: list[str]) -> str | None:
    filesystem = _doctor_detail_value_from_details(details, "filesystem sandbox")
    network = _doctor_detail_value_from_details(details, "network sandbox")
    if filesystem is None or network is None:
        return None
    if filesystem == "restricted" and network == "restricted":
        return None
    return f"filesystem {filesystem} \u00b7 network {network}"

def _doctor_output_auth_reachability_note_summary(websocket_details: list[str], reachability_details: list[str]) -> str | None:
    auth_mode = _doctor_detail_value_from_details(websocket_details, "auth mode")
    reachability_mode = _doctor_detail_value_from_details(reachability_details, "reachability mode")
    if auth_mode is None or reachability_mode is None:
        return None
    if "chatgpt" in auth_mode.lower() and "api key" in reachability_mode.lower():
        return "mixed auth signals: ChatGPT login plus API key env var; HTTP reachability uses API-key mode"
    return None

def _doctor_output_notes_order(categories: list[str]) -> list[str]:
    ordered: list[str] = []
    if "updates" in categories:
        ordered.append("updates")
    if "state" in categories:
        ordered.append("rollouts")
    if "sandbox" in categories:
        ordered.append("sandbox")
    ordered.extend(f"non-ok:{category}" for category in categories)
    if "websocket" in categories and "reachability" in categories:
        ordered.append("auth")
    return ordered

def _doctor_output_footer_lines(*, show_details: bool) -> list[str]:
    if show_details:
        return [
            "--summary compact output --all expand truncated lists",
            "--json redacted report",
        ]
    return [
        "Run codex doctor without --summary for detailed diagnostics.",
        "--all expand truncated lists --json redacted report",
    ]

def _doctor_output_header_suffix(codex_version: str, runtime_details: list[str] | None = None) -> str:
    version = f"v{codex_version}"
    if runtime_details is None:
        return version
    platform_value = _doctor_detail_value_from_details(runtime_details, "platform")
    if platform_value is None:
        return version
    return f"{version} \u00b7 {platform_value}"

def _doctor_output_summary_line_text(
    *,
    ok: int,
    idle: int,
    notes: int,
    warning: int,
    fail: int,
    overall_status: str,
    ascii_output: bool = False,
) -> str:
    parts = [f"{ok} ok"]
    if idle > 0:
        parts.append(f"{idle} idle")
    if notes > 0:
        parts.append(f"{notes} notes")
    parts.append(f"{warning} warn")
    parts.append(f"{fail} fail")
    separator = " | " if ascii_output else " \u00b7 "
    return f"{separator.join(parts)} {_doctor_output_overall_status_label(overall_status)}"

def _doctor_output_checks_for_group(
    checks: list[tuple[str, str]],
    group_keys: tuple[str, ...],
) -> list[tuple[str, str]]:
    """Return checks matching group keys in Rust output.rs group-key order."""
    return [check for key in group_keys for check in checks if check[0] == key]

def _doctor_output_actionable_note_summary(
    summary: str,
    *,
    issue_summary: str | None = None,
    remediation: str | None = None,
) -> str:
    """Mirror Rust output.rs actionable_note_summary text precedence."""
    if issue_summary is not None:
        return issue_summary
    if remediation is not None:
        return f"{summary} - {remediation}"
    return summary

def _doctor_output_non_ok_notes(checks: list[dict[str, str | None]]) -> list[tuple[str, str]]:
    """Mirror Rust output.rs non_ok_notes warning/fail filtering."""
    notes: list[tuple[str, str]] = []
    for check in checks:
        status = check.get("status")
        if status not in {"warning", "fail"}:
            continue
        summary = check.get("summary") or ""
        notes.append(
            (
                _doctor_output_display_status("", str(status), {}),
                _doctor_output_actionable_note_summary(
                    summary,
                    issue_summary=check.get("issue_summary"),
                    remediation=check.get("remediation"),
                ),
            )
        )
    return notes

def _doctor_output_ascii_status_marker_slot(status: str) -> str:
    """Mirror Rust output.rs status_marker_slot for ascii status markers."""
    return f"{_doctor_output_ascii_status_marker(status)} "

def _doctor_output_ascii_detail_marker(is_issue: bool) -> str:
    """Mirror Rust output.rs detail_marker for ascii output."""
    return ">" if is_issue else " "

def _doctor_output_style_update_note_summary_no_color(summary: str) -> str:
    """Mirror Rust output.rs style_update_note_summary when color is disabled."""
    return summary

def _doctor_output_count_label_no_color(count: int, label: str, status: str) -> str:
    """Mirror Rust output.rs count_label text when color styling is disabled."""
    if status not in {"ok", "update", "note", "warning", "fail", "idle"}:
        raise ValueError(f"unknown display status: {status}")
    return f"{count} {label}"

def _doctor_output_styled_overall_status_no_color(label: str, status: str) -> str:
    """Mirror Rust output.rs styled_overall_status when color is disabled."""
    if status not in {"ok", "warning", "fail"}:
        raise ValueError(f"unknown check status: {status}")
    return label

def _doctor_output_style_update_note_summary_from_note_no_color(
    status: str, summary: str
) -> str:
    """Mirror Rust output.rs style_note_summary update/no-color path."""
    if status != "update":
        raise ValueError("this helper only covers the update status no-color path")
    return _doctor_output_style_update_note_summary_no_color(summary)

def _doctor_output_highlight_actions_no_color(text: str) -> str:
    """Mirror Rust output.rs highlight_actions when color is disabled."""
    return text

def _doctor_output_highlight_flags_no_color(text: str) -> str:
    """Mirror Rust output.rs highlight_flags when styling has no visible effect."""
    return text

def _doctor_output_is_safe_presence_value(value: str) -> bool:
    """Mirror Rust output.rs is_safe_presence_value."""
    return value.strip().lower() in {
        "true",
        "false",
        "yes",
        "no",
        "present",
        "absent",
        "missing",
        "not set",
    }

def _doctor_output_redact_url_path(path: str) -> str:
    """Mirror Rust output.rs redact_url_path."""
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return path
    first_segment = segments[0]
    if len(segments) > 1:
        return f"/{first_segment}/<redacted>"
    return path

def _doctor_output_redact_url_token(token: str) -> str:
    """Mirror Rust output.rs redact_url_token for a single token."""
    scheme_end = token.find("://")
    if scheme_end == -1:
        return token
    suffix_start = len(token)
    trailing = set(" \t\n\r.,;:)]")
    while suffix_start > scheme_end + 3 and token[suffix_start - 1] in trailing:
        suffix_start -= 1
    body = token[:suffix_start]
    suffix = token[suffix_start:]
    scheme_prefix_end = scheme_end + 3
    rest = body[scheme_prefix_end:]
    authority_end_offset = len(rest)
    for separator in ("/", "?", "#"):
        index = rest.find(separator)
        if index != -1:
            authority_end_offset = min(authority_end_offset, index)
    authority_end = scheme_prefix_end + authority_end_offset
    authority = body[scheme_prefix_end:authority_end]
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]
    path = body[authority_end:]
    query_index = len(path)
    for separator in ("?", "#"):
        index = path.find(separator)
        if index != -1:
            query_index = min(query_index, index)
    path = _doctor_output_redact_url_path(path[:query_index])
    return f"{body[:scheme_prefix_end]}{authority}{path}{suffix}"

def _doctor_output_redact_urls(detail: str) -> str:
    """Mirror Rust output.rs redact_urls over whitespace-inclusive tokens."""
    out: list[str] = []
    start = 0
    for index, char in enumerate(detail):
        if char.isspace():
            out.append(_doctor_output_redact_url_token(detail[start : index + 1]))
            start = index + 1
    if start < len(detail):
        out.append(_doctor_output_redact_url_token(detail[start:]))
    return "".join(out)

def _doctor_output_redact_detail_env_var_branch(detail: str) -> str:
    """Mirror Rust output.rs redact_detail branch for labels containing env var."""
    label = detail.lower().split(":", 1)[0]
    if "env var" not in label:
        raise ValueError("this helper only covers redact_detail env var labels")
    return _doctor_output_redact_urls(detail)

def _doctor_output_redact_detail_safe_presence_branch(detail: str) -> str:
    """Mirror Rust output.rs redact_detail safe-presence value branch."""
    if ": " not in detail:
        raise ValueError("this helper only covers redact_detail details with ': '")
    _, value = detail.split(": ", 1)
    if not _doctor_output_is_safe_presence_value(value):
        raise ValueError("this helper only covers safe presence values")
    return _doctor_output_redact_urls(detail)

def _doctor_output_redact_detail_secret_key_branch(detail: str) -> str:
    """Mirror Rust output.rs redact_detail secret-key branch."""
    secret_keys = {
        "openai_api_key",
        "codex_api_key",
        "codex_access_token",
        "authorization",
        "bearer_token",
        "token",
        "secret",
    }
    lower = detail.lower()
    if not any(key in lower for key in secret_keys):
        raise ValueError("this helper only covers redact_detail secret-key details")
    name = detail.split(":", 1)[0]
    return f"{name}: <redacted>"

def _doctor_output_redact_detail_fallback_branch(detail: str) -> str:
    """Mirror Rust output.rs redact_detail fallback branch."""
    lower = detail.lower()
    label = lower.split(":", 1)[0]
    secret_keys = {
        "openai_api_key",
        "codex_api_key",
        "codex_access_token",
        "authorization",
        "bearer_token",
        "token",
        "secret",
    }
    if "env var" in label:
        raise ValueError("env var branch is not the fallback branch")
    if ": " in detail:
        _, value = detail.split(": ", 1)
        if _doctor_output_is_safe_presence_value(value):
            raise ValueError("safe presence branch is not the fallback branch")
    if any(key in lower for key in secret_keys):
        raise ValueError("secret-key branch is not the fallback branch")
    return _doctor_output_redact_urls(detail)

def _doctor_output_status_counts_from_display_statuses(
    statuses: list[str], *, notes: int
) -> dict[str, int]:
    """Mirror Rust output.rs StatusCounts::from_report counting rules."""
    counts = {"ok": 0, "idle": 0, "notes": notes, "warning": 0, "fail": 0}
    for status in statuses:
        if status == "ok":
            counts["ok"] += 1
        elif status == "idle":
            counts["idle"] += 1
        elif status == "warning":
            counts["warning"] += 1
        elif status == "fail":
            counts["fail"] += 1
        elif status in {"update", "note"}:
            continue
        else:
            raise ValueError(f"unknown display status: {status}")
    return counts

def _doctor_output_bold_no_color(text: str) -> str:
    """Mirror Rust output.rs bold when color is disabled."""
    return text

def _doctor_output_dim_no_color(text: str) -> str:
    """Mirror Rust output.rs dim when color is disabled."""
    return text

def _doctor_output_detail_value_no_color(text: str) -> str:
    """Mirror Rust output.rs detail_value when color is disabled."""
    return text

def _doctor_output_color256_no_color(text: str, code: int) -> str:
    """Mirror Rust output.rs color256 when color is disabled."""
    if not 0 <= code <= 255:
        raise ValueError(f"xterm color code out of range: {code}")
    return text

def _doctor_output_green_no_color(text: str) -> str:
    """Mirror Rust output.rs green when color is disabled."""
    return _doctor_output_color256_no_color(text, 10)

def _doctor_output_amber_no_color(text: str) -> str:
    """Mirror Rust output.rs amber when color is disabled."""
    return _doctor_output_color256_no_color(text, 220)

def _doctor_output_orange_no_color(text: str) -> str:
    """Mirror Rust output.rs orange when color is disabled."""
    return _doctor_output_color256_no_color(text, 214)

def _doctor_output_red_no_color(text: str) -> str:
    """Mirror Rust output.rs red when color is disabled."""
    return _doctor_output_color256_no_color(text, 196)

def _doctor_output_cyan_no_color(text: str) -> str:
    """Mirror Rust output.rs cyan when color is disabled."""
    return _doctor_output_color256_no_color(text, 117)

def _doctor_output_very_dim_no_color(text: str) -> str:
    """Mirror Rust output.rs very_dim when color is disabled."""
    return _doctor_output_color256_no_color(text, 238)

def _doctor_output_detail_label_no_color(text: str) -> str:
    """Mirror Rust output.rs detail_label when color is disabled."""
    return _doctor_output_color256_no_color(text, 240)

def _doctor_output_looks_copyable(text: str) -> bool:
    """Mirror Rust output.rs looks_copyable."""
    return text.startswith(("http://", "https://", "wss://", "~/", "/", "./", "../"))

def _doctor_output_style_detail_token_plain_no_color(token: str) -> str:
    """Mirror Rust output.rs style_detail_token for plain bare tokens without styling branches."""
    trimmed = token.rstrip()
    suffix = token[len(trimmed) :]
    bare = trimmed.rstrip(",.:;)")
    punctuation = trimmed[len(bare) :]
    if not bare:
        return f"{punctuation}{suffix}"
    if (
        bare == "<redacted>"
        or "(missing)" in bare
        or bare.startswith("--")
        or _doctor_output_looks_copyable(bare)
        or bare in {"ok", "B", "KB", "MB", "GB", "TB", "files", "file"}
    ):
        raise ValueError("this helper only covers plain unstyled detail tokens")
    return f"{bare}{punctuation}{suffix}"

def _doctor_output_style_detail_plain_text_plain_no_color(text: str) -> str:
    """Mirror Rust output.rs style_detail_plain_text for plain unstyled text."""
    out: list[str] = []
    start = 0
    for index, char in enumerate(text):
        if char.isspace():
            out.append(_doctor_output_style_detail_token_plain_no_color(text[start : index + 1]))
            start = index + 1
    if start < len(text):
        out.append(_doctor_output_style_detail_token_plain_no_color(text[start:]))
    return "".join(out)

def _doctor_output_style_detail_text_plain_no_color(text: str) -> str:
    """Mirror Rust output.rs style_detail_text for plain/no-color text."""
    parts = text.split("`")
    if not parts:
        return ""
    out = [_doctor_output_style_detail_plain_text_plain_no_color(parts[0])]
    in_code = True
    for part in parts[1:]:
        if in_code:
            out.append(_doctor_output_cyan_no_color(part))
        else:
            out.append(_doctor_output_style_detail_plain_text_plain_no_color(part))
        in_code = not in_code
    return "".join(out)

def _doctor_output_style_detail_bare_token_unit_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token unit-token no-color branch."""
    if bare not in {"B", "KB", "MB", "GB", "TB", "files", "file"}:
        raise ValueError("this helper only covers unit detail tokens")
    return _doctor_output_dim_no_color(bare)

def _doctor_output_style_detail_bare_token_ok_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token ok-token no-color branch."""
    if bare != "ok":
        raise ValueError("this helper only covers the ok detail token")
    return _doctor_output_green_no_color(bare)

def _doctor_output_style_detail_bare_token_copyable_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token flag/copyable no-color branch."""
    if not (bare.startswith("--") or _doctor_output_looks_copyable(bare)):
        raise ValueError("this helper only covers flag or copyable detail tokens")
    return _doctor_output_cyan_no_color(bare)

def _doctor_output_style_detail_bare_token_empty(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token empty-token branch."""
    if bare != "":
        raise ValueError("this helper only covers the empty detail token")
    return ""

def _doctor_output_style_detail_bare_token_redacted_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token <redacted> no-color branch."""
    if bare != "<redacted>":
        raise ValueError("this helper only covers the <redacted> detail token")
    return _doctor_output_color256_no_color(bare, 244)

def _doctor_output_style_detail_bare_token_falsy_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token falsy/missing no-color branch."""
    if "(missing)" not in bare and not _doctor_detail_is_falsy(bare):
        raise ValueError("this helper only covers falsy or missing detail tokens")
    return _doctor_output_color256_no_color(bare, 240)

def _doctor_output_style_detail_bare_token_label_falsy_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token label:falsy no-color branch."""
    if ":" not in bare:
        raise ValueError("this helper only covers label:value detail tokens")
    label, value = bare.split(":", 1)
    if not _doctor_detail_is_falsy(value):
        raise ValueError("this helper only covers falsy detail token values")
    return f"{label}:{_doctor_output_color256_no_color(value, 240)}"

def _doctor_output_style_detail_bare_token_fallback_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token fallback branch."""
    if (
        bare == ""
        or bare == "<redacted>"
        or "(missing)" in bare
        or _doctor_detail_is_falsy(bare)
        or bare == "ok"
        or bare.startswith("--")
        or _doctor_output_looks_copyable(bare)
        or bare in {"B", "KB", "MB", "GB", "TB", "files", "file"}
    ):
        raise ValueError("this helper only covers fallback detail tokens")
    if ":" in bare:
        _, value = bare.split(":", 1)
        if _doctor_detail_is_falsy(value):
            raise ValueError("label:falsy branch is not the fallback branch")
    return bare

def _doctor_output_style_description_ok_idle_no_color(description: str, status: str) -> str:
    """Mirror Rust output.rs style_description Ok/Idle branch with color disabled."""
    if status not in {"ok", "idle"}:
        raise ValueError("this helper only covers ok/idle description styling")
    return _doctor_output_dim_no_color(_doctor_output_highlight_actions_no_color(description))

def _doctor_output_style_description_update_no_color(description: str, status: str) -> str:
    """Mirror Rust output.rs style_description Update branch with color disabled."""
    if status != "update":
        raise ValueError("this helper only covers update description styling")
    return _doctor_output_amber_no_color(_doctor_output_highlight_actions_no_color(description))

def _doctor_output_style_description_note_warning_fail_no_color(description: str, status: str) -> str:
    """Mirror Rust output.rs style_description Note/Warning/Fail branch with color disabled."""
    if status not in {"note", "warning", "fail"}:
        raise ValueError("this helper only covers note/warning/fail description styling")
    return _doctor_output_highlight_actions_no_color(description)

def _doctor_output_style_note_summary_non_update_no_color(status: str, summary: str) -> str:
    """Mirror Rust output.rs style_note_summary non-update path with color disabled."""
    if status == "update":
        raise ValueError("update status uses style_update_note_summary")
    if status in {"ok", "idle"}:
        return _doctor_output_style_description_ok_idle_no_color(summary, status)
    if status in {"note", "warning", "fail"}:
        return _doctor_output_style_description_note_warning_fail_no_color(summary, status)
    raise ValueError(f"unknown display status: {status}")

def _doctor_output_style_detail_bare_token_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token branch order with color disabled."""
    if bare == "":
        return _doctor_output_style_detail_bare_token_empty(bare)
    if bare == "<redacted>":
        return _doctor_output_style_detail_bare_token_redacted_no_color(bare)
    if "(missing)" in bare or _doctor_detail_is_falsy(bare):
        return _doctor_output_style_detail_bare_token_falsy_no_color(bare)
    if ":" in bare:
        _, value = bare.split(":", 1)
        if _doctor_detail_is_falsy(value):
            return _doctor_output_style_detail_bare_token_label_falsy_no_color(bare)
    if bare == "ok":
        return _doctor_output_style_detail_bare_token_ok_no_color(bare)
    if bare.startswith("--") or _doctor_output_looks_copyable(bare):
        return _doctor_output_style_detail_bare_token_copyable_no_color(bare)
    if bare in {"B", "KB", "MB", "GB", "TB", "files", "file"}:
        return _doctor_output_style_detail_bare_token_unit_no_color(bare)
    return _doctor_output_style_detail_bare_token_fallback_no_color(bare)

def _doctor_output_style_detail_token_no_color(token: str) -> str:
    """Mirror Rust output.rs style_detail_token with full no-color bare-token dispatch."""
    trimmed = token.rstrip()
    suffix = token[len(trimmed) :]
    bare = trimmed.rstrip(",.:;)")
    punctuation = trimmed[len(bare) :]
    styled = _doctor_output_style_detail_bare_token_no_color(bare)
    return f"{styled}{punctuation}{suffix}"

def _doctor_output_style_detail_plain_text_no_color(text: str) -> str:
    """Mirror Rust output.rs style_detail_plain_text with full no-color token dispatch."""
    out: list[str] = []
    start = 0
    for index, char in enumerate(text):
        if char.isspace():
            out.append(_doctor_output_style_detail_token_no_color(text[start : index + 1]))
            start = index + 1
    if start < len(text):
        out.append(_doctor_output_style_detail_token_no_color(text[start:]))
    return "".join(out)

def _doctor_output_style_detail_text_no_color(text: str) -> str:
    """Mirror Rust output.rs style_detail_text with full no-color plain/code dispatch."""
    parts = text.split("`")
    if not parts:
        return ""
    out = [_doctor_output_style_detail_plain_text_no_color(parts[0])]
    in_code = True
    for part in parts[1:]:
        if in_code:
            out.append(_doctor_output_cyan_no_color(part))
        else:
            out.append(_doctor_output_style_detail_plain_text_no_color(part))
        in_code = not in_code
    return "".join(out)

def _doctor_output_redact_detail(detail: str) -> str:
    """Mirror Rust output.rs redact_detail branch order."""
    lower = detail.lower()
    label = lower.split(":", 1)[0]
    if "env var" in label:
        return _doctor_output_redact_detail_env_var_branch(detail)
    if ": " in detail:
        _, value = detail.split(": ", 1)
        if _doctor_output_is_safe_presence_value(value):
            return _doctor_output_redact_detail_safe_presence_branch(detail)
    secret_keys = {
        "openai_api_key",
        "codex_api_key",
        "codex_access_token",
        "authorization",
        "bearer_token",
        "token",
        "secret",
    }
    if any(key in lower for key in secret_keys):
        return _doctor_output_redact_detail_secret_key_branch(detail)
    return _doctor_output_redact_detail_fallback_branch(detail)

def _doctor_output_style_description_no_color(description: str, status: str) -> str:
    """Mirror Rust output.rs style_description branch order with color disabled."""
    if status in {"ok", "idle"}:
        return _doctor_output_style_description_ok_idle_no_color(description, status)
    if status == "update":
        return _doctor_output_style_description_update_no_color(description, status)
    if status in {"note", "warning", "fail"}:
        return _doctor_output_style_description_note_warning_fail_no_color(description, status)
    raise ValueError(f"unknown display status: {status}")

def _doctor_output_detailed_no_color_unicode_options() -> dict[str, bool]:
    """Mirror Rust output.rs detailed_no_color_unicode_options test fixture."""
    return {
        "show_details": True,
        "show_all": False,
        "ascii": False,
        "color_enabled": False,
    }

def _doctor_output_summary_no_color_unicode_options() -> dict[str, bool]:
    """Mirror Rust output.rs summary_no_color_unicode_options test fixture."""
    return {
        "show_details": False,
        "show_all": False,
        "ascii": False,
        "color_enabled": False,
    }

def _doctor_output_detailed_all_no_color_unicode_options() -> dict[str, bool]:
    """Mirror Rust output.rs detailed_all_no_color_unicode_options test fixture."""
    return {
        "show_details": True,
        "show_all": True,
        "ascii": False,
        "color_enabled": False,
    }

def _doctor_output_detailed_color_unicode_options() -> dict[str, bool]:
    """Mirror Rust output.rs detailed_color_unicode_options test fixture."""
    return {
        "show_details": True,
        "show_all": False,
        "ascii": False,
        "color_enabled": True,
    }

def _doctor_output_sample_report_check_metadata() -> dict[str, object]:
    """Mirror Rust output.rs sample_report lightweight check metadata."""
    return {
        "schema_version": 1,
        "generated_at": "0s since unix epoch",
        "overall_status": "fail",
        "codex_version": "0.0.0",
        "checks": [
            ("system.environment", "system", "ok"),
            ("runtime.provenance", "runtime", "ok"),
            ("installation", "install", "ok"),
            ("runtime.search", "search", "ok"),
            ("git.environment", "git", "ok"),
            ("terminal.env", "terminal", "warning"),
            ("terminal.title", "title", "ok"),
            ("state.paths", "state", "ok"),
            ("auth.credentials", "auth", "fail"),
            ("updates.status", "updates", "ok"),
            ("network.env", "network", "ok"),
            ("network.websocket_reachability", "websocket", "ok"),
            ("app_server.status", "app-server", "ok"),
            ("network.provider_reachability", "reachability", "ok"),
        ],
    }

def _doctor_output_sample_report_detail_metadata() -> dict[str, dict[str, object]]:
    """Mirror Rust output.rs sample_report detail/remediation metadata."""
    return {
        "system.environment": {
            "details": ["os: macOS 15.0", "os language: en-US"],
            "remediation": None,
        },
        "git.environment": {
            "details": [
                "selected git: /usr/bin/git",
                "git version: git version 2.54.0",
                "repo detected: true",
            ],
            "remediation": None,
        },
        "terminal.title": {
            "details": [
                "terminal title source: default",
                "terminal title items: activity, project-name",
                "terminal title project value: codex",
            ],
            "remediation": None,
        },
        "auth.credentials": {
            "details": ["OPENAI_API_KEY: present"],
            "remediation": "Run `codex login`.",
        },
    }

def _doctor_output_sample_report_status_counts(notes: int = 0) -> dict[str, int]:
    """Mirror Rust output.rs sample_report status counts via StatusCounts::from_report."""
    report = _doctor_output_sample_report_check_metadata()
    statuses = [status for _, _, status in report["checks"]]
    return _doctor_output_status_counts_from_display_statuses(statuses, notes=notes)

def _doctor_output_sample_report_non_ok_notes() -> list[tuple[str, str]]:
    """Mirror Rust output.rs sample_report non-ok notes generation."""
    checks = [
        {"status": "ok", "summary": "OS language en-US"},
        {"status": "ok", "summary": "running local build on darwin-arm64"},
        {"status": "ok", "summary": "installation looks consistent"},
        {"status": "ok", "summary": "search is OK (bundled)"},
        {"status": "ok", "summary": "git version 2.54.0"},
        {"status": "warning", "summary": "narrow terminal"},
        {"status": "ok", "summary": "terminal title default"},
        {"status": "ok", "summary": "state paths inspectable"},
        {"status": "fail", "summary": "token expired", "remediation": "Run `codex login`."},
        {"status": "ok", "summary": "update configuration is locally consistent"},
        {"status": "ok", "summary": "network environment readable"},
        {"status": "ok", "summary": "Responses WebSocket handshake succeeded"},
        {"status": "ok", "summary": "background server is not running"},
        {"status": "ok", "summary": "active provider endpoints are reachable over HTTP"},
    ]
    return _doctor_output_non_ok_notes(checks)

def _doctor_output_sample_report_summary_line(*, ascii_output: bool = False, notes: int = 0) -> str:
    """Mirror Rust output.rs summary_line for sample_report counts."""
    counts = _doctor_output_sample_report_status_counts(notes=notes)
    return _doctor_output_summary_line_text(
        ok=counts["ok"],
        idle=counts["idle"],
        notes=counts["notes"],
        warning=counts["warning"],
        fail=counts["fail"],
        overall_status="fail",
        ascii_output=ascii_output,
    )

def _doctor_output_summary_mode_footer_lines() -> list[str]:
    """Mirror Rust output.rs summary-mode footer advice lines."""
    return [
        "Run codex doctor without --summary for detailed diagnostics.",
        "--all expand truncated lists       --json redacted report",
    ]

def _doctor_output_sample_report_summary_notes_lines() -> list[str]:
    """Mirror Rust output.rs summary output notes block for sample_report."""
    return [
        "Notes",
        "   ⚠ terminal     narrow terminal",
        "   ✗ auth         token expired - Run `codex login`.",
    ]

def _doctor_output_sample_report_summary_section_headings() -> list[str]:
    """Mirror Rust output.rs summary output section heading order for sample_report."""
    return [
        "Environment",
        "Configuration",
        "Updates",
        "Connectivity",
        "Background Server",
    ]

def _doctor_output_sample_report_summary_environment_lines() -> list[str]:
    """Mirror Rust output.rs summary output Environment rows for sample_report."""
    return [
        "  ✓ system       en-US",
        "  ✓ runtime      running local build on darwin-arm64",
        "  ✓ install      consistent",
        "  ✓ search       search is OK (bundled)",
        "  ✓ git          git version 2.54.0",
        "  ⚠ terminal     narrow terminal",
        "  ✓ title        default · project codex",
        "  ✓ state        state paths inspectable",
    ]

def _doctor_output_sample_report_summary_updates_lines() -> list[str]:
    """Mirror Rust output.rs summary output Updates rows for sample_report."""
    return [
        "  ✓ updates      update configuration is locally consistent",
    ]

def _doctor_output_sample_report_summary_connectivity_lines() -> list[str]:
    """Mirror Rust output.rs summary output Connectivity rows for sample_report."""
    return [
        "  ✓ network      network environment readable",
        "  ✓ websocket    Responses WebSocket handshake succeeded",
        "  ✓ reachability active provider endpoints are reachable over HTTP",
    ]

def _doctor_output_sample_report_summary_background_server_lines() -> list[str]:
    """Mirror Rust output.rs summary output Background Server rows for sample_report."""
    return [
        "  ✓ app-server   background server is not running",
    ]

def _doctor_output_sample_report_summary_configuration_lines() -> list[str]:
    """Mirror Rust output.rs summary output Configuration rows for sample_report."""
    return [
        "  ✗ auth         token expired — Run `codex login`.",
    ]

def _doctor_output_sample_report_summary_section_blocks() -> list[tuple[str, list[str]]]:
    """Mirror Rust output.rs summary output section blocks for sample_report."""
    return [
        ("Environment", _doctor_output_sample_report_summary_environment_lines()),
        ("Configuration", _doctor_output_sample_report_summary_configuration_lines()),
        ("Updates", _doctor_output_sample_report_summary_updates_lines()),
        ("Connectivity", _doctor_output_sample_report_summary_connectivity_lines()),
        ("Background Server", _doctor_output_sample_report_summary_background_server_lines()),
    ]

def _doctor_output_sample_report_summary_title_line() -> str:
    """Mirror Rust output.rs summary output title line for sample_report."""
    return "Codex Doctor v0.0.0"

def _doctor_output_sample_report_summary_footer_summary_line() -> str:
    """Mirror Rust output.rs summary output footer summary line for sample_report."""
    return _doctor_output_sample_report_summary_line(notes=2)

def _doctor_output_sample_report_summary_no_color_rendered() -> str:
    """Mirror Rust output.rs render_human_report summary/no-color sample_report snapshot."""
    separator = "─" * 61
    lines: list[str] = [
        _doctor_output_sample_report_summary_title_line(),
        "",
        *_doctor_output_sample_report_summary_notes_lines(),
        separator,
        "",
    ]
    for index, (heading, section_lines) in enumerate(
        _doctor_output_sample_report_summary_section_blocks()
    ):
        if index:
            lines.append("")
        lines.append(heading)
        lines.extend(section_lines)
    lines.extend(
        [
            "",
            separator,
            _doctor_output_sample_report_summary_footer_summary_line(),
            "",
            *_doctor_output_summary_mode_footer_lines(),
        ]
    )
    return "\n".join(lines) + "\n"

def _doctor_output_summary_environment_threads_row() -> str:
    """Mirror Rust output.rs summary row for state.rollout_db_parity in Environment."""
    return "  ⚠ threads      rollout files and state DB thread inventory differ"

def _doctor_output_state_health_summary_with_memories_db_lines() -> list[str]:
    """Mirror Rust output.rs detailed state health summary including memories DB."""
    return [
        "✓ state        databases healthy",
        "memories DB              /tmp/memories.sqlite · integrity ok",
    ]

def _doctor_output_sample_report_summary_ascii_rendered() -> str:
    """Mirror Rust output.rs render_human_report summary/ascii sample_report snapshot."""
    separator = "-" * 61
    return "\n".join(
        [
            "Codex Doctor v0.0.0",
            "",
            "Notes",
            "   [!!] terminal     narrow terminal",
            "   [XX] auth         token expired - Run `codex login`.",
            separator,
            "",
            "Environment",
            "  [ok] system       en-US",
            "  [ok] runtime      running local build on darwin-arm64",
            "  [ok] install      consistent",
            "  [ok] search       search is OK (bundled)",
            "  [ok] git          git version 2.54.0",
            "  [!!] terminal     narrow terminal",
            "  [ok] title        default | project codex",
            "  [ok] state        state paths inspectable",
            "",
            "Configuration",
            "  [XX] auth         token expired - Run `codex login`.",
            "",
            "Updates",
            "  [ok] updates      update configuration is locally consistent",
            "",
            "Connectivity",
            "  [ok] network      network environment readable",
            "  [ok] websocket    Responses WebSocket handshake succeeded",
            "  [ok] reachability active provider endpoints are reachable over HTTP",
            "",
            "Background Server",
            "  [ok] app-server   background server is not running",
            "",
            separator,
            "12 ok | 2 notes | 1 warn | 1 fail failed",
            "",
            "Run codex doctor without --summary for detailed diagnostics.",
            "--all expand truncated lists       --json redacted report",
        ]
    ) + "\n"

def _doctor_output_sample_report_redacted_detail_lines() -> list[str]:
    """Mirror Rust output.rs detailed sample_report redacted credential details."""
    return [
        "      OPENAI_API_KEY           present",
    ]

def _doctor_output_terminal_warning_issue_lines() -> list[str]:
    """Mirror Rust output.rs detailed terminal warning issue rendering."""
    return [
        "⚠ terminal     width 79 cols - output may wrap (recommended >=80)",
        "▸ terminal size            79x26 (expected >= 80 columns)",
        "→ resize the window to at least 80 columns",
    ]

def _doctor_output_terminal_warning_issue_forbidden_summary() -> str:
    """Mirror Rust output.rs terminal warning summary that must not be rendered."""
    return "⚠ terminal     Ghostty 1.3.1"

def _doctor_output_promoted_notes_without_status_change_lines() -> list[str]:
    """Mirror Rust output.rs promoted notes rendering without changing statuses."""
    return [
        "Notes\n   ↑ updates",
        "0.130.0 available (current 0.0.0, dismissed 0.128.0)",
        "⚠ rollouts",
        "⚠ sandbox",
        "⚠ mcp",
        "⚠ auth         mixed auth signals: ChatGPT login plus API key env var; HTTP reachability uses API-key mode",
        "○ app-server   not running (ephemeral mode)",
        "5 ok · 1 idle · 5 notes · 1 warn · 0 fail degraded",
    ]

