"""Linux sandbox command request helpers.

Ported from the pure argument/request construction portions of
``codex/codex-rs/core/src/landlock.rs`` and
``codex/codex-rs/sandboxing/src/landlock.rs``. Actual Linux sandbox execution
and network proxy environment mutation remain runtime boundaries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

from pycodex.core.spawn import SpawnChildRequest, StdioPolicy, build_spawn_child_request
from pycodex.protocol import NetworkSandboxPolicy, PermissionProfile


CODEX_LINUX_SANDBOX_ARG0 = "codex-linux-sandbox"


def _as_posix_path(value: str | Path) -> str:
    return str(Path(value).as_posix())


def allow_network_for_proxy(enforce_managed_network: bool) -> bool:
    if not isinstance(enforce_managed_network, bool):
        raise TypeError("enforce_managed_network must be a bool")
    return enforce_managed_network


def create_linux_sandbox_command_args_for_permission_profile(
    command: Sequence[str],
    command_cwd: str | Path,
    permission_profile: PermissionProfile,
    sandbox_policy_cwd: str | Path,
    use_legacy_landlock: bool,
    allow_network_for_proxy: bool,
) -> list[str]:
    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError("permission_profile must be a PermissionProfile")
    if not isinstance(use_legacy_landlock, bool):
        raise TypeError("use_legacy_landlock must be a bool")
    if not isinstance(allow_network_for_proxy, bool):
        raise TypeError("allow_network_for_proxy must be a bool")
    linux_cmd = [
        "--sandbox-policy-cwd",
        _as_posix_path(sandbox_policy_cwd),
        "--command-cwd",
        _as_posix_path(command_cwd),
        "--permission-profile",
        json.dumps(permission_profile.to_mapping(), separators=(",", ":"), ensure_ascii=False),
    ]
    if use_legacy_landlock:
        linux_cmd.append("--use-legacy-landlock")
    if allow_network_for_proxy:
        linux_cmd.append("--allow-network-for-proxy")
    linux_cmd.append("--")
    linux_cmd.extend(_string_sequence(command, "command"))
    return linux_cmd


def create_linux_sandbox_command_args(
    command: Sequence[str],
    command_cwd: str | Path,
    sandbox_policy_cwd: str | Path,
    use_legacy_landlock: bool,
    allow_network_for_proxy: bool,
) -> list[str]:
    if not isinstance(use_legacy_landlock, bool):
        raise TypeError("use_legacy_landlock must be a bool")
    if not isinstance(allow_network_for_proxy, bool):
        raise TypeError("allow_network_for_proxy must be a bool")
    linux_cmd = [
        "--sandbox-policy-cwd",
        _as_posix_path(sandbox_policy_cwd),
        "--command-cwd",
        _as_posix_path(command_cwd),
    ]
    if use_legacy_landlock:
        linux_cmd.append("--use-legacy-landlock")
    if allow_network_for_proxy:
        linux_cmd.append("--allow-network-for-proxy")
    linux_cmd.append("--")
    linux_cmd.extend(_string_sequence(command, "command"))
    return linux_cmd


def linux_sandbox_arg0(codex_linux_sandbox_exe: str | Path) -> str:
    path = Path(codex_linux_sandbox_exe)
    if path.name == CODEX_LINUX_SANDBOX_ARG0:
        return path.as_posix()
    return CODEX_LINUX_SANDBOX_ARG0


def build_linux_sandbox_spawn_child_request(
    codex_linux_sandbox_exe: str | Path,
    command: Sequence[str],
    command_cwd: str | Path,
    permission_profile: PermissionProfile,
    sandbox_policy_cwd: str | Path,
    use_legacy_landlock: bool,
    stdio_policy: StdioPolicy,
    env: Mapping[str, str] | None = None,
    network: object | None = None,
) -> SpawnChildRequest:
    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError("permission_profile must be a PermissionProfile")
    args = create_linux_sandbox_command_args_for_permission_profile(
        command,
        command_cwd,
        permission_profile,
        sandbox_policy_cwd,
        use_legacy_landlock,
        allow_network_for_proxy(False),
    )
    network_policy = permission_profile.network_sandbox_policy()
    if not isinstance(network_policy, NetworkSandboxPolicy):
        raise TypeError("permission_profile.network_sandbox_policy() must return NetworkSandboxPolicy")
    return build_spawn_child_request(
        Path(codex_linux_sandbox_exe),
        args,
        arg0=linux_sandbox_arg0(codex_linux_sandbox_exe),
        cwd=Path(command_cwd),
        network_sandbox_policy=network_policy,
        network=network,
        stdio_policy=stdio_policy,
        env=env or {},
    )


def _string_sequence(value: object, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of strings")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{label} must contain only strings")
    return tuple(value)


__all__ = [
    "CODEX_LINUX_SANDBOX_ARG0",
    "allow_network_for_proxy",
    "create_linux_sandbox_command_args",
    "build_linux_sandbox_spawn_child_request",
    "create_linux_sandbox_command_args_for_permission_profile",
    "linux_sandbox_arg0",
]
