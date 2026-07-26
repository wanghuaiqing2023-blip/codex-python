"""Rust-aligned implementation for codex-cli debug_sandbox::seatbelt."""



from __future__ import annotations

import json

import os

import re

import subprocess

import threading

import time

from collections.abc import Callable, Iterable, Mapping, Sequence

from dataclasses import dataclass

from enum import Enum

from pathlib import Path

import sys

from pycodex.core.spawn import CODEX_SANDBOX_ENV_VAR, CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR



@dataclass(frozen=True)
class DebugSandboxDenialLoggerPlan:
    """Lifecycle decisions for macOS Seatbelt denial logging."""

    enabled: bool
    platform: str
    log_denials_requested: bool
    create_before_spawn: bool
    attach_after_child_spawn: bool
    finish_after_child_wait: bool
    output_header: str | None
    empty_message: str | None
    denial_line_template: str | None

@dataclass(frozen=True)
class DebugSandboxDenialLogResult:
    """Collected denial logger output after the child wait."""

    enabled: bool
    denials: tuple[tuple[str, str], ...]
    output_lines: tuple[str, ...]

@dataclass(frozen=True)
class SandboxDenial:
    """Parsed macOS sandbox denial log entry."""

    pid: int
    name: str
    capability: str

def build_debug_sandbox_denial_logger_plan(
    *,
    log_denials: bool,
    platform: str | None = None,
) -> DebugSandboxDenialLoggerPlan:
    """Build the lifecycle plan for Rust's optional Seatbelt denial logger."""

    platform_name = platform or sys.platform
    enabled = platform_name == "darwin" and log_denials
    return DebugSandboxDenialLoggerPlan(
        enabled=enabled,
        platform=platform_name,
        log_denials_requested=log_denials,
        create_before_spawn=enabled,
        attach_after_child_spawn=enabled,
        finish_after_child_wait=enabled,
        output_header="\n=== Sandbox denials ===" if enabled else None,
        empty_message="None found." if enabled else None,
        denial_line_template="({name}) {capability}" if enabled else None,
    )

def format_debug_sandbox_denial_summary(
    denials: Sequence[tuple[str, str]],
) -> tuple[str, ...]:
    """Return the user-facing Seatbelt denial summary lines."""

    lines = ["", "=== Sandbox denials ==="]
    if not denials:
        lines.append("None found.")
    else:
        for name, capability in denials:
            lines.append(f"({name}) {capability}")
    return tuple(lines)

_SEATBELT_DENIAL_RE = re.compile(r"^Sandbox:\s*(.+?)\((\d+)\)\s+deny\(.*?\)\s*(.+)$")

def parse_message(msg: str) -> SandboxDenial | None:
    """Parse Rust seatbelt.rs DenialLogger sandbox eventMessage text."""

    match = _SEATBELT_DENIAL_RE.match(msg)
    if match is None:
        return None
    name, pid_str, capability = match.groups()
    try:
        pid = int(pid_str.strip())
    except ValueError:
        return None
    return SandboxDenial(pid=pid, name=name, capability=capability)

def collect_debug_sandbox_seatbelt_denials(
    log_lines: Iterable[str],
    pid_set: set[int] | frozenset[int],
) -> tuple[tuple[str, str], ...]:
    """Collect unique Seatbelt denials from ndjson log stream lines."""

    if not pid_set:
        return ()

    seen: set[tuple[str, str]] = set()
    denials: list[tuple[str, str]] = []
    for line in log_lines:
        try:
            payload = json.loads(line)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        msg = payload.get("eventMessage")
        if not isinstance(msg, str):
            continue
        parsed = parse_message(msg)
        if parsed is None or parsed.pid not in pid_set:
            continue
        denial = (parsed.name, parsed.capability)
        if denial in seen:
            continue
        seen.add(denial)
        denials.append(denial)
    return tuple(denials)

def finish_debug_sandbox_denial_logger_plan(
    plan: DebugSandboxDenialLoggerPlan,
    *,
    collector: Callable[[], Sequence[tuple[str, str]]] | None = None,
) -> DebugSandboxDenialLogResult:
    """Collect and format Seatbelt denials after the child has exited."""

    if not plan.enabled:
        return DebugSandboxDenialLogResult(
            enabled=False,
            denials=(),
            output_lines=(),
        )

    denials = tuple(collector() if collector is not None else ())
    return DebugSandboxDenialLogResult(
        enabled=True,
        denials=denials,
        output_lines=format_debug_sandbox_denial_summary(denials),
    )

