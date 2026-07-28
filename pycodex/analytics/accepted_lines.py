"""Rust-aligned ``codex-analytics::accepted_lines`` owner."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .facts import AcceptedLineFingerprint

@dataclass(frozen=True)
class AcceptedLineFingerprintSummary:
    accepted_added_lines: int
    accepted_deleted_lines: int
    line_fingerprints: list[AcceptedLineFingerprint]

@dataclass(frozen=True)
class AcceptedLineFingerprintEventInput:
    event_type: str
    turn_id: str
    thread_id: str
    product_surface: str | None
    model_slug: str | None
    completed_at: int
    repo_hash: str | None
    accepted_added_lines: int
    accepted_deleted_lines: int
    line_fingerprints: list[AcceptedLineFingerprint]

def fingerprint_hash(domain: str, value: str) -> str:
    hasher = hashlib.sha1()
    hasher.update(b"file-line-v1\0")
    hasher.update(domain.encode())
    hasher.update(b"\0")
    hasher.update(value.encode())
    return hasher.hexdigest()

def accepted_line_fingerprints_from_unified_diff(unified_diff: str) -> AcceptedLineFingerprintSummary:
    current_path: str | None = None
    in_hunk = False
    accepted_added_lines = 0
    accepted_deleted_lines = 0
    fingerprints: list[AcceptedLineFingerprint] = []
    for line in unified_diff.splitlines():
        if line.startswith("diff --git "):
            current_path = None
            in_hunk = False
            continue
        if line.startswith("@@ "):
            in_hunk = True
            continue
        if not in_hunk and line.startswith("+++ "):
            current_path = _normalize_diff_path(line[4:])
            continue
        if not in_hunk and line.startswith("--- "):
            continue
        if line.startswith("+"):
            accepted_added_lines += 1
            if current_path is not None:
                normalized = _normalize_effective_line(line[1:])
                if normalized is not None:
                    fingerprints.append(AcceptedLineFingerprint(fingerprint_hash("path", current_path), fingerprint_hash("line", normalized)))
            continue
        if line.startswith("-"):
            accepted_deleted_lines += 1
    return AcceptedLineFingerprintSummary(accepted_added_lines, accepted_deleted_lines, fingerprints)

def accepted_line_fingerprint_event_requests(
    input: AcceptedLineFingerprintEventInput,
) -> list[dict[str, Any]]:
    return [
        {
            "event_type": "codex_accepted_line_fingerprints",
            "event_params": {
                "event_type": input.event_type,
                "turn_id": input.turn_id,
                "thread_id": input.thread_id,
                "product_surface": input.product_surface,
                "model_slug": input.model_slug,
                "completed_at": input.completed_at,
                "repo_hash": input.repo_hash,
                "accepted_added_lines": input.accepted_added_lines,
                "accepted_deleted_lines": input.accepted_deleted_lines,
                "line_fingerprints": [],
            },
        }
    ]

def _normalize_diff_path(path: str) -> str | None:
    path = path.strip()
    if path == "/dev/null":
        return None
    return path[2:] if path.startswith(("a/", "b/")) else path

def _normalize_effective_line(line: str) -> str | None:
    normalized = " ".join(line.split())
    if len(normalized) <= 3:
        return None
    if not any(ch.isalnum() or ch == "_" for ch in normalized):
        return None
    return normalized


__all__ = [name for name in globals() if not name.startswith("_")]
