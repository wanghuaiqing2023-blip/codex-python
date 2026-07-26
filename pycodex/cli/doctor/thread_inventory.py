"""Rust-aligned implementation for codex-cli doctor::thread_inventory."""



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



from pycodex.cli.doctor import DoctorUpdateCheck, _bool_text, _display_list, _doctor_path_text, _optional_str



def thread_inventory_check(
    *,
    codex_home: str | Path,
    sqlite_home: str | Path | None = None,
    default_provider: str = "openai",
) -> DoctorUpdateCheck:
    home = Path(codex_home)
    sqlite_root = Path(sqlite_home) if sqlite_home is not None else home
    scan = _scan_rollout_inventory(home)
    state_db_path = sqlite_root / "state_5.sqlite"
    details = [
        f"default model provider: {default_provider}",
        f"rollout DB active files: {sum(1 for item in scan['files'] if not item['archived'])}",
        f"rollout DB archived files: {sum(1 for item in scan['files'] if item['archived'])}",
        f"rollout DB scan errors: {len(scan['scan_errors'])}",
        f"rollout DB malformed file names: {len(scan['malformed_names'])}",
        f"rollout DB scan cap reached: {_bool_text(scan['reached_scan_cap'])}",
    ]
    _push_samples(details, "rollout DB scan error sample", scan["scan_errors"])
    _push_samples(
        details,
        "rollout DB malformed file sample",
        [_doctor_path_text(path) for path in scan["malformed_names"]],
    )

    if not state_db_path.is_file():
        details.append("rollout DB rows: skipped (state DB missing)")
        if not scan["files"] and not scan["scan_errors"] and not scan["malformed_names"] and not scan["reached_scan_cap"]:
            return DoctorUpdateCheck(
                status="ok",
                summary="no rollout/state DB inventory to compare",
                details=tuple(details),
            )
        summary = "state DB is missing while rollout files exist" if scan["files"] else "rollout scan was incomplete or found bad files"
        issues: list[dict[str, Any]] = []
        if scan["files"]:
            issues.append(
                {
                    "severity": "warn",
                    "cause": "rollout files exist but the state DB is missing",
                    "measured": f"{len(scan['files'])} rollout files",
                    "expected": "state DB contains matching thread rows",
                    "remedy": "Start Codex with no state DB present so startup backfill can create it from rollout files.",
                    "fields": [],
                }
            )
        if scan["scan_errors"] or scan["malformed_names"] or scan["reached_scan_cap"]:
            issues.append(_thread_inventory_scan_issue(scan))
        return DoctorUpdateCheck(
            status="warn",
            summary=summary,
            details=tuple(details),
            remediation=(
                "Start Codex with no state DB present so startup backfill can create it from rollout files."
                if scan["files"]
                else None
            ),
            issues=tuple(issues),
        )

    try:
        rows = _read_thread_inventory_rows(state_db_path)
    except Exception as exc:
        details.append(f"rollout DB read error: {exc}")
        return DoctorUpdateCheck(
            status="warn",
            summary="state database thread inventory could not be read",
            details=tuple(details),
            issues=(
                {
                    "severity": "warn",
                    "cause": "state DB thread rows could not be queried",
                    "measured": str(exc),
                    "expected": "readable threads table",
                    "remedy": None,
                    "fields": [],
                },
            ),
        )

    return _thread_inventory_parity_check(home, scan, rows, details)

def _scan_rollout_inventory(codex_home: Path) -> dict[str, Any]:
    scan: dict[str, Any] = {
        "files": [],
        "scan_errors": [],
        "malformed_names": [],
        "reached_scan_cap": False,
    }
    _scan_rollout_inventory_root(codex_home / "sessions", False, scan)
    _scan_rollout_inventory_root(codex_home / "archived_sessions", True, scan)
    return scan

def _scan_rollout_inventory_root(root: Path, archived: bool, scan: dict[str, Any]) -> None:
    stack = [root]
    while stack:
        if _rollout_scan_candidate_count(scan) >= 10_000:
            scan["reached_scan_cap"] = True
            return
        directory = stack.pop()
        try:
            entries = list(directory.iterdir())
        except FileNotFoundError:
            continue
        except OSError as exc:
            scan["scan_errors"].append(f"{_doctor_path_text(directory)} ({exc})")
            continue
        for entry in entries:
            if _rollout_scan_candidate_count(scan) >= 10_000:
                scan["reached_scan_cap"] = True
                return
            try:
                if entry.is_dir():
                    stack.append(entry)
                    continue
                if not entry.is_file() or entry.suffix != ".jsonl" or not entry.name.startswith("rollout-"):
                    continue
            except OSError as exc:
                scan["scan_errors"].append(f"{_doctor_path_text(entry)} ({exc})")
                continue
            thread_id, unusable_reason = _thread_id_from_rollout(entry)
            if thread_id is None:
                if unusable_reason is None:
                    scan["malformed_names"].append(entry)
                else:
                    scan["scan_errors"].append(f"{_doctor_path_text(entry)} ({unusable_reason})")
                continue
            scan["files"].append(
                {
                    "path": entry,
                    "key": _path_key(entry),
                    "archived": archived,
                    "thread_id": thread_id,
                }
            )

