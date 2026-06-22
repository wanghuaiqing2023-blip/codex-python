"""Linux sandbox helper CLI and execution planning.

Port slice for ``codex/codex-rs/linux-sandbox/src/linux_run_main.rs``.

The Rust helper ultimately enters Linux-only syscall and ``execvp`` boundaries.
This Python module mirrors the parse/permission/dispatch decisions and exposes
those OS boundaries as injectable hooks for tests and callers.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, NoReturn, Sequence

from pycodex.protocol import FileSystemSandboxPolicy, NetworkSandboxPolicy, PermissionProfile

from . import CODEX_LINUX_SANDBOX_ARG0
from . import bwrap
from . import landlock
from . import launcher
from . import proxy_routing


class LinuxRunStage(str, Enum):
    INNER_SECCOMP_THEN_EXEC = "inner_seccomp_then_exec"
    FULL_DISK_DIRECT_EXEC = "full_disk_direct_exec"
    BWRAP_OUTER = "bwrap_outer"
    LEGACY_LANDLOCK = "legacy_landlock"


@dataclass(frozen=True)
class LandlockCommand:
    sandbox_policy_cwd: Path
    command_cwd: Path | None
    permission_profile: PermissionProfile | None
    use_legacy_landlock: bool
    apply_seccomp_then_exec: bool
    allow_network_for_proxy: bool
    proxy_route_spec: str | None
    no_proc: bool
    command: tuple[str, ...]


@dataclass(frozen=True)
class EffectivePermissions:
    permission_profile: PermissionProfile
    file_system_sandbox_policy: FileSystemSandboxPolicy
    network_sandbox_policy: NetworkSandboxPolicy


@dataclass(frozen=True)
class LinuxRunMainPlan:
    stage: LinuxRunStage
    command: LandlockCommand
    effective_permissions: EffectivePermissions
    landlock_plan: landlock.LandlockApplicationPlan | None = None
    inner_command: tuple[str, ...] = ()
    bwrap_args: bwrap.BwrapArgs | None = None
    proxy_route_spec: str | None = None


ExecRunner = Callable[[Sequence[str]], object]
BwrapRunner = Callable[[bwrap.BwrapArgs], object]
ProxyRoutePreparer = Callable[[], str]
ProxyRouteActivator = Callable[[str], object]
CurrentExeResolver = Callable[[], str | Path]


def parse_args(argv: Sequence[str]) -> LandlockCommand:
    values = _string_sequence(argv, "argv")
    sandbox_policy_cwd: Path | None = None
    command_cwd: Path | None = None
    permission_profile: PermissionProfile | None = None
    use_legacy_landlock = False
    apply_seccomp_then_exec = False
    allow_network_for_proxy = False
    proxy_route_spec: str | None = None
    no_proc = False
    command: tuple[str, ...] | None = None

    index = 0
    while index < len(values):
        arg = values[index]
        if arg == "--":
            command = values[index + 1 :]
            break
        if arg == "--sandbox-policy-cwd":
            sandbox_policy_cwd = Path(_take_option_value(values, index, arg))
            index += 2
            continue
        if arg == "--command-cwd":
            command_cwd = Path(_take_option_value(values, index, arg))
            index += 2
            continue
        if arg == "--permission-profile":
            permission_profile = parse_permission_profile(_take_option_value(values, index, arg))
            index += 2
            continue
        if arg == "--use-legacy-landlock":
            use_legacy_landlock = True
            index += 1
            continue
        if arg == "--apply-seccomp-then-exec":
            apply_seccomp_then_exec = True
            index += 1
            continue
        if arg == "--allow-network-for-proxy":
            allow_network_for_proxy = True
            index += 1
            continue
        if arg == "--proxy-route-spec":
            proxy_route_spec = _take_option_value(values, index, arg)
            index += 2
            continue
        if arg == "--no-proc":
            no_proc = True
            index += 1
            continue
        raise ValueError(f"unknown linux sandbox option: {arg}")

    if sandbox_policy_cwd is None:
        raise ValueError("missing required option --sandbox-policy-cwd")
    if command is None:
        command = ()
    return LandlockCommand(
        sandbox_policy_cwd=sandbox_policy_cwd,
        command_cwd=command_cwd,
        permission_profile=permission_profile,
        use_legacy_landlock=use_legacy_landlock,
        apply_seccomp_then_exec=apply_seccomp_then_exec,
        allow_network_for_proxy=allow_network_for_proxy,
        proxy_route_spec=proxy_route_spec,
        no_proc=no_proc,
        command=command,
    )


def parse_permission_profile(value: str) -> PermissionProfile:
    try:
        data = json.loads(value)
        return PermissionProfile.from_mapping(data)
    except Exception as err:
        raise ValueError(f"invalid permission profile JSON: {err}") from err


def resolve_permission_profile(permission_profile: PermissionProfile | None) -> EffectivePermissions:
    if permission_profile is None:
        raise ValueError("missing permission profile configuration")
    file_system_sandbox_policy, network_sandbox_policy = permission_profile.to_runtime_permissions()
    return EffectivePermissions(
        permission_profile=permission_profile,
        file_system_sandbox_policy=file_system_sandbox_policy,
        network_sandbox_policy=network_sandbox_policy,
    )


def ensure_inner_stage_mode_is_valid(apply_seccomp_then_exec: bool, use_legacy_landlock: bool) -> None:
    if apply_seccomp_then_exec and use_legacy_landlock:
        raise ValueError("--apply-seccomp-then-exec is incompatible with --use-legacy-landlock")


def ensure_legacy_landlock_mode_supports_policy(
    use_legacy_landlock: bool,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    network_sandbox_policy: NetworkSandboxPolicy,
    sandbox_policy_cwd: Path | str,
) -> None:
    if use_legacy_landlock and file_system_sandbox_policy.needs_direct_runtime_enforcement(
        network_sandbox_policy,
        sandbox_policy_cwd,
    ):
        raise ValueError(
            "permission profiles requiring direct runtime enforcement are incompatible with --use-legacy-landlock"
        )


def bwrap_network_mode(
    network_sandbox_policy: NetworkSandboxPolicy,
    allow_network_for_proxy: bool,
) -> bwrap.BwrapNetworkMode:
    if allow_network_for_proxy:
        return bwrap.BwrapNetworkMode.PROXY_ONLY
    if network_sandbox_policy.is_enabled():
        return bwrap.BwrapNetworkMode.FULL_ACCESS
    return bwrap.BwrapNetworkMode.ISOLATED


def build_bwrap_argv(
    inner: Sequence[str],
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    sandbox_policy_cwd: Path | str,
    command_cwd: Path | str,
    options: bwrap.BwrapOptions,
) -> bwrap.BwrapArgs:
    bwrap_args = bwrap.create_bwrap_command_args(
        inner,
        file_system_sandbox_policy,
        sandbox_policy_cwd,
        command_cwd,
        options,
    )
    return bwrap.BwrapArgs(
        args=("bwrap", *bwrap_args.args),
        preserved_files=bwrap_args.preserved_files,
        synthetic_mount_targets=bwrap_args.synthetic_mount_targets,
        protected_create_targets=bwrap_args.protected_create_targets,
    )


def apply_inner_command_argv0_for_launcher(
    argv: list[str],
    supports_argv0: bool,
    argv0_fallback_command: str,
) -> None:
    try:
        command_separator_index = argv.index("--")
    except ValueError as err:
        raise ValueError("bubblewrap argv is missing command separator '--'") from err
    if supports_argv0:
        argv[command_separator_index:command_separator_index] = ["--argv0", CODEX_LINUX_SANDBOX_ARG0]
        return
    command_index = command_separator_index + 1
    if command_index >= len(argv):
        raise ValueError("bubblewrap argv is missing inner command after '--'")
    argv[command_index] = argv0_fallback_command


def apply_inner_command_argv0(
    argv: list[str],
    *,
    supports_argv0: bool | None = None,
    argv0_fallback_command: str | None = None,
) -> None:
    if supports_argv0 is None:
        supports_argv0 = launcher.preferred_bwrap_supports_argv0()
    if argv0_fallback_command is None:
        argv0_fallback_command = sys.argv[0] if sys.argv else CODEX_LINUX_SANDBOX_ARG0
    apply_inner_command_argv0_for_launcher(argv, supports_argv0, argv0_fallback_command)


def is_proc_mount_failure(stderr: str) -> bool:
    return (
        "Can't mount proc" in stderr
        and "/newroot/proc" in stderr
        and any(reason in stderr for reason in ("Invalid argument", "Operation not permitted", "Permission denied"))
    )


def build_inner_seccomp_command(
    *,
    sandbox_policy_cwd: Path | str,
    command_cwd: Path | str | None,
    permission_profile: PermissionProfile,
    allow_network_for_proxy: bool,
    proxy_route_spec: str | None,
    command: Sequence[str],
    current_exe: str | Path | None = None,
    current_exe_resolver: CurrentExeResolver | None = None,
) -> tuple[str, ...]:
    if current_exe is None:
        current_exe = current_exe_resolver() if current_exe_resolver is not None else _current_exe()
    inner: list[str] = [
        Path(current_exe).as_posix(),
        "--sandbox-policy-cwd",
        Path(sandbox_policy_cwd).as_posix(),
    ]
    if command_cwd is not None:
        inner.extend(["--command-cwd", Path(command_cwd).as_posix()])
    inner.extend(
        [
            "--permission-profile",
            json.dumps(permission_profile.to_mapping(), separators=(",", ":"), ensure_ascii=False),
            "--apply-seccomp-then-exec",
        ]
    )
    if allow_network_for_proxy:
        if proxy_route_spec is None:
            raise ValueError("managed proxy mode requires a proxy route spec")
        inner.extend(["--allow-network-for-proxy", "--proxy-route-spec", proxy_route_spec])
    inner.append("--")
    inner.extend(_string_sequence(command, "command"))
    return tuple(inner)


def plan_linux_run_main(
    argv: Sequence[str],
    *,
    current_exe_resolver: CurrentExeResolver | None = None,
    proxy_route_preparer: ProxyRoutePreparer | None = None,
    proc_mount_supported: bool | None = True,
    bwrap_supports_argv0: bool = True,
    argv0_fallback_command: str = CODEX_LINUX_SANDBOX_ARG0,
) -> LinuxRunMainPlan:
    command = parse_args(argv)
    if not command.command:
        raise ValueError("No command specified to execute.")
    ensure_inner_stage_mode_is_valid(command.apply_seccomp_then_exec, command.use_legacy_landlock)
    effective = resolve_permission_profile(command.permission_profile)
    ensure_legacy_landlock_mode_supports_policy(
        command.use_legacy_landlock,
        effective.file_system_sandbox_policy,
        effective.network_sandbox_policy,
        command.sandbox_policy_cwd,
    )

    if command.apply_seccomp_then_exec:
        if command.allow_network_for_proxy and command.proxy_route_spec is None:
            raise ValueError("managed proxy mode requires --proxy-route-spec")
        landlock_plan = landlock.plan_permission_profile_application(
            effective.permission_profile,
            command.sandbox_policy_cwd,
            apply_landlock_fs=False,
            allow_network_for_proxy=command.allow_network_for_proxy,
            proxy_routed_network=command.allow_network_for_proxy,
        )
        return LinuxRunMainPlan(
            stage=LinuxRunStage.INNER_SECCOMP_THEN_EXEC,
            command=command,
            effective_permissions=effective,
            landlock_plan=landlock_plan,
            proxy_route_spec=command.proxy_route_spec,
        )

    if (
        effective.file_system_sandbox_policy.has_full_disk_write_access()
        and not command.allow_network_for_proxy
    ):
        landlock_plan = landlock.plan_permission_profile_application(
            effective.permission_profile,
            command.sandbox_policy_cwd,
            apply_landlock_fs=False,
            allow_network_for_proxy=command.allow_network_for_proxy,
            proxy_routed_network=False,
        )
        return LinuxRunMainPlan(
            stage=LinuxRunStage.FULL_DISK_DIRECT_EXEC,
            command=command,
            effective_permissions=effective,
            landlock_plan=landlock_plan,
        )

    if not command.use_legacy_landlock:
        proxy_route_spec = None
        if command.allow_network_for_proxy:
            proxy_route_spec = proxy_route_preparer() if proxy_route_preparer is not None else proxy_routing.prepare_host_proxy_route_spec()
        command_cwd = command.command_cwd or command.sandbox_policy_cwd
        inner = build_inner_seccomp_command(
            sandbox_policy_cwd=command.sandbox_policy_cwd,
            command_cwd=command.command_cwd,
            permission_profile=effective.permission_profile,
            allow_network_for_proxy=command.allow_network_for_proxy,
            proxy_route_spec=proxy_route_spec,
            command=command.command,
            current_exe_resolver=current_exe_resolver,
        )
        network_mode = bwrap_network_mode(effective.network_sandbox_policy, command.allow_network_for_proxy)
        mount_proc = (not command.no_proc) and bool(proc_mount_supported)
        options = bwrap.BwrapOptions(mount_proc=mount_proc, network_mode=network_mode)
        bwrap_args = build_bwrap_argv(
            inner,
            effective.file_system_sandbox_policy,
            command.sandbox_policy_cwd,
            command_cwd,
            options,
        )
        argv_with_arg0 = list(bwrap_args.args)
        apply_inner_command_argv0_for_launcher(argv_with_arg0, bwrap_supports_argv0, argv0_fallback_command)
        bwrap_args = bwrap.BwrapArgs(
            args=tuple(argv_with_arg0),
            preserved_files=bwrap_args.preserved_files,
            synthetic_mount_targets=bwrap_args.synthetic_mount_targets,
            protected_create_targets=bwrap_args.protected_create_targets,
        )
        return LinuxRunMainPlan(
            stage=LinuxRunStage.BWRAP_OUTER,
            command=command,
            effective_permissions=effective,
            inner_command=inner,
            bwrap_args=bwrap_args,
            proxy_route_spec=proxy_route_spec,
        )

    landlock_plan = landlock.plan_permission_profile_application(
        effective.permission_profile,
        command.sandbox_policy_cwd,
        apply_landlock_fs=True,
        allow_network_for_proxy=command.allow_network_for_proxy,
        proxy_routed_network=False,
    )
    return LinuxRunMainPlan(
        stage=LinuxRunStage.LEGACY_LANDLOCK,
        command=command,
        effective_permissions=effective,
        landlock_plan=landlock_plan,
    )


def run_main(
    argv: Sequence[str] | None = None,
    *,
    exec_runner: ExecRunner | None = None,
    bwrap_runner: BwrapRunner | None = None,
    proxy_route_preparer: ProxyRoutePreparer | None = None,
    proxy_route_activator: ProxyRouteActivator | None = None,
    proc_mount_supported: bool | None = True,
) -> object:
    """Run the Linux sandbox helper or delegate to injected runtime hooks."""

    plan = plan_linux_run_main(
        sys.argv[1:] if argv is None else argv,
        proxy_route_preparer=proxy_route_preparer,
        proc_mount_supported=proc_mount_supported,
    )
    if plan.stage is LinuxRunStage.BWRAP_OUTER:
        if plan.bwrap_args is None:
            raise RuntimeError("bwrap stage missing argv")
        if bwrap_runner is not None:
            return bwrap_runner(plan.bwrap_args)
        return launcher.exec_bwrap(plan.bwrap_args.args, plan.bwrap_args.preserved_files)

    if plan.stage is LinuxRunStage.INNER_SECCOMP_THEN_EXEC:
        if plan.command.allow_network_for_proxy:
            spec = plan.command.proxy_route_spec
            if spec is None:
                raise RuntimeError("managed proxy mode requires --proxy-route-spec")
            activator = proxy_route_activator or proxy_routing.activate_proxy_routes_in_netns
            activator(spec)
        landlock.apply_permission_profile_to_current_thread(
            plan.effective_permissions.permission_profile,
            plan.command.sandbox_policy_cwd,
            apply_landlock_fs=False,
            allow_network_for_proxy=plan.command.allow_network_for_proxy,
            proxy_routed_network=plan.command.allow_network_for_proxy,
        )
    elif plan.stage is LinuxRunStage.FULL_DISK_DIRECT_EXEC:
        landlock.apply_permission_profile_to_current_thread(
            plan.effective_permissions.permission_profile,
            plan.command.sandbox_policy_cwd,
            apply_landlock_fs=False,
            allow_network_for_proxy=plan.command.allow_network_for_proxy,
            proxy_routed_network=False,
        )
    elif plan.stage is LinuxRunStage.LEGACY_LANDLOCK:
        landlock.apply_permission_profile_to_current_thread(
            plan.effective_permissions.permission_profile,
            plan.command.sandbox_policy_cwd,
            apply_landlock_fs=True,
            allow_network_for_proxy=plan.command.allow_network_for_proxy,
            proxy_routed_network=False,
        )

    runner = exec_runner or exec_or_panic
    return runner(plan.command.command)


def exec_or_panic(command: Sequence[str]) -> NoReturn:
    args = _string_sequence(command, "command")
    try:
        os.execvp(args[0], list(args))
    except OSError as err:
        raise RuntimeError(f"Failed to execvp {args[0]}: {err}") from err


def _current_exe() -> str:
    if sys.argv:
        return sys.argv[0]
    return CODEX_LINUX_SANDBOX_ARG0


def _take_option_value(argv: tuple[str, ...], index: int, option: str) -> str:
    value_index = index + 1
    if value_index >= len(argv) or argv[value_index] == "--":
        raise ValueError(f"{option} requires a value")
    return argv[value_index]


def _string_sequence(value: object, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of strings")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{label} must contain only strings")
    return tuple(value)


__all__ = [
    "EffectivePermissions",
    "LandlockCommand",
    "LinuxRunMainPlan",
    "LinuxRunStage",
    "apply_inner_command_argv0",
    "apply_inner_command_argv0_for_launcher",
    "build_bwrap_argv",
    "build_inner_seccomp_command",
    "bwrap_network_mode",
    "ensure_inner_stage_mode_is_valid",
    "ensure_legacy_landlock_mode_supports_policy",
    "exec_or_panic",
    "is_proc_mount_failure",
    "parse_args",
    "parse_permission_profile",
    "plan_linux_run_main",
    "resolve_permission_profile",
    "run_main",
]
