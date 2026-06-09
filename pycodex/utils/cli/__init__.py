"""Shared CLI helpers ported from ``codex-rs/utils/cli``."""

from __future__ import annotations

import shlex
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


class ApprovalModeCliArg(Enum):
    UNTRUSTED = "untrusted"
    ON_FAILURE = "on-failure"
    ON_REQUEST = "on-request"
    NEVER = "never"

    def to_ask_for_approval(self) -> str:
        return {
            ApprovalModeCliArg.UNTRUSTED: "unless-trusted",
            ApprovalModeCliArg.ON_FAILURE: "on-failure",
            ApprovalModeCliArg.ON_REQUEST: "on-request",
            ApprovalModeCliArg.NEVER: "never",
        }[self]


class SandboxModeCliArg(Enum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"

    def to_sandbox_mode(self) -> str:
        return self.value


@dataclass
class CliConfigOverrides:
    raw_overrides: list[str] = field(default_factory=list)

    def prepend_root_overrides(self, root_overrides: "CliConfigOverrides") -> None:
        self.raw_overrides[0:0] = list(root_overrides.raw_overrides)

    def parse_overrides(self) -> list[tuple[str, Any]]:
        parsed: list[tuple[str, Any]] = []
        for raw in self.raw_overrides:
            key, sep, value_text = raw.partition("=")
            key = key.strip()
            if not sep:
                raise ValueError(f"Invalid override (missing '='): {raw}")
            if not key:
                raise ValueError(f"Empty key in override: {raw}")
            value_text = value_text.strip()
            try:
                value = tomllib.loads(f"_x_ = {value_text}")["_x_"]
            except Exception:
                value = value_text.strip().strip('"').strip("'")
            parsed.append((canonicalize_override_key(key), value))
        return parsed

    def apply_on_value(self, target: dict[str, Any]) -> None:
        if not isinstance(target, dict):
            raise TypeError("target must be a dict")
        for path, value in self.parse_overrides():
            apply_single_override(target, path, value)


def canonicalize_override_key(key: str) -> str:
    if key == "use_legacy_landlock":
        return "features.use_legacy_landlock"
    return key


def apply_single_override(root: dict[str, Any], path: str, value: Any) -> None:
    current: dict[str, Any] = root
    parts = path.split(".")
    for index, part in enumerate(parts):
        if index == len(parts) - 1:
            current[part] = value
            return
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child


def format_env_display(env: Mapping[str, str] | None, env_vars: Sequence[str]) -> str:
    parts: list[str] = []
    if env is not None:
        parts.extend(f"{key}=*****" for key in sorted(env))
    parts.extend(f"{var}=*****" for var in env_vars)
    return ", ".join(parts) if parts else "-"


def resume_command(thread_name: str | None, thread_id: object | None) -> str | None:
    target = thread_name if thread_name else (str(thread_id) if thread_id is not None else None)
    if not target:
        return None
    escaped = _shlex_join_one(target)
    if target.startswith("-"):
        return f"codex resume -- {escaped}"
    return f"codex resume {escaped}"


def resume_hint(thread_name: str | None, thread_id: object | None) -> str | None:
    if thread_id is None:
        return None
    if thread_name:
        return f"codex resume, then select {thread_name} ({thread_id})"
    return resume_command(None, thread_id)


@dataclass
class SharedCliOptions:
    images: list[Path] = field(default_factory=list)
    model: str | None = None
    oss: bool = False
    oss_provider: str | None = None
    config_profile_v2: str | None = None
    sandbox_mode: SandboxModeCliArg | None = None
    dangerously_bypass_approvals_and_sandbox: bool = False
    bypass_hook_trust: bool = False
    cwd: Path | None = None
    add_dir: list[Path] = field(default_factory=list)

    def inherit_exec_root_options(self, root: "SharedCliOptions") -> None:
        self_selected_sandbox = self.sandbox_mode is not None or self.dangerously_bypass_approvals_and_sandbox
        if self.model is None:
            self.model = root.model
        if root.oss:
            self.oss = True
        if self.oss_provider is None:
            self.oss_provider = root.oss_provider
        if self.config_profile_v2 is None:
            self.config_profile_v2 = root.config_profile_v2
        if self.sandbox_mode is None:
            self.sandbox_mode = root.sandbox_mode
        if not self_selected_sandbox:
            self.dangerously_bypass_approvals_and_sandbox = root.dangerously_bypass_approvals_and_sandbox
        if not self.bypass_hook_trust:
            self.bypass_hook_trust = root.bypass_hook_trust
        if self.cwd is None:
            self.cwd = root.cwd
        if root.images:
            self.images = list(root.images) + self.images
        if root.add_dir:
            self.add_dir = list(root.add_dir) + self.add_dir

    def apply_subcommand_overrides(self, subcommand: "SharedCliOptions") -> None:
        sub_selected_sandbox = subcommand.sandbox_mode is not None or subcommand.dangerously_bypass_approvals_and_sandbox
        if subcommand.model is not None:
            self.model = subcommand.model
        if subcommand.oss:
            self.oss = True
        if subcommand.oss_provider is not None:
            self.oss_provider = subcommand.oss_provider
        if subcommand.config_profile_v2 is not None:
            self.config_profile_v2 = subcommand.config_profile_v2
        if sub_selected_sandbox:
            self.sandbox_mode = subcommand.sandbox_mode
            self.dangerously_bypass_approvals_and_sandbox = subcommand.dangerously_bypass_approvals_and_sandbox
        if subcommand.bypass_hook_trust:
            self.bypass_hook_trust = True
        if subcommand.cwd is not None:
            self.cwd = subcommand.cwd
        if subcommand.images:
            self.images = list(subcommand.images)
        if subcommand.add_dir:
            self.add_dir.extend(subcommand.add_dir)


def _shlex_join_one(value: str) -> str:
    if value and all(ch.isalnum() or ch in "@%_+=:,./-" for ch in value):
        return value
    if "'" in value and '"' not in value:
        return '"' + value.replace('"', '\\"') + '"'
    return shlex.quote(value)


__all__ = [
    "ApprovalModeCliArg",
    "CliConfigOverrides",
    "SandboxModeCliArg",
    "SharedCliOptions",
    "apply_single_override",
    "canonicalize_override_key",
    "format_env_display",
    "resume_command",
    "resume_hint",
]