def _rollout_scan_candidate_count(scan: dict[str, Any]) -> int:
    return len(scan["files"]) + len(scan["scan_errors"]) + len(scan["malformed_names"])

def _thread_id_from_rollout(path: Path) -> tuple[str | None, str | None]:
    jsonl_thread_id, error = _thread_id_from_rollout_jsonl(path)
    if jsonl_thread_id is not None:
        return jsonl_thread_id, None
    if error is not None:
        return None, error
    filename_thread_id = _thread_id_from_rollout_filename(path)
    if filename_thread_id is not None:
        return filename_thread_id, None
    return None, None

def _thread_id_from_rollout_jsonl(path: Path) -> tuple[str | None, str | None]:
    saw_parseable_line = False
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                saw_parseable_line = True
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    return None, str(exc)
                thread_id = _session_meta_thread_id(item)
                if thread_id is not None:
                    return thread_id, None
    except OSError as exc:
        return None, str(exc)
    if saw_parseable_line:
        return None, None
    return None, "no parseable rollout items"

def _session_meta_thread_id(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    candidates: list[Any] = []
    if item.get("type") == "session_meta":
        candidates.append(item.get("payload"))
    nested_item = item.get("item")
    if isinstance(nested_item, dict) and nested_item.get("type") == "session_meta":
        candidates.append(nested_item.get("payload"))
    candidates.append(item.get("session_meta"))
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        thread_id = _optional_str(candidate.get("id"))
        if thread_id is not None and _is_uuid_like(thread_id):
            return thread_id.lower()
        meta = candidate.get("meta")
        if isinstance(meta, dict):
            thread_id = _optional_str(meta.get("id"))
            if thread_id is not None and _is_uuid_like(thread_id):
                return thread_id.lower()
    return None

def _thread_id_from_rollout_filename(path: Path) -> str | None:
    stem = path.stem
    prefix = "rollout-"
    if not stem.startswith(prefix):
        return None
    thread_id = stem[-36:]
    return thread_id.lower() if _is_uuid_like(thread_id) else None

def _is_uuid_like(value: str) -> bool:
    if len(value) != 36:
        return False
    parts = value.split("-")
    if [len(part) for part in parts] != [8, 4, 4, 4, 12]:
        return False
    return all(all(char in "0123456789abcdefABCDEF" for char in part) for part in parts)

def _read_thread_inventory_rows(state_db_path: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(state_db_path)
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT id, rollout_path, archived, model_provider, source FROM threads"
        ).fetchall()
    finally:
        connection.close()
    _close_sqlite_connections_for_path(state_db_path)
    return [
        {
            "id": str(row["id"]).lower(),
            "rollout_path": Path(str(row["rollout_path"])),
            "archived": bool(row["archived"]),
            "model_provider": str(row["model_provider"]),
            "source": str(row["source"]),
        }
        for row in rows
    ]

def _close_sqlite_connections_for_path(db_path: Path) -> None:
    target = str(db_path)
    try:
        normalized_target = str(db_path.resolve())
    except OSError:
        normalized_target = target
    for candidate in list(gc.get_objects()):
        if candidate.__class__.__name__ != "Connection":
            continue
        try:
            databases = candidate.execute("PRAGMA database_list").fetchall()
        except Exception:
            continue
        for _, _, filename in databases:
            if not isinstance(filename, str):
                continue
            normalized_filename = filename
            try:
                normalized_filename = str(Path(filename).resolve())
            except OSError:
                normalized_filename = filename
            if filename == target or normalized_filename == normalized_target:
                with suppress(Exception):
                    candidate.close()
                break

def _thread_inventory_parity_check(
    codex_home: Path,
    scan: dict[str, Any],
    rows: list[dict[str, Any]],
    details: list[str],
) -> DoctorUpdateCheck:
    files = scan["files"]
    rows_by_key: dict[Path, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_key.setdefault(_path_key(row["rollout_path"]), []).append(row)

    missing_active = _missing_rollout_paths(files, rows_by_key, archived=False)
    missing_archived = _missing_rollout_paths(files, rows_by_key, archived=True)
    scan_complete = not scan["reached_scan_cap"]
    stale_rows = [row for row in rows if not row["rollout_path"].is_file()] if scan_complete else []
    archive_mismatches = _archive_mismatch_rows(codex_home, files, rows) if scan_complete else []
    duplicate_rollout_thread_ids = _duplicate_values(str(item["thread_id"]) for item in files)
    duplicate_db_paths = _duplicate_values(str(_path_key(row["rollout_path"])) for row in rows)
    archived_rows = sum(1 for row in rows if row["archived"])
    active_rows = len(rows) - archived_rows

    details.extend(
        [
            f"rollout DB rows: {len(rows)}",
            f"rollout DB active rows: {active_rows}",
            f"rollout DB archived rows: {archived_rows}",
            f"rollout DB missing active rows: {len(missing_active)}",
            f"rollout DB missing archived rows: {len(missing_archived)}",
            f"rollout DB stale rows: {_count_or_skipped(len(stale_rows), scan_complete)}",
            f"rollout DB archive mismatches: {_count_or_skipped(len(archive_mismatches), scan_complete)}",
            f"rollout DB duplicate rollout thread ids: {len(duplicate_rollout_thread_ids)}",
            f"rollout DB duplicate DB paths: {len(duplicate_db_paths)}",
            f"rollout DB model providers: {_count_summary(row['model_provider'] for row in rows)}",
            f"rollout DB sources: {_count_summary(_source_category(row['source']) for row in rows)}",
        ]
    )
    _push_samples(details, "rollout DB missing active sample", [_doctor_path_text(path) for path in missing_active])
    _push_samples(details, "rollout DB missing archived sample", [_doctor_path_text(path) for path in missing_archived])
    _push_samples(
        details,
        "rollout DB stale row sample",
        [_doctor_path_text(row["rollout_path"]) for row in stale_rows],
    )
    _push_samples(
        details,
        "rollout DB archive mismatch sample",
        [_doctor_path_text(row["rollout_path"]) for row in archive_mismatches],
    )
    _push_samples(details, "rollout DB duplicate rollout thread id sample", duplicate_rollout_thread_ids)
    _push_samples(details, "rollout DB duplicate DB path sample", duplicate_db_paths)

    clean = (
        not scan["scan_errors"]
        and not scan["malformed_names"]
        and not scan["reached_scan_cap"]
        and not missing_active
        and not missing_archived
        and not stale_rows
        and not archive_mismatches
        and not duplicate_rollout_thread_ids
        and not duplicate_db_paths
    )
    issues: list[dict[str, Any]] = []
    if missing_active or missing_archived:
        issues.append(
            {
                "severity": "warn",
                "cause": "rollout files are missing from the state DB",
                "measured": f"{len(missing_active)} active, {len(missing_archived)} archived",
                "expected": "every rollout file has a matching threads row",
                "remedy": None,
                "fields": [],
            }
        )
    if stale_rows:
        issues.append(
            {
                "severity": "warn",
                "cause": "state DB rows point at missing or unusable rollout files",
                "measured": f"{len(stale_rows)} stale rows",
                "expected": "every state DB rollout path is a file on disk",
                "remedy": None,
                "fields": [],
            }
        )
    if archive_mismatches:
        issues.append(
            {
                "severity": "warn",
                "cause": "state DB archive flags disagree with rollout file locations",
                "measured": f"{len(archive_mismatches)} mismatched rows",
                "expected": "rows under archived_sessions are archived and rows under sessions are active",
                "remedy": None,
                "fields": [],
            }
        )
    if duplicate_rollout_thread_ids or duplicate_db_paths:
        issues.append(
            {
                "severity": "warn",
                "cause": "duplicate thread inventory entries found",
                "measured": (
                    f"{len(duplicate_rollout_thread_ids)} duplicate rollout thread ids, "
                    f"{len(duplicate_db_paths)} duplicate DB paths"
                ),
                "expected": "one rollout path and thread id per thread",
                "remedy": "Attach the doctor report to a bug report so support can inspect samples.",
                "fields": [],
            }
        )
    if scan["scan_errors"] or scan["malformed_names"] or scan["reached_scan_cap"]:
        issues.append(_thread_inventory_scan_issue(scan))

    return DoctorUpdateCheck(
        status="ok" if clean else "warn",
        summary=(
            "rollout files and state DB thread inventory agree"
            if clean
            else "rollout files and state DB thread inventory differ"
        ),
        details=tuple(details),
        issues=tuple(issues),
    )

def _thread_inventory_scan_issue(scan: dict[str, Any]) -> dict[str, Any]:
    return {
        "severity": "warn",
        "cause": "rollout scan was incomplete or found bad files",
        "measured": (
            f"{len(scan['scan_errors'])} scan errors, "
            f"{len(scan['malformed_names'])} malformed names, "
            f"scan cap reached: {_bool_text(scan['reached_scan_cap'])}"
        ),
        "expected": "rollout directories are fully scannable",
        "remedy": "Check file permissions and unexpected files under CODEX_HOME sessions.",
        "fields": [],
    }

def _missing_rollout_paths(files: list[dict[str, Any]], rows_by_key: dict[Path, list[dict[str, Any]]], *, archived: bool) -> list[Path]:
    missing: list[Path] = []
    for file in files:
        if file["archived"] != archived:
            continue
        rows = rows_by_key.get(file["key"], [])
        if not any(row["id"] == file["thread_id"] for row in rows):
            missing.append(file["path"])
    return missing

def _archive_mismatch_rows(codex_home: Path, files: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    archived_by_key = {file["key"]: file["archived"] for file in files}
    mismatches: list[dict[str, Any]] = []
    for row in rows:
        key = _path_key(row["rollout_path"])
        expected = archived_by_key.get(key)
        if expected is None:
            expected = _archived_from_rollout_path(codex_home, row["rollout_path"])
        if expected is not None and expected != row["archived"]:
            mismatches.append(row)
    return mismatches

def _archived_from_rollout_path(codex_home: Path, path: Path) -> bool | None:
    key = _path_key(path)
    if _path_is_relative_to(key, _path_key(codex_home / "archived_sessions")):
        return True
    if _path_is_relative_to(key, _path_key(codex_home / "sessions")):
        return False
    return None

def _path_key(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except OSError:
        return path

def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False

def _duplicate_values(values: Any) -> list[str]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return sorted(value for value, count in counts.items() if count > 1)

def _count_or_skipped(count: int, complete: bool) -> str:
    return str(count) if complete else "skipped (scan cap reached)"

def _count_summary(values: Any) -> str:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    if not counts:
        return "none"
    entries = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    omitted = entries[8:]
    parts = [f"{key}={count}" for key, count in entries[:8]]
    if omitted:
        omitted_rows = sum(count for _key, count in omitted)
        parts.append(f"other={omitted_rows} across {len(omitted)} categories")
    return ", ".join(parts)

def _source_category(source: str) -> str:
    parsed: Any = source
    try:
        parsed = json.loads(source)
    except Exception:
        pass
    if isinstance(parsed, str):
        normalized = parsed.strip().lower()
        return {
            "cli": "cli",
            "vscode": "vscode",
            "exec": "exec",
            "mcp": "mcp",
            "unknown": "unknown",
        }.get(normalized, "unparsable")
    if not isinstance(parsed, dict):
        return "unparsable"
    source_type = _optional_str(parsed.get("type"))
    if source_type == "custom":
        return "custom"
    if source_type == "internal":
        internal_type = _optional_str(parsed.get("internal_source")) or _optional_str(parsed.get("source"))
        if internal_type == "memory_consolidation":
            return "internal:memory_consolidation"
        return "unparsable"
    if source_type == "subagent":
        subagent_source = parsed.get("subagent_source")
        if isinstance(subagent_source, str):
            return {
                "review": "subagent:review",
                "compact": "subagent:compact",
                "memory_consolidation": "subagent:memory_consolidation",
            }.get(subagent_source, "subagent:other")
        if isinstance(subagent_source, dict):
            subagent_type = _optional_str(subagent_source.get("type"))
            return {
                "review": "subagent:review",
                "compact": "subagent:compact",
                "thread_spawn": "subagent:thread_spawn",
                "memory_consolidation": "subagent:memory_consolidation",
                "other": "subagent:other",
            }.get(subagent_type or "", "subagent:other")
        return "subagent:other"
    return "unparsable"

def _push_samples(details: list[str], label: str, values: list[str]) -> None:
    for value in values[:5]:
        details.append(f"{label}: {value}")
    omitted = len(values) - 5
    if omitted > 0:
        details.append(f"{label}: {omitted} more omitted")

def _push_feature_flag_details(details: list[str], config: dict[str, Any]) -> None:
    features = config.get("features")
    if not isinstance(features, dict):
        enabled: list[str] = []
        overrides: list[str] = []
    else:
        enabled = sorted(key for key, value in features.items() if value is True)
        overrides = sorted(f"{key}={_bool_text(value)}" for key, value in features.items() if isinstance(value, bool))
    details.append(f"feature flags enabled: {len(enabled)}")
    details.append(f"enabled feature flags: {_display_list(enabled)}")
    details.append(f"feature flag overrides: {_display_list(overrides)}")
    for usage in config.get("legacy_feature_usages", ()):
        if not isinstance(usage, dict):
            continue
        alias = _optional_str(usage.get("alias"))
        feature = _optional_str(usage.get("feature_key")) or _optional_str(usage.get("feature"))
        if alias and feature:
            details.append(f"legacy feature flag: {alias} -> {feature}")

