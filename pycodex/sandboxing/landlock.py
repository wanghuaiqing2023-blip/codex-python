"""Landlock helper argv surface for ``codex-sandboxing``.

Rust counterpart: ``codex/codex-rs/sandboxing/src/landlock.rs``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from pycodex.linux_sandbox import (
    CODEX_LINUX_SANDBOX_ARG0,
    allow_network_for_proxy,
    create_linux_sandbox_command_args,
    create_linux_sandbox_command_args_for_permission_profile,
    linux_sandbox_arg0,
)
from pycodex.protocol import PermissionProfile


def create_landlock_command_args(
    command: Sequence[str],
    command_cwd: str | Path,
    sandbox_policy_cwd: str | Path,
    use_legacy_landlock: bool,
    allow_proxy_network: bool,
) -> list[str]:
    """Mirror Rust's private ``create_linux_sandbox_command_args`` helper."""

    return create_linux_sandbox_command_args(
        command,
        command_cwd,
        sandbox_policy_cwd,
        use_legacy_landlock,
        allow_proxy_network,
    )


def create_landlock_command_args_for_permission_profile(
    command: Sequence[str],
    command_cwd: str | Path,
    permission_profile: PermissionProfile,
    sandbox_policy_cwd: str | Path,
    use_legacy_landlock: bool,
    allow_proxy_network: bool,
) -> list[str]:
    """Mirror Rust's public permission-profile argv builder."""

    return create_linux_sandbox_command_args_for_permission_profile(
        command,
        command_cwd,
        permission_profile,
        sandbox_policy_cwd,
        use_legacy_landlock,
        allow_proxy_network,
    )


__all__ = [
    "CODEX_LINUX_SANDBOX_ARG0",
    "allow_network_for_proxy",
    "create_landlock_command_args",
    "create_landlock_command_args_for_permission_profile",
    "create_linux_sandbox_command_args",
    "create_linux_sandbox_command_args_for_permission_profile",
    "linux_sandbox_arg0",
]
