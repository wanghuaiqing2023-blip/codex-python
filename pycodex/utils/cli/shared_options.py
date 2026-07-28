"""Shared CLI option precedence from Rust ``shared_options.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .sandbox_mode_cli_arg import SandboxModeCliArg


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
        selected_sandbox = (
            self.sandbox_mode is not None
            or self.dangerously_bypass_approvals_and_sandbox
        )
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
        if not selected_sandbox:
            self.dangerously_bypass_approvals_and_sandbox = (
                root.dangerously_bypass_approvals_and_sandbox
            )
        if not self.bypass_hook_trust:
            self.bypass_hook_trust = root.bypass_hook_trust
        if self.cwd is None:
            self.cwd = root.cwd
        if root.images:
            self.images = list(root.images) + self.images
        if root.add_dir:
            self.add_dir = list(root.add_dir) + self.add_dir

    def apply_subcommand_overrides(self, subcommand: "SharedCliOptions") -> None:
        selected_sandbox = (
            subcommand.sandbox_mode is not None
            or subcommand.dangerously_bypass_approvals_and_sandbox
        )
        if subcommand.model is not None:
            self.model = subcommand.model
        if subcommand.oss:
            self.oss = True
        if subcommand.oss_provider is not None:
            self.oss_provider = subcommand.oss_provider
        if subcommand.config_profile_v2 is not None:
            self.config_profile_v2 = subcommand.config_profile_v2
        if selected_sandbox:
            self.sandbox_mode = subcommand.sandbox_mode
            self.dangerously_bypass_approvals_and_sandbox = (
                subcommand.dangerously_bypass_approvals_and_sandbox
            )
        if subcommand.bypass_hook_trust:
            self.bypass_hook_trust = True
        if subcommand.cwd is not None:
            self.cwd = subcommand.cwd
        if subcommand.images:
            self.images = list(subcommand.images)
        if subcommand.add_dir:
            self.add_dir.extend(subcommand.add_dir)


__all__ = ["SharedCliOptions"]
