"""Debug sandbox helpers.

Ported from ``codex/codex-rs/cli/src/debug_sandbox.rs``.
"""

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

WINDOWS_STDIN_FORWARD_CHUNK_SIZE = 8 * 1024


def _debug_sandbox_path_arg(value: str | Path) -> str:
    """Render debug sandbox path args without host OS separator rewriting."""

    if isinstance(value, Path):
        return value.as_posix()
    return str(value)


@dataclass(frozen=True)
class DebugSandboxExecutionPlan:
    """Python execution plan for the debug sandbox command path."""

    command: tuple[str, ...]
    cwd: Path | None
    permission_profile_cwd: Path | None
    backend_program: Path | None
    backend_args: tuple[str, ...]
    child_arg0: str | None
    env: dict[str, str]
    sandbox_type: str
    permissions_profile: str | None
    managed_requirements_mode: "ManagedRequirementsMode"
    include_managed_config: bool


@dataclass(frozen=True)
class DebugSandboxConfigLoadPlan:
    """Plan-level mirror of Rust debug sandbox config loading decisions."""

    cli_overrides: tuple[tuple[str, object], ...]
    harness_cwd: Path | None
    codex_linux_sandbox_exe: Path | None
    codex_home: Path | None
    fallback_cwd: Path | None
    loader_overrides: dict[str, object]
    strict_config: bool
    uses_legacy_sandbox_mode_override: bool
    should_retry_with_read_only: bool


@dataclass(frozen=True)
class DebugSandboxConfigLoadResult:
    """Result of executing the debug sandbox config-loader boundary."""

    config: object
    attempts: tuple[tuple[tuple[tuple[str, object], ...], str | None], ...]
    retried_with_read_only: bool


@dataclass(frozen=True)
class DebugSandboxConfigBuilderResult:
    """Config object returned by the default debug sandbox ConfigBuilder bridge."""

    config_layer_stack: object
    effective_config: dict[str, object]
    harness_overrides: dict[str, object]
    cli_overrides: tuple[tuple[str, object], ...]
    loader_overrides: dict[str, object]
    strict_config: bool
    codex_home: Path | None
    fallback_cwd: Path | None


@dataclass(frozen=True)
class DebugSandboxPlatformImplementationDecision:
    """Ownership decision for platform-specific debug sandbox implementation."""

    concern: str
    owner: str
    status: str
    debug_sandbox_role: str


@dataclass(frozen=True)
class DebugSandboxNetworkPlan:
    """Plan-level mirror of managed network proxy decisions."""

    should_start_proxy: bool
    permission_profile: str | None
    managed_network_requirements_enabled: bool
    audit_metadata: dict[str, object]
    proxy_env: dict[str, str]
    lifetime: str = "child_process"


@dataclass(frozen=True)
class DebugSandboxNetworkProxyStartResult:
    """Result of the managed network proxy startup boundary."""

    started: bool
    proxy_env: dict[str, str]
    lifetime: str


@dataclass(frozen=True)
class DebugSandboxBackendArgsPlan:
    """Inputs passed to the platform-specific backend argument builders."""

    sandbox_type: str
    command: tuple[str, ...]
    cwd: Path | None
    permission_profile_cwd: Path | None
    permission_profile: str | None
    use_legacy_landlock: bool
    allow_network_for_proxy: bool
    extra_allow_unix_sockets: tuple[Path, ...]
    enforce_managed_network: bool = False


@dataclass(frozen=True)
class DebugSandboxBackendArgsBuildResult:
    """Result produced by a platform backend argument builder."""

    sandbox_type: str
    args: tuple[str, ...]
    builder_invoked: bool
    adapter: str | None = None


@dataclass(frozen=True)
class DebugSandboxWindowsSessionPlan:
    """Inputs passed to the Rust Windows sandbox session spawners."""

    mode: str
    permission_profile: object | None
    permission_profile_cwd: Path | None
    codex_home: Path | None
    command: tuple[str, ...]
    cwd: Path | None
    env: dict[str, str]
    read_roots_override: tuple[Path, ...] | None
    read_roots_include_platform_defaults: bool
    write_roots_override: tuple[Path, ...] | None
    deny_read_paths_override: tuple[Path, ...]
    deny_write_paths_override: tuple[Path, ...]
    tty: bool
    stdin_open: bool
    private_desktop: bool
    output_drain_timeout_seconds: int


@dataclass(frozen=True)
class DebugSandboxWindowsSessionRunResult:
    """Result of spawning a Windows sandbox session boundary."""

    mode: str
    exit_code: int
    output_drain_timeout_seconds: int
    error_message: str | None
    stdout: bytes = b""
    stderr: bytes = b""


@dataclass(frozen=True)
class DebugSandboxWindowsSessionControlResult:
    """Control-flow decisions after a Windows sandbox session is spawned."""

    exit_code: int
    requested_terminate: bool
    closed_stdin_after_eof: bool
    aborted_stdin_close_task: bool
    waited_for_output_drain: bool
    output_drain_timeout_seconds: int


@dataclass(frozen=True)
class DebugSandboxWindowsSessionIoBridgeResult:
    """Observed Windows session stdio bridge behavior."""

    stdin_chunks: tuple[bytes, ...]
    stdout: bytes
    stderr: bytes
    control: DebugSandboxWindowsSessionControlResult
    actions: tuple[str, ...]


@dataclass(frozen=True)
class DebugSandboxWindowsSpawnBridgeResult:
    """Combined Windows session spawn plus stdio bridge result."""

    run: DebugSandboxWindowsSessionRunResult
    io: DebugSandboxWindowsSessionIoBridgeResult | None


@dataclass(frozen=True)
class DebugSandboxDeferredNativeBoundary:
    """Native behavior intentionally left behind injectable debug-sandbox adapters."""

    concern: str
    upstream_owner: str
    python_boundary: str
    rationale: str


@dataclass(frozen=True)
class DebugSandboxEntrypointPlan:
    """Inputs forwarded by the public debug sandbox entrypoints."""

    sandbox_type: str
    command: tuple[str, ...]
    cwd: Path | None
    permissions_profile: str | None
    managed_requirements_mode: "ManagedRequirementsMode"
    config_overrides: tuple[tuple[str, object], ...]
    codex_linux_sandbox_exe: Path | None
    loader_overrides: dict[str, object]
    log_denials: bool
    allow_unix_sockets: tuple[Path, ...]


@dataclass(frozen=True)
class DebugSandboxChildSpawnPlan:
    """Inputs and env decisions used by Rust's child spawn helper."""

    program: Path
    args: tuple[str, ...]
    arg0: str | None
    cwd: Path
    env: dict[str, str]
    env_clear: bool
    stdin: str
    stdout: str
    stderr: str
    kill_on_drop: bool


@dataclass(frozen=True)
class DebugSandboxChildRunResult:
    """Result captured after running a child spawn plan."""

    returncode: int
    argv: tuple[str, ...]
    executable: str | None
    cwd: Path
    env: dict[str, str]


@dataclass(frozen=True)
class DebugSandboxChildRunExitStatusPlan:
    """Child run result paired with the Rust-compatible exit-status plan."""

    child: DebugSandboxChildRunResult
    exit_status: "DebugSandboxExitStatusPlan"


@dataclass(frozen=True)
class DebugSandboxPidTracker:
    """Lightweight counterpart for Rust's macOS debug sandbox PidTracker."""

    root_pid: int
    list_children: Callable[[int], Sequence[int]] | None = None
    is_alive: Callable[[int], bool] | None = None

    @classmethod
    def new(
        cls,
        root_pid: int,
        *,
        list_children: Callable[[int], Sequence[int]] | None = None,
        is_alive: Callable[[int], bool] | None = None,
    ) -> "DebugSandboxPidTracker | None":
        if root_pid <= 0:
            return None
        return cls(root_pid, list_children=list_children, is_alive=is_alive)

    async def stop(self) -> set[int]:
        return collect_debug_sandbox_descendant_pids(
            self.root_pid,
            list_children=self.list_children,
            is_alive=self.is_alive,
        )


@dataclass(frozen=True)
class DebugSandboxNetworkEnvApplicationPlan:
    """Environment mutations applied around the managed network proxy."""

    sandbox_type: str
    network_present: bool
    network_sandbox_enabled: bool
    env_after_apply: dict[str, str]
    final_env: dict[str, str]
    applies_seatbelt_marker: bool
    disabled_network_marker_value: str | None


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
class DebugSandboxSeatbeltDenial:
    """Parsed macOS sandbox denial log entry."""

    pid: int
    name: str
    capability: str


@dataclass(frozen=True)
class DebugSandboxExecutionWithDenialsResult:
    """Shared execution result with optional post-wait denial output."""

    child_exit: DebugSandboxChildRunExitStatusPlan
    denial_log: DebugSandboxDenialLogResult


@dataclass(frozen=True)
class DebugSandboxRunFlowPlan:
    """Phase ordering for Rust's shared run_command_under_sandbox path."""

    sandbox_type: str
    platform: str
    phases: tuple[str, ...]
    strict_config: bool
    cwd_source: str
    permission_profile_cwd_source: str
    windows_special_case_before_denial_logger: bool
    denial_logger_before_network_proxy: bool
    child_wait_before_exit_status: bool
    handles_exit_status: bool


@dataclass(frozen=True)
class DebugSandboxRunFlowExecutionResult:
    """Observed execution of a debug sandbox run-flow plan."""

    sandbox_type: str
    executed_phases: tuple[str, ...]
    missing_handlers: tuple[str, ...]
    terminal_phase: str | None
    outputs: tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class DebugSandboxRunFlowHandlerWiring:
    """Handler map prepared for a debug sandbox run-flow plan."""

    sandbox_type: str
    handlers: Mapping[str, Callable[[], object]]
    wired_phases: tuple[str, ...]
    missing_phases: tuple[str, ...]
    terminal_phases: tuple[str, ...]


@dataclass(frozen=True)
class DebugSandboxExitStatusPlan:
    """Process exit-code decision after the sandbox child exits."""

    platform: str
    child_exit_code: int | None
    child_signal: int | None
    process_exit_code: int
    used_signal_fallback: bool
    used_generic_fallback: bool


class ManagedRequirementsMode(str, Enum):
    """Whether debug sandbox config loading includes managed requirements."""

    INCLUDE = "include"
    IGNORE = "ignore"

    @classmethod
    def for_profile_invocation(
        cls,
        permissions_profile: str | None,
        include_managed_config: bool,
    ) -> "ManagedRequirementsMode":
        if permissions_profile is not None and not include_managed_config:
            return cls.IGNORE
        return cls.INCLUDE


def cli_overrides_use_legacy_sandbox_mode(cli_overrides: list[tuple[str, object]]) -> bool:
    """Return whether CLI overrides explicitly include legacy ``sandbox_mode``."""

    return any(key == "sandbox_mode" for key, _value in cli_overrides)


def with_permissions_profile_override(
    cli_overrides: list[tuple[str, object]],
    permissions_profile: str | None,
) -> list[tuple[str, object]]:
    """Return CLI overrides with an explicit debug-sandbox permission profile applied."""

    overrides = list(cli_overrides)
    if permissions_profile is not None:
        overrides.append(("default_permissions", permissions_profile))
    return overrides


def config_uses_permission_profiles(config: object) -> bool:
    """Return whether debug sandbox config has an active permission profile."""

    effective_config = config.config_layer_stack.effective_config()  # type: ignore[attr-defined]
    return effective_config.get("default_permissions") is not None


def should_default_legacy_config_to_read_only(
    config: object,
    cli_overrides: list[tuple[str, object]],
) -> bool:
    """Return whether legacy debug sandbox config should default to read-only."""

    if config_uses_permission_profiles(config):
        return False
    if cli_overrides_use_legacy_sandbox_mode(cli_overrides):
        return False
    return True


def loader_overrides_with_managed_requirements_mode(
    loader_overrides: dict[str, object],
    managed_requirements_mode: ManagedRequirementsMode,
) -> dict[str, object]:
    """Return loader overrides adjusted for debug sandbox managed requirements."""

    overrides = dict(loader_overrides)
    if managed_requirements_mode is ManagedRequirementsMode.IGNORE:
        overrides["ignore_managed_requirements"] = True
    return overrides


def build_debug_sandbox_config_load_plan(
    cli_overrides: Sequence[tuple[str, object]],
    *,
    permissions_profile: str | None = None,
    cwd: str | Path | None = None,
    codex_linux_sandbox_exe: str | Path | None = None,
    codex_home: str | Path | None = None,
    managed_requirements_mode: ManagedRequirementsMode = ManagedRequirementsMode.INCLUDE,
    loader_overrides: Mapping[str, object] | None = None,
    strict_config: bool = False,
    config_uses_permission_profile: bool = False,
) -> DebugSandboxConfigLoadPlan:
    """Build the pure decision plan for debug sandbox config loading."""

    overrides = with_permissions_profile_override(list(cli_overrides), permissions_profile)
    uses_legacy = cli_overrides_use_legacy_sandbox_mode(overrides)
    should_retry = not config_uses_permission_profile and not uses_legacy
    codex_home_path = Path(codex_home) if codex_home is not None else None
    return DebugSandboxConfigLoadPlan(
        cli_overrides=tuple(overrides),
        harness_cwd=Path(cwd) if cwd is not None else None,
        codex_linux_sandbox_exe=Path(codex_linux_sandbox_exe)
        if codex_linux_sandbox_exe is not None
        else None,
        codex_home=codex_home_path,
        fallback_cwd=codex_home_path,
        loader_overrides=loader_overrides_with_managed_requirements_mode(
            dict(loader_overrides or {}),
            managed_requirements_mode,
        ),
        strict_config=strict_config,
        uses_legacy_sandbox_mode_override=uses_legacy,
        should_retry_with_read_only=should_retry,
    )


def run_debug_sandbox_config_load_plan(
    plan: DebugSandboxConfigLoadPlan,
    loader: Callable[[DebugSandboxConfigLoadPlan, tuple[tuple[str, object], ...], str | None], object],
) -> DebugSandboxConfigLoadResult:
    """Execute the Rust-style debug sandbox config-loading boundary."""

    attempts: list[tuple[tuple[tuple[str, object], ...], str | None]] = []
    attempts.append((plan.cli_overrides, None))
    config = loader(plan, plan.cli_overrides, None)
    if plan.should_retry_with_read_only:
        attempts.append((plan.cli_overrides, "read-only"))
        config = loader(plan, plan.cli_overrides, "read-only")
    return DebugSandboxConfigLoadResult(
        config=config,
        attempts=tuple(attempts),
        retried_with_read_only=plan.should_retry_with_read_only,
    )


def build_debug_sandbox_config_with_loader_overrides_from_plan(
    plan: DebugSandboxConfigLoadPlan,
    cli_overrides: tuple[tuple[str, object], ...],
    sandbox_mode: str | None,
    builder_factory: Callable[[], object],
) -> object:
    """Run a ConfigBuilder-shaped object with Rust debug-sandbox inputs."""

    builder = builder_factory()
    harness_overrides = {
        "cwd": plan.harness_cwd,
        "codex_linux_sandbox_exe": plan.codex_linux_sandbox_exe,
        "sandbox_mode": sandbox_mode,
    }
    builder = builder.cli_overrides(cli_overrides)
    builder = builder.harness_overrides(harness_overrides)
    builder = builder.strict_config(plan.strict_config)
    builder = builder.loader_overrides(plan.loader_overrides)
    if plan.codex_home is not None:
        builder = builder.codex_home(plan.codex_home)
        builder = builder.fallback_cwd(plan.fallback_cwd)
    return builder.build()


def _loader_overrides_from_mapping(loader_overrides: Mapping[str, object]) -> object:
    """Build a config ``LoaderOverrides`` object from debug-sandbox mapping data."""

    from dataclasses import fields

    from pycodex.config import LoaderOverrides

    field_names = {field.name for field in fields(LoaderOverrides)}
    values = {
        key: Path(value) if key.endswith("_path") and value is not None else value
        for key, value in loader_overrides.items()
        if key in field_names
    }
    return LoaderOverrides(**values)


class DebugSandboxDefaultConfigBuilder:
    """Minimal ConfigBuilder-shaped bridge backed by ``pycodex.config``."""

    def __init__(self) -> None:
        self._cli_overrides: tuple[tuple[str, object], ...] = ()
        self._harness_overrides: dict[str, object] = {}
        self._strict_config = False
        self._loader_overrides: dict[str, object] = {}
        self._codex_home: Path | None = None
        self._fallback_cwd: Path | None = None

    def cli_overrides(self, value: Sequence[tuple[str, object]]) -> "DebugSandboxDefaultConfigBuilder":
        self._cli_overrides = tuple((str(key), val) for key, val in value)
        return self

    def harness_overrides(self, value: Mapping[str, object]) -> "DebugSandboxDefaultConfigBuilder":
        self._harness_overrides = dict(value)
        return self

    def strict_config(self, value: bool) -> "DebugSandboxDefaultConfigBuilder":
        self._strict_config = bool(value)
        return self

    def loader_overrides(self, value: Mapping[str, object]) -> "DebugSandboxDefaultConfigBuilder":
        self._loader_overrides = dict(value)
        return self

    def codex_home(self, value: str | Path) -> "DebugSandboxDefaultConfigBuilder":
        self._codex_home = Path(value)
        return self

    def fallback_cwd(self, value: str | Path | None) -> "DebugSandboxDefaultConfigBuilder":
        self._fallback_cwd = Path(value) if value is not None else None
        return self

    def build(self) -> DebugSandboxConfigBuilderResult:
        from pycodex.config import ConfigLoadOptions, load_config_layers_state

        codex_home = self._codex_home or self._fallback_cwd or Path.cwd()
        cwd_value = self._harness_overrides.get("cwd")
        cwd = Path(cwd_value) if cwd_value is not None else self._fallback_cwd
        config_load_options = ConfigLoadOptions(
            loader_overrides=_loader_overrides_from_mapping(self._loader_overrides),
            strict_config=self._strict_config,
        )
        stack = load_config_layers_state(
            codex_home,
            cwd=cwd,
            cli_overrides=self._cli_overrides,
            config_load_options=config_load_options,
        )
        effective_config = stack.effective_config()
        for key, value in self._harness_overrides.items():
            if value is not None:
                effective_config[key] = value
        return DebugSandboxConfigBuilderResult(
            config_layer_stack=stack,
            effective_config=effective_config,
            harness_overrides=dict(self._harness_overrides),
            cli_overrides=self._cli_overrides,
            loader_overrides=dict(self._loader_overrides),
            strict_config=self._strict_config,
            codex_home=self._codex_home,
            fallback_cwd=self._fallback_cwd,
        )


def load_debug_sandbox_config_with_default_builder(
    plan: DebugSandboxConfigLoadPlan,
) -> DebugSandboxConfigLoadResult:
    """Execute the debug sandbox config-load plan with the Python config loader."""

    return run_debug_sandbox_config_load_plan(
        plan,
        lambda current_plan, cli_overrides, sandbox_mode: build_debug_sandbox_config_with_loader_overrides_from_plan(
            current_plan,
            cli_overrides,
            sandbox_mode,
            DebugSandboxDefaultConfigBuilder,
        ),
    )


def build_debug_sandbox_platform_implementation_decisions() -> tuple[
    DebugSandboxPlatformImplementationDecision,
    ...
]:
    """Return ownership boundaries for platform-specific debug sandbox work."""

    return (
        DebugSandboxPlatformImplementationDecision(
            concern="seatbelt_policy_generation",
            owner="codex-sandboxing/seatbelt",
            status="delegated",
            debug_sandbox_role="pass policy argv shape to sandbox-exec",
        ),
        DebugSandboxPlatformImplementationDecision(
            concern="landlock_permission_profile_serialization",
            owner="codex-protocol/codex-sandboxing",
            status="delegated",
            debug_sandbox_role="pass serialized profile argv shape to codex-linux-sandbox",
        ),
        DebugSandboxPlatformImplementationDecision(
            concern="windows_session_objects_and_forwarder_threads",
            owner="codex-cli platform backend",
            status="adapter_boundary",
            debug_sandbox_role="mirror session spawn/control/stdio bridge contracts",
        ),
        DebugSandboxPlatformImplementationDecision(
            concern="config_builder_implementation",
            owner="pycodex config package",
            status="adapter_boundary",
            debug_sandbox_role="call ConfigBuilder-shaped loader in Rust order",
        ),
    )


def build_debug_sandbox_network_plan(
    *,
    network_spec_present: bool,
    permission_profile: object | None = None,
    managed_network_requirements_enabled: bool = False,
    proxy_env: Mapping[str, str] | None = None,
) -> DebugSandboxNetworkPlan:
    """Build the pure network-proxy decision plan for debug sandbox execution."""

    return DebugSandboxNetworkPlan(
        should_start_proxy=network_spec_present,
        permission_profile=permission_profile if network_spec_present else None,
        managed_network_requirements_enabled=managed_network_requirements_enabled
        if network_spec_present
        else False,
        audit_metadata={},
        proxy_env=dict(proxy_env or {}) if network_spec_present else {},
    )


def format_debug_sandbox_network_proxy_error(error: object) -> str:
    """Return the Rust debug-sandbox managed network proxy startup error."""

    return f"failed to start managed network proxy: {error}"


def start_debug_sandbox_network_proxy_plan(
    plan: DebugSandboxNetworkPlan,
    *,
    starter: Callable[[DebugSandboxNetworkPlan], Mapping[str, str] | object] | None = None,
) -> DebugSandboxNetworkProxyStartResult:
    """Start the planned managed network proxy through an injectable boundary."""

    if not plan.should_start_proxy:
        return DebugSandboxNetworkProxyStartResult(
            started=False,
            proxy_env={},
            lifetime=plan.lifetime,
        )

    try:
        started = starter(plan) if starter is not None else plan.proxy_env
    except Exception as exc:
        raise RuntimeError(format_debug_sandbox_network_proxy_error(exc)) from exc

    if isinstance(started, Mapping):
        proxy_env = dict(started)
    else:
        proxy_env = dict(getattr(started, "proxy_env"))
    return DebugSandboxNetworkProxyStartResult(
        started=True,
        proxy_env=proxy_env,
        lifetime=plan.lifetime,
    )


def build_debug_sandbox_backend_args_plan(
    command: Sequence[str],
    *,
    sandbox_type: str,
    cwd: str | Path | None = None,
    permission_profile_cwd: str | Path | None = None,
    permission_profile: str | None = None,
    use_legacy_landlock: bool = False,
    managed_network_requirements_enabled: bool = False,
    extra_allow_unix_sockets: Sequence[str | Path] = (),
) -> DebugSandboxBackendArgsPlan:
    """Build inputs for the Rust platform-specific backend argv builders."""

    cwd_path = Path(cwd) if cwd is not None else None
    permission_profile_cwd_path = (
        Path(permission_profile_cwd)
        if permission_profile_cwd is not None
        else cwd_path
    )
    return DebugSandboxBackendArgsPlan(
        sandbox_type=sandbox_type,
        command=tuple(str(part) for part in command),
        cwd=cwd_path,
        permission_profile_cwd=permission_profile_cwd_path,
        permission_profile=permission_profile,
        use_legacy_landlock=use_legacy_landlock if sandbox_type == "landlock" else False,
        allow_network_for_proxy=managed_network_requirements_enabled
        if sandbox_type == "landlock"
        else False,
        extra_allow_unix_sockets=tuple(Path(path) for path in extra_allow_unix_sockets)
        if sandbox_type == "seatbelt"
        else (),
        enforce_managed_network=False,
    )


def build_debug_sandbox_backend_args_from_plan(
    plan: DebugSandboxBackendArgsPlan,
    *,
    builder: Callable[[DebugSandboxBackendArgsPlan], Sequence[str]] | None = None,
) -> DebugSandboxBackendArgsBuildResult:
    """Build backend args through an injectable platform builder boundary."""

    if builder is None:
        return DebugSandboxBackendArgsBuildResult(
            sandbox_type=plan.sandbox_type,
            args=plan.command,
            builder_invoked=False,
        )

    return DebugSandboxBackendArgsBuildResult(
        sandbox_type=plan.sandbox_type,
        args=tuple(str(part) for part in builder(plan)),
        builder_invoked=True,
    )


def build_debug_sandbox_seatbelt_backend_args_from_plan(
    plan: DebugSandboxBackendArgsPlan,
    *,
    policy: str,
    definitions: Mapping[str, str | Path] | None = None,
) -> DebugSandboxBackendArgsBuildResult:
    """Build the Seatbelt ``sandbox-exec`` argv shape used by Rust."""

    if plan.sandbox_type != "seatbelt":
        raise ValueError("seatbelt backend args require sandbox_type='seatbelt'")

    args: list[str] = ["-p", policy]
    for key, value in (definitions or {}).items():
        args.append(f"-D{key}={_debug_sandbox_path_arg(value)}")
    args.append("--")
    args.extend(plan.command)
    return DebugSandboxBackendArgsBuildResult(
        sandbox_type=plan.sandbox_type,
        args=tuple(args),
        builder_invoked=True,
        adapter="seatbelt",
    )


def build_debug_sandbox_landlock_backend_args_from_plan(
    plan: DebugSandboxBackendArgsPlan,
    *,
    permission_profile_json: str,
) -> DebugSandboxBackendArgsBuildResult:
    """Build the Landlock ``codex-linux-sandbox`` argv shape used by Rust."""

    if plan.sandbox_type != "landlock":
        raise ValueError("landlock backend args require sandbox_type='landlock'")
    if plan.cwd is None:
        raise ValueError("landlock backend args require command cwd")
    if plan.permission_profile_cwd is None:
        raise ValueError("landlock backend args require sandbox policy cwd")

    args: list[str] = [
        "--sandbox-policy-cwd",
        _debug_sandbox_path_arg(plan.permission_profile_cwd),
        "--command-cwd",
        _debug_sandbox_path_arg(plan.cwd),
        "--permission-profile",
        permission_profile_json,
    ]
    if plan.use_legacy_landlock:
        args.append("--use-legacy-landlock")
    if plan.allow_network_for_proxy:
        args.append("--allow-network-for-proxy")
    args.append("--")
    args.extend(plan.command)
    return DebugSandboxBackendArgsBuildResult(
        sandbox_type=plan.sandbox_type,
        args=tuple(args),
        builder_invoked=True,
        adapter="landlock",
    )


def build_debug_sandbox_windows_session_plan(
    command: Sequence[str],
    *,
    cwd: str | Path | None = None,
    permission_profile_cwd: str | Path | None = None,
    permission_profile: str | None = None,
    codex_home: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    use_elevated: bool = False,
    private_desktop: bool = False,
) -> DebugSandboxWindowsSessionPlan:
    """Build inputs for Rust's Windows sandbox session spawn branches."""

    command_tuple = tuple(str(part) for part in command)
    if not command_tuple:
        raise ValueError("windows sandbox command must not be empty")
    cwd_path = Path(cwd) if cwd is not None else None
    permission_profile_cwd_path = (
        Path(permission_profile_cwd)
        if permission_profile_cwd is not None
        else cwd_path
    )
    return DebugSandboxWindowsSessionPlan(
        mode="elevated" if use_elevated else "legacy",
        permission_profile=permission_profile,
        permission_profile_cwd=permission_profile_cwd_path,
        codex_home=Path(codex_home) if codex_home is not None else None,
        command=command_tuple,
        cwd=cwd_path,
        env=dict(env or {}),
        read_roots_override=None,
        read_roots_include_platform_defaults=False,
        write_roots_override=None,
        deny_read_paths_override=(),
        deny_write_paths_override=(),
        tty=False,
        stdin_open=True,
        private_desktop=private_desktop,
        output_drain_timeout_seconds=5,
    )


def build_debug_sandbox_windows_product_plan(
    command: Sequence[str],
    *,
    cli_overrides: Sequence[tuple[str, object]] = (),
    permissions_profile: str | None = None,
    cwd: str | Path | None = None,
    codex_home: str | Path | None = None,
    config_profile: str | None = None,
    include_managed_config: bool = False,
) -> DebugSandboxWindowsSessionPlan:
    """Load config and build the native Windows ``codex sandbox`` plan.

    Fixed Rust owners are ``run_command_under_sandbox`` and
    ``run_command_under_windows_session``. An ordinary subprocess must never
    stand in for this native plan.
    """

    from pycodex.config.types import ShellEnvironmentPolicyToml
    from pycodex.core.config.permissions import (
        builtin_permission_profile,
        compile_permission_profile_selection,
    )
    from pycodex.core.exec_env import create_env
    from pycodex.core.windows_sandbox import (
        resolve_windows_sandbox_private_desktop,
        resolve_windows_sandbox_mode,
        WindowsSandboxModeToml,
    )
    from pycodex.protocol import PermissionProfile, SandboxMode
    from pycodex.utils.home_dir import find_codex_home

    command_cwd = (Path.cwd() if cwd is None else Path(cwd)).resolve(strict=True)
    home = Path(codex_home) if codex_home is not None else find_codex_home()
    loader_overrides: dict[str, object] = {}
    if config_profile is not None:
        loader_overrides["user_config_profile"] = config_profile
    load_plan = build_debug_sandbox_config_load_plan(
        cli_overrides,
        permissions_profile=permissions_profile,
        cwd=command_cwd,
        codex_home=home,
        managed_requirements_mode=ManagedRequirementsMode.for_profile_invocation(
            permissions_profile,
            include_managed_config,
        ),
        loader_overrides=loader_overrides,
        # Inspect the loaded config below before applying the legacy fallback.
        config_uses_permission_profile=True,
    )
    loaded = load_debug_sandbox_config_with_default_builder(load_plan)
    effective = dict(loaded.config.effective_config)

    selected_profile = effective.get("default_permissions")
    permission_profile: PermissionProfile
    if isinstance(selected_profile, str):
        built_in = builtin_permission_profile(selected_profile)
        if built_in is not None:
            permission_profile = built_in
        else:
            filesystem, network = compile_permission_profile_selection(
                effective.get("permissions"),
                selected_profile,
                policy_cwd=command_cwd,
            )
            permission_profile = PermissionProfile.from_runtime_permissions(filesystem, network)
    else:
        sandbox_mode = effective.get("sandbox_mode")
        if sandbox_mode == SandboxMode.WORKSPACE_WRITE.value:
            permission_profile = PermissionProfile.workspace_write((command_cwd,))
        elif sandbox_mode == SandboxMode.DANGER_FULL_ACCESS.value:
            permission_profile = PermissionProfile.disabled()
        else:
            # Rust reloads a legacy config as read-only when neither an active
            # permission profile nor an explicit sandbox mode is present.
            permission_profile = PermissionProfile.read_only()

    policy_value = effective.get("shell_environment_policy")
    policy = ShellEnvironmentPolicyToml.from_mapping(
        policy_value if isinstance(policy_value, Mapping) else None
    ).to_policy()
    windows_mode = resolve_windows_sandbox_mode(effective)
    return build_debug_sandbox_windows_session_plan(
        command,
        cwd=command_cwd,
        permission_profile_cwd=command_cwd,
        permission_profile=permission_profile,
        codex_home=home,
        env=create_env(policy, None),
        use_elevated=windows_mode is WindowsSandboxModeToml.ELEVATED,
        private_desktop=resolve_windows_sandbox_private_desktop(effective),
    )


def _mapping_or_attr(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _effective_windows_permission_profile(config: object) -> str | None:
    permissions = _mapping_or_attr(config, "permissions")
    if permissions is None:
        return None
    getter = _mapping_or_attr(permissions, "effective_permission_profile")
    if callable(getter):
        return getter()
    return _mapping_or_attr(permissions, "effective_permission_profile") or _mapping_or_attr(
        permissions,
        "permission_profile",
    )


def _windows_sandbox_level(config: object) -> str | None:
    permissions = _mapping_or_attr(config, "permissions")
    level = _mapping_or_attr(config, "windows_sandbox_level")
    if level is None and permissions is not None:
        level = _mapping_or_attr(permissions, "windows_sandbox_level")
    if level is None:
        return None
    value = getattr(level, "value", level)
    return str(value).lower()


def build_debug_sandbox_windows_session_plan_from_config(
    config: object,
    command: Sequence[str],
    *,
    cwd: str | Path,
    permission_profile_cwd: str | Path,
    env: Mapping[str, str] | None = None,
) -> DebugSandboxWindowsSessionPlan:
    """Build the Windows session spawn plan from a Config-shaped object."""

    permissions = _mapping_or_attr(config, "permissions")
    private_desktop = (
        bool(_mapping_or_attr(permissions, "windows_sandbox_private_desktop", False))
        if permissions is not None
        else False
    )
    return build_debug_sandbox_windows_session_plan(
        command,
        cwd=cwd,
        permission_profile_cwd=permission_profile_cwd,
        permission_profile=_effective_windows_permission_profile(config),
        codex_home=_mapping_or_attr(config, "codex_home"),
        env=env,
        use_elevated=_windows_sandbox_level(config) == "elevated",
        private_desktop=private_desktop,
    )


def run_debug_sandbox_windows_session_plan(
    plan: DebugSandboxWindowsSessionPlan,
    *,
    spawner: Callable[[DebugSandboxWindowsSessionPlan], object] | None = None,
) -> DebugSandboxWindowsSessionRunResult:
    """Run the planned Windows sandbox session through the native backend."""

    try:
        spawned = spawner(plan) if spawner is not None else _spawn_debug_windows_session_native(plan)
    except Exception as exc:
        return DebugSandboxWindowsSessionRunResult(
            mode=plan.mode,
            exit_code=1,
            output_drain_timeout_seconds=plan.output_drain_timeout_seconds,
            error_message=f"windows sandbox failed: {exc}",
        )

    exit_code = getattr(spawned, "exit_code", spawned)
    stdout = getattr(spawned, "stdout", b"")
    stderr = getattr(spawned, "stderr", b"")
    return DebugSandboxWindowsSessionRunResult(
        mode=plan.mode,
        exit_code=int(exit_code),
        output_drain_timeout_seconds=plan.output_drain_timeout_seconds,
        error_message=None,
        stdout=stdout if isinstance(stdout, bytes) else str(stdout).encode("utf-8", errors="replace"),
        stderr=stderr if isinstance(stderr, bytes) else str(stderr).encode("utf-8", errors="replace"),
    )


def _spawn_debug_windows_session_native(plan: DebugSandboxWindowsSessionPlan) -> object:
    from pycodex.protocol import PermissionProfile
    from pycodex.windows_sandbox import run_windows_sandbox_capture_with_filesystem_overrides

    if not isinstance(plan.permission_profile, PermissionProfile):
        raise TypeError("native Windows sandbox debug execution requires a PermissionProfile")
    if plan.permission_profile_cwd is None or plan.cwd is None or plan.codex_home is None:
        raise ValueError("native Windows sandbox debug execution requires profile cwd, cwd, and codex_home")
    env = os.environ.copy()
    env.update(plan.env)
    if plan.mode == "elevated":
        from pycodex.windows_sandbox.elevated import run_elevated_capture

        return run_elevated_capture(
            plan.permission_profile,
            plan.permission_profile_cwd,
            plan.codex_home,
            plan.command,
            plan.cwd,
            env,
            None,
            use_private_desktop=plan.private_desktop,
            proxy_enforced=False,
            additional_deny_read_paths=plan.deny_read_paths_override,
            additional_deny_write_paths=plan.deny_write_paths_override,
        )
    return run_windows_sandbox_capture_with_filesystem_overrides(
        plan.permission_profile,
        plan.permission_profile_cwd,
        plan.codex_home,
        plan.command,
        plan.cwd,
        env,
        None,
        plan.deny_read_paths_override,
        plan.deny_write_paths_override,
        plan.private_desktop,
    )


def _spawn_debug_windows_session_popen_native(
    plan: DebugSandboxWindowsSessionPlan,
) -> object:
    """Spawn the product CLI session with live stdio and Job Object ownership."""

    from pycodex.protocol import PermissionProfile
    from pycodex.windows_sandbox import spawn_windows_sandbox_popen

    if not isinstance(plan.permission_profile, PermissionProfile):
        raise TypeError("native Windows sandbox debug execution requires a PermissionProfile")
    if plan.permission_profile_cwd is None or plan.cwd is None or plan.codex_home is None:
        raise ValueError("native Windows sandbox debug execution requires profile cwd, cwd, and codex_home")
    env = os.environ.copy()
    env.update(plan.env)
    common = dict(
        stdin_open=plan.stdin_open,
        tty=plan.tty,
        merge_stderr=False,
        use_private_desktop=plan.private_desktop,
        additional_deny_read_paths=plan.deny_read_paths_override,
        additional_deny_write_paths=plan.deny_write_paths_override,
    )
    if plan.mode == "elevated":
        from pycodex.windows_sandbox.elevated import spawn_elevated_popen

        return spawn_elevated_popen(
            plan.permission_profile,
            plan.permission_profile_cwd,
            plan.codex_home,
            plan.command,
            plan.cwd,
            env,
            proxy_enforced=False,
            **common,
        )
    return spawn_windows_sandbox_popen(
        plan.permission_profile,
        plan.permission_profile_cwd,
        plan.codex_home,
        plan.command,
        plan.cwd,
        env,
        **common,
    )


def _binary_stream(stream: object) -> object:
    return getattr(stream, "buffer", stream)


def _write_forwarded_bytes(stream: object, data: bytes) -> None:
    destination = _binary_stream(stream)
    try:
        destination.write(data)
    except TypeError:
        destination.write(data.decode("utf-8", errors="replace"))
    flush = getattr(destination, "flush", None)
    if callable(flush):
        flush()


def _forward_windows_output(source: object | None, destination: object) -> None:
    if source is None:
        return
    try:
        while True:
            chunk = source.read(64 * 1024)
            if not chunk:
                return
            _write_forwarded_bytes(destination, bytes(chunk))
    except (BrokenPipeError, OSError, ValueError):
        return


def _forward_windows_input(source: object, process_stdin: object) -> None:
    input_stream = _binary_stream(source)
    try:
        while True:
            chunk = input_stream.read(WINDOWS_STDIN_FORWARD_CHUNK_SIZE)
            if not chunk:
                return
            payload = chunk.encode("utf-8") if isinstance(chunk, str) else bytes(chunk)
            process_stdin.write(payload)
            process_stdin.flush()
    except (BrokenPipeError, OSError, ValueError):
        return
    finally:
        try:
            process_stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass


def run_debug_sandbox_windows_product_session(
    plan: DebugSandboxWindowsSessionPlan,
    *,
    stdin: object,
    stdout: object,
    stderr: object,
    spawner: Callable[[DebugSandboxWindowsSessionPlan], object] | None = None,
) -> DebugSandboxWindowsSessionRunResult:
    """Run the real Windows CLI session with Rust-like inherited stdio.

    Rust owner: ``codex-cli::debug_sandbox::run_command_under_windows_session``.
    Input and output forwarders are deliberately daemon threads: terminal
    stdin may remain blocked after the child exits, while output is drained
    for the fixed five-second window before process resources are released.
    """

    try:
        process = (
            spawner(plan)
            if spawner is not None
            else _spawn_debug_windows_session_popen_native(plan)
        )
    except Exception as exc:
        return DebugSandboxWindowsSessionRunResult(
            mode=plan.mode,
            exit_code=1,
            output_drain_timeout_seconds=plan.output_drain_timeout_seconds,
            error_message=f"windows sandbox failed: {exc}",
        )

    output_threads = [
        threading.Thread(
            target=_forward_windows_output,
            args=(getattr(process, "stdout", None), stdout),
            name="pycodex-sandbox-stdout",
            daemon=True,
        ),
        threading.Thread(
            target=_forward_windows_output,
            args=(getattr(process, "stderr", None), stderr),
            name="pycodex-sandbox-stderr",
            daemon=True,
        ),
    ]
    for thread in output_threads:
        thread.start()

    process_stdin = getattr(process, "stdin", None)
    if process_stdin is not None:
        threading.Thread(
            target=_forward_windows_input,
            args=(stdin, process_stdin),
            name="pycodex-sandbox-stdin",
            daemon=True,
        ).start()

    try:
        try:
            exit_code = int(process.wait())
        except KeyboardInterrupt:
            process.terminate()
            exit_code = int(process.wait())
        deadline = time.monotonic() + plan.output_drain_timeout_seconds
        for thread in output_threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        return DebugSandboxWindowsSessionRunResult(
            mode=plan.mode,
            exit_code=exit_code,
            output_drain_timeout_seconds=plan.output_drain_timeout_seconds,
            error_message=None,
        )
    except Exception as exc:
        try:
            process.terminate()
        except Exception:
            pass
        return DebugSandboxWindowsSessionRunResult(
            mode=plan.mode,
            exit_code=1,
            output_drain_timeout_seconds=plan.output_drain_timeout_seconds,
            error_message=f"windows sandbox failed: {exc}",
        )
    finally:
        close = getattr(process, "close", None)
        if callable(close):
            close()


def run_debug_sandbox_windows_session_control_flow(
    plan: DebugSandboxWindowsSessionPlan,
    *,
    exit_code: int | None,
    ctrl_c: bool = False,
    stdin_eof: bool = False,
) -> DebugSandboxWindowsSessionControlResult:
    """Mirror Rust's post-spawn Windows session control decisions.

    The Rust implementation waits for either the sandbox session exit or
    Ctrl-C, closes stdin after forwarded EOF, aborts the stdin close task after
    exit, and then waits for stdout/stderr forwarders with a fixed timeout.
    """

    return DebugSandboxWindowsSessionControlResult(
        exit_code=exit_code if exit_code is not None else -1,
        requested_terminate=ctrl_c,
        closed_stdin_after_eof=stdin_eof,
        aborted_stdin_close_task=True,
        waited_for_output_drain=True,
        output_drain_timeout_seconds=plan.output_drain_timeout_seconds,
    )


def run_debug_sandbox_windows_session_io_bridge(
    plan: DebugSandboxWindowsSessionPlan,
    *,
    stdin: bytes = b"",
    stdout_chunks: Sequence[bytes] = (),
    stderr_chunks: Sequence[bytes] = (),
    exit_code: int | None,
    ctrl_c: bool = False,
    write_stdin: Callable[[bytes], None] | None = None,
    close_stdin: Callable[[], None] | None = None,
    request_terminate: Callable[[], None] | None = None,
) -> DebugSandboxWindowsSessionIoBridgeResult:
    """Bridge finite stdio data through Rust-equivalent Windows session hooks."""

    stdin_chunks = tuple(windows_stdin_forward_chunks(stdin))
    actions: list[str] = []
    for chunk in stdin_chunks:
        if write_stdin is not None:
            write_stdin(chunk)
        actions.append("write_stdin")

    if close_stdin is not None:
        close_stdin()
    actions.append("close_stdin")

    if ctrl_c:
        if request_terminate is not None:
            request_terminate()
        actions.append("request_terminate")

    control = run_debug_sandbox_windows_session_control_flow(
        plan,
        exit_code=exit_code,
        ctrl_c=ctrl_c,
        stdin_eof=True,
    )
    return DebugSandboxWindowsSessionIoBridgeResult(
        stdin_chunks=stdin_chunks,
        stdout=windows_output_forward_bytes(list(stdout_chunks)),
        stderr=windows_output_forward_bytes(list(stderr_chunks)),
        control=control,
        actions=tuple(actions),
    )


def run_debug_sandbox_windows_session_with_stdio_bridge(
    plan: DebugSandboxWindowsSessionPlan,
    *,
    spawner: Callable[[DebugSandboxWindowsSessionPlan], object],
    write_stdin: Callable[[bytes], None] | None = None,
    close_stdin: Callable[[], None] | None = None,
    request_terminate: Callable[[], None] | None = None,
) -> DebugSandboxWindowsSpawnBridgeResult:
    """Spawn a Windows session and bridge finite stdio through injected hooks."""

    try:
        spawned = spawner(plan)
    except Exception as exc:
        return DebugSandboxWindowsSpawnBridgeResult(
            run=DebugSandboxWindowsSessionRunResult(
                mode=plan.mode,
                exit_code=1,
                output_drain_timeout_seconds=plan.output_drain_timeout_seconds,
                error_message=f"windows sandbox failed: {exc}",
            ),
            io=None,
        )

    exit_code = getattr(spawned, "exit_code", None)
    io = run_debug_sandbox_windows_session_io_bridge(
        plan,
        stdin=getattr(spawned, "stdin", b""),
        stdout_chunks=tuple(getattr(spawned, "stdout_chunks", ())),
        stderr_chunks=tuple(getattr(spawned, "stderr_chunks", ())),
        exit_code=exit_code,
        ctrl_c=bool(getattr(spawned, "ctrl_c", False)),
        write_stdin=write_stdin,
        close_stdin=close_stdin,
        request_terminate=request_terminate,
    )
    return DebugSandboxWindowsSpawnBridgeResult(
        run=DebugSandboxWindowsSessionRunResult(
            mode=plan.mode,
            exit_code=io.control.exit_code,
            output_drain_timeout_seconds=plan.output_drain_timeout_seconds,
            error_message=None,
        ),
        io=io,
    )


def build_debug_sandbox_deferred_native_boundaries() -> tuple[
    DebugSandboxDeferredNativeBoundary,
    ...
]:
    """Return native debug-sandbox work kept behind injectable boundaries."""

    return (
        DebugSandboxDeferredNativeBoundary(
            concern="platform_policy_builders",
            upstream_owner="codex-sandboxing and codex-protocol",
            python_boundary="build_debug_sandbox_seatbelt_backend_args_from_plan/build_debug_sandbox_landlock_backend_args_from_plan",
            rationale="policy serialization/generation is owned by sibling crates; debug_sandbox.rs consumes argv shapes",
        ),
    )


def build_debug_sandbox_entrypoint_plan(
    command: Sequence[str],
    *,
    sandbox_type: str,
    cwd: str | Path | None = None,
    permissions_profile: str | None = None,
    include_managed_config: bool = False,
    config_overrides: Sequence[tuple[str, object]] = (),
    codex_linux_sandbox_exe: str | Path | None = None,
    loader_overrides: Mapping[str, object] | None = None,
    log_denials: bool = False,
    allow_unix_sockets: Sequence[str | Path] = (),
) -> DebugSandboxEntrypointPlan:
    """Build the public-entrypoint forwarding plan for a debug sandbox run."""

    command_tuple = tuple(str(part) for part in command)
    if not command_tuple:
        raise ValueError("debug sandbox command must not be empty")
    return DebugSandboxEntrypointPlan(
        sandbox_type=sandbox_type,
        command=command_tuple,
        cwd=Path(cwd) if cwd is not None else None,
        permissions_profile=permissions_profile,
        managed_requirements_mode=ManagedRequirementsMode.for_profile_invocation(
            permissions_profile,
            include_managed_config,
        ),
        config_overrides=tuple(config_overrides),
        codex_linux_sandbox_exe=Path(codex_linux_sandbox_exe)
        if codex_linux_sandbox_exe is not None
        else None,
        loader_overrides=dict(loader_overrides or {}),
        log_denials=log_denials if sandbox_type == "seatbelt" else False,
        allow_unix_sockets=tuple(Path(path) for path in allow_unix_sockets)
        if sandbox_type == "seatbelt"
        else (),
    )


def sandbox_unavailable_error(sandbox_type: str, platform: str | None = None) -> str | None:
    """Return the Rust debug-sandbox platform availability error, if any."""

    platform_name = platform or sys.platform
    if sandbox_type == "seatbelt" and platform_name != "darwin":
        return "Seatbelt sandbox is only available on macOS"
    if sandbox_type == "windows" and platform_name != "win32":
        return "Windows sandbox is only available on Windows"
    return None


def debug_sandbox_pid_is_alive(pid: int) -> bool:
    """Mirror Rust pid_is_alive: invalid pids are dead; EPERM still means alive."""

    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def debug_sandbox_list_child_pids(
    parent: int,
    *,
    platform: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> list[int]:
    """Best-effort Python boundary for Rust's macOS proc_listchildpids wrapper."""

    if parent <= 0:
        return []
    platform_name = platform or sys.platform
    if platform_name != "darwin":
        return []

    run = runner if runner is not None else subprocess.run
    try:
        result = run(
            ["pgrep", "-P", str(parent)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return []

    if getattr(result, "returncode", 1) not in (0, 1):
        return []

    pids: list[int] = []
    for line in str(getattr(result, "stdout", "")).splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid > 0:
            pids.append(pid)
    return pids


def collect_debug_sandbox_descendant_pids(
    root_pid: int,
    *,
    list_children: Callable[[int], Sequence[int]] | None = None,
    is_alive: Callable[[int], bool] | None = None,
) -> set[int]:
    """Collect root and recursively discovered child pids for the debug sandbox."""

    if root_pid <= 0:
        return set()

    child_lister = list_children if list_children is not None else debug_sandbox_list_child_pids
    alive = is_alive if is_alive is not None else debug_sandbox_pid_is_alive

    seen: set[int] = {root_pid}
    stack = [root_pid]
    while stack:
        parent = stack.pop()
        if parent != root_pid and not alive(parent):
            continue
        for child_pid in child_lister(parent):
            if child_pid <= 0 or child_pid in seen:
                continue
            seen.add(child_pid)
            stack.append(child_pid)
    return seen


def debug_sandbox_child_env(
    env: dict[str, str],
    network_sandbox_enabled: bool,
) -> dict[str, str]:
    """Return child env adjusted for debug sandbox network policy."""

    child_env = dict(env)
    if not network_sandbox_enabled:
        child_env[CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR] = "1"
    return child_env


def debug_sandbox_seatbelt_env(env: dict[str, str]) -> dict[str, str]:
    """Return child env marked for the debug Seatbelt sandbox."""

    child_env = dict(env)
    child_env[CODEX_SANDBOX_ENV_VAR] = "seatbelt"
    return child_env


def debug_sandbox_child_arg0(
    program: str | Path,
    arg0: str | None = None,
    *,
    is_unix: bool = True,
) -> str | None:
    """Return the Unix argv[0] used for a debug sandbox child."""

    if not is_unix:
        return None
    return arg0 if arg0 is not None else _debug_sandbox_path_arg(program)


def build_debug_sandbox_child_spawn_plan(
    program: str | Path,
    args: Sequence[str],
    *,
    cwd: str | Path,
    env: Mapping[str, str] | None = None,
    env_updates: Mapping[str, str] | None = None,
    arg0: str | None = None,
    network_sandbox_enabled: bool = True,
    is_unix: bool = True,
) -> DebugSandboxChildSpawnPlan:
    """Build the pure child-spawn plan from Rust's spawn helper."""

    final_env = dict(env or {})
    final_env.update(env_updates or {})
    if not network_sandbox_enabled:
        final_env[CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR] = "1"
    return DebugSandboxChildSpawnPlan(
        program=Path(program),
        args=tuple(str(part) for part in args),
        arg0=debug_sandbox_child_arg0(program, arg0=arg0, is_unix=is_unix),
        cwd=Path(cwd),
        env=final_env,
        env_clear=True,
        stdin="inherit",
        stdout="inherit",
        stderr="inherit",
        kill_on_drop=True,
    )


def build_debug_sandbox_network_env_application_plan(
    *,
    sandbox_type: str,
    base_env: Mapping[str, str] | None = None,
    proxy_env: Mapping[str, str] | None = None,
    network_present: bool = False,
    network_sandbox_enabled: bool = True,
) -> DebugSandboxNetworkEnvApplicationPlan:
    """Build the env mutation plan for sandbox child network setup."""

    env_after_apply = dict(base_env or {})
    applies_seatbelt_marker = sandbox_type == "seatbelt"
    if applies_seatbelt_marker:
        env_after_apply[CODEX_SANDBOX_ENV_VAR] = "seatbelt"
    if network_present:
        env_after_apply.update(proxy_env or {})
    final_env = debug_sandbox_child_env(
        env_after_apply,
        network_sandbox_enabled=network_sandbox_enabled,
    )
    return DebugSandboxNetworkEnvApplicationPlan(
        sandbox_type=sandbox_type,
        network_present=network_present,
        network_sandbox_enabled=network_sandbox_enabled,
        env_after_apply=env_after_apply,
        final_env=final_env,
        applies_seatbelt_marker=applies_seatbelt_marker,
        disabled_network_marker_value=final_env.get(CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR),
    )


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


def parse_debug_sandbox_seatbelt_denial_message(msg: str) -> DebugSandboxSeatbeltDenial | None:
    """Parse Rust seatbelt.rs DenialLogger sandbox eventMessage text."""

    match = _SEATBELT_DENIAL_RE.match(msg)
    if match is None:
        return None
    name, pid_str, capability = match.groups()
    try:
        pid = int(pid_str.strip())
    except ValueError:
        return None
    return DebugSandboxSeatbeltDenial(pid=pid, name=name, capability=capability)


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
        parsed = parse_debug_sandbox_seatbelt_denial_message(msg)
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


def build_debug_sandbox_run_flow_plan(
    *,
    sandbox_type: str,
    platform: str | None = None,
) -> DebugSandboxRunFlowPlan:
    """Build the shared debug sandbox orchestration phase order."""

    platform_name = platform or sys.platform
    common_prefix = (
        "parse_config_overrides",
        "load_debug_sandbox_config",
        "clone_config_cwd",
        "set_permission_profile_cwd_from_cwd",
        "create_shell_env",
    )
    if sandbox_type == "windows":
        if platform_name == "win32":
            phases = common_prefix + ("run_windows_session_and_exit",)
        else:
            phases = common_prefix + ("windows_unavailable_error",)
        return DebugSandboxRunFlowPlan(
            sandbox_type=sandbox_type,
            platform=platform_name,
            phases=phases,
            strict_config=False,
            cwd_source="config.cwd",
            permission_profile_cwd_source="cwd",
            windows_special_case_before_denial_logger=True,
            denial_logger_before_network_proxy=False,
            child_wait_before_exit_status=False,
            handles_exit_status=False,
        )

    phases = common_prefix + (
        "maybe_create_denial_logger",
        "compute_managed_network_requirements",
        "maybe_start_network_proxy",
        "build_backend_args",
        "spawn_debug_sandbox_child",
        "maybe_attach_denial_logger",
        "wait_child",
        "maybe_finish_denial_logger",
        "handle_exit_status",
    )
    return DebugSandboxRunFlowPlan(
        sandbox_type=sandbox_type,
        platform=platform_name,
        phases=phases,
        strict_config=False,
        cwd_source="config.cwd",
        permission_profile_cwd_source="cwd",
        windows_special_case_before_denial_logger=False,
        denial_logger_before_network_proxy=True,
        child_wait_before_exit_status=True,
        handles_exit_status=True,
    )


def execute_debug_sandbox_run_flow_plan(
    plan: DebugSandboxRunFlowPlan,
    handlers: Mapping[str, Callable[[], object]],
    *,
    require_handlers: bool = False,
) -> DebugSandboxRunFlowExecutionResult:
    """Execute the planned Rust phase order through injected handlers."""

    terminal_phases = {
        "handle_exit_status",
        "run_windows_session_and_exit",
        "windows_unavailable_error",
    }
    executed: list[str] = []
    missing: list[str] = []
    outputs: list[tuple[str, object]] = []
    terminal_phase: str | None = None

    for phase in plan.phases:
        handler = handlers.get(phase)
        if handler is None:
            if require_handlers:
                raise KeyError(f"missing debug sandbox phase handler: {phase}")
            missing.append(phase)
            continue
        outputs.append((phase, handler()))
        executed.append(phase)
        if phase in terminal_phases:
            terminal_phase = phase
            break

    return DebugSandboxRunFlowExecutionResult(
        sandbox_type=plan.sandbox_type,
        executed_phases=tuple(executed),
        missing_handlers=tuple(missing),
        terminal_phase=terminal_phase,
        outputs=tuple(outputs),
    )


def build_debug_sandbox_run_flow_handler_wiring(
    plan: DebugSandboxRunFlowPlan,
    handlers: Mapping[str, Callable[[], object]],
) -> DebugSandboxRunFlowHandlerWiring:
    """Select concrete phase handlers for the planned Rust run-flow order."""

    terminal_phase_set = {
        "handle_exit_status",
        "run_windows_session_and_exit",
        "windows_unavailable_error",
    }
    wired_handlers: dict[str, Callable[[], object]] = {}
    missing: list[str] = []
    for phase in plan.phases:
        handler = handlers.get(phase)
        if handler is None:
            missing.append(phase)
        else:
            wired_handlers[phase] = handler

    terminal_phases = tuple(phase for phase in plan.phases if phase in terminal_phase_set)
    return DebugSandboxRunFlowHandlerWiring(
        sandbox_type=plan.sandbox_type,
        handlers=wired_handlers,
        wired_phases=tuple(wired_handlers),
        missing_phases=tuple(missing),
        terminal_phases=terminal_phases,
    )


def build_debug_sandbox_default_run_flow_handlers(
    plan: DebugSandboxRunFlowPlan,
    *,
    config_plan: DebugSandboxConfigLoadPlan | None = None,
    config_result: DebugSandboxConfigLoadResult | None = None,
    execution_plan: DebugSandboxExecutionPlan | None = None,
    network_plan: DebugSandboxNetworkPlan | None = None,
    network_proxy_result: DebugSandboxNetworkProxyStartResult | None = None,
    backend_args_result: DebugSandboxBackendArgsBuildResult | None = None,
    child_exit: DebugSandboxChildRunExitStatusPlan | None = None,
    denial_logger: DebugSandboxDenialLoggerPlan | None = None,
    denial_log: DebugSandboxDenialLogResult | None = None,
    exit_status: DebugSandboxExitStatusPlan | None = None,
    windows_result: DebugSandboxWindowsSessionRunResult | None = None,
) -> DebugSandboxRunFlowHandlerWiring:
    """Build default phase handlers from existing debug sandbox helper results."""

    handlers: dict[str, Callable[[], object]] = {}
    if config_plan is not None:
        handlers["parse_config_overrides"] = lambda: config_plan.cli_overrides
        handlers["load_debug_sandbox_config"] = lambda: (
            config_result if config_result is not None else config_plan
        )
    if execution_plan is not None:
        handlers["clone_config_cwd"] = lambda: execution_plan.cwd
        handlers["set_permission_profile_cwd_from_cwd"] = (
            lambda: execution_plan.permission_profile_cwd
        )
        handlers["create_shell_env"] = lambda: execution_plan.env
    if denial_logger is not None:
        handlers["maybe_create_denial_logger"] = lambda: denial_logger
        handlers["maybe_attach_denial_logger"] = lambda: denial_logger.enabled
    if network_plan is not None:
        handlers["compute_managed_network_requirements"] = (
            lambda: network_plan.managed_network_requirements_enabled
        )
    if network_proxy_result is not None:
        handlers["maybe_start_network_proxy"] = lambda: network_proxy_result
    if backend_args_result is not None:
        handlers["build_backend_args"] = lambda: backend_args_result
    if child_exit is not None:
        handlers["spawn_debug_sandbox_child"] = lambda: child_exit.child
        handlers["wait_child"] = lambda: child_exit.exit_status
    if denial_log is not None:
        handlers["maybe_finish_denial_logger"] = lambda: denial_log
    if exit_status is not None:
        handlers["handle_exit_status"] = lambda: exit_status.process_exit_code
    if windows_result is not None:
        handlers["run_windows_session_and_exit"] = lambda: windows_result.exit_code
    return build_debug_sandbox_run_flow_handler_wiring(plan, handlers)


def build_debug_sandbox_execution_plan(
    command: Sequence[str],
    *,
    cwd: str | Path | None = None,
    permissions_profile: str | None = None,
    include_managed_config: bool = False,
    sandbox_type: str = "landlock",
    codex_linux_sandbox_exe: str | Path | None = None,
    backend_args: Sequence[str] | None = None,
    network_sandbox_enabled: bool = True,
    network_env: Mapping[str, str] | None = None,
    base_env: Mapping[str, str] | None = None,
    platform: str | None = None,
) -> DebugSandboxExecutionPlan:
    """Build the command/cwd/env plan used by the Python debug sandbox shim."""

    command_tuple = tuple(str(part) for part in command)
    if not command_tuple:
        raise ValueError("debug sandbox command must not be empty")
    unavailable = sandbox_unavailable_error(sandbox_type, platform=platform)
    if unavailable is not None:
        raise RuntimeError(unavailable)

    env = dict(base_env or {})
    env["PYCODEX_SANDBOX_MODE"] = "workspace-write"
    if sandbox_type == "seatbelt":
        env = debug_sandbox_seatbelt_env(env)
    if network_env is not None:
        env.update(network_env)
    env = debug_sandbox_child_env(env, network_sandbox_enabled=network_sandbox_enabled)
    cwd_path = Path(cwd) if cwd is not None else None
    backend_program: Path | None
    child_arg0: str | None
    if sandbox_type == "seatbelt":
        backend_program = Path("/usr/bin/sandbox-exec")
        child_arg0 = None
    elif sandbox_type == "landlock":
        backend_program = Path(codex_linux_sandbox_exe) if codex_linux_sandbox_exe is not None else None
        child_arg0 = "codex-linux-sandbox"
    else:
        backend_program = None
        child_arg0 = None

    return DebugSandboxExecutionPlan(
        command=command_tuple,
        cwd=cwd_path,
        permission_profile_cwd=cwd_path,
        backend_program=backend_program,
        backend_args=tuple(str(part) for part in backend_args) if backend_args is not None else command_tuple,
        child_arg0=child_arg0,
        env=env,
        sandbox_type=sandbox_type,
        permissions_profile=permissions_profile,
        managed_requirements_mode=ManagedRequirementsMode.for_profile_invocation(
            permissions_profile,
            include_managed_config,
        ),
        include_managed_config=include_managed_config,
    )


def debug_sandbox_subprocess_argv(plan: DebugSandboxExecutionPlan) -> tuple[str, ...]:
    """Return the subprocess argv for a debug sandbox execution plan."""

    if plan.backend_program is None:
        return plan.command
    return (_debug_sandbox_path_arg(plan.backend_program), *plan.backend_args)


def debug_sandbox_child_spawn_plan_from_execution_plan(
    plan: DebugSandboxExecutionPlan,
    *,
    is_unix: bool = True,
) -> DebugSandboxChildSpawnPlan:
    """Convert the execution plan into Rust-style child spawn inputs."""

    argv = debug_sandbox_subprocess_argv(plan)
    if not argv:
        raise ValueError("debug sandbox subprocess argv must not be empty")
    program = plan.backend_program if plan.backend_program is not None else Path(argv[0])
    args = plan.backend_args if plan.backend_program is not None else argv[1:]
    cwd = plan.cwd if plan.cwd is not None else Path.cwd()
    return build_debug_sandbox_child_spawn_plan(
        program,
        args,
        cwd=cwd,
        env=plan.env,
        arg0=plan.child_arg0,
        network_sandbox_enabled=(
            CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR not in plan.env
        ),
        is_unix=is_unix,
    )


def run_debug_sandbox_child_spawn_plan(
    plan: DebugSandboxChildSpawnPlan,
    *,
    runner: Callable[..., object] | None = None,
) -> DebugSandboxChildRunResult:
    """Run a child spawn plan with Rust-style inherited stdio/env inputs."""

    run = runner or subprocess.run
    program = _debug_sandbox_path_arg(plan.program)
    executable = program if plan.arg0 is not None else None
    argv = (
        (plan.arg0, *plan.args)
        if plan.arg0 is not None
        else (program, *plan.args)
    )
    completed = run(
        list(argv),
        executable=executable,
        cwd=_debug_sandbox_path_arg(plan.cwd),
        env=dict(plan.env),
        stdin=None,
        stdout=None,
        stderr=None,
        check=False,
    )
    returncode = getattr(completed, "returncode", completed)
    return DebugSandboxChildRunResult(
        returncode=int(returncode),
        argv=argv,
        executable=executable,
        cwd=plan.cwd,
        env=dict(plan.env),
    )


def run_debug_sandbox_child_spawn_plan_with_exit_status(
    plan: DebugSandboxChildSpawnPlan,
    *,
    runner: Callable[..., object] | None = None,
    platform: str | None = None,
) -> DebugSandboxChildRunExitStatusPlan:
    """Run a child spawn plan and prepare the post-wait exit-status plan."""

    child = run_debug_sandbox_child_spawn_plan(plan, runner=runner)
    return DebugSandboxChildRunExitStatusPlan(
        child=child,
        exit_status=build_debug_sandbox_exit_status_plan(
            exit_code=child.returncode,
            platform=platform,
        ),
    )


def run_debug_sandbox_execution_plan_with_exit_status(
    plan: DebugSandboxExecutionPlan,
    *,
    runner: Callable[..., object] | None = None,
    platform: str | None = None,
    is_unix: bool = True,
) -> DebugSandboxChildRunExitStatusPlan:
    """Run an execution plan through the Rust-style child spawn path."""

    spawn_plan = debug_sandbox_child_spawn_plan_from_execution_plan(
        plan,
        is_unix=is_unix,
    )
    return run_debug_sandbox_child_spawn_plan_with_exit_status(
        spawn_plan,
        runner=runner,
        platform=platform,
    )


def run_debug_sandbox_backend_args_plan_with_exit_status(
    plan: DebugSandboxBackendArgsPlan,
    *,
    backend_program: str | Path | None = None,
    runner: Callable[..., object] | None = None,
    builder: Callable[[DebugSandboxBackendArgsPlan], Sequence[str]] | None = None,
    base_env: Mapping[str, str] | None = None,
    network_env: Mapping[str, str] | None = None,
    network_sandbox_enabled: bool = True,
    platform: str | None = None,
    is_unix: bool = True,
) -> DebugSandboxChildRunExitStatusPlan:
    """Build backend args from a plan and run them through the child path."""

    built_args = build_debug_sandbox_backend_args_from_plan(plan, builder=builder)
    execution_plan = build_debug_sandbox_execution_plan(
        plan.command,
        cwd=plan.cwd,
        permissions_profile=plan.permission_profile,
        sandbox_type=plan.sandbox_type,
        codex_linux_sandbox_exe=backend_program,
        backend_args=built_args.args,
        network_sandbox_enabled=network_sandbox_enabled,
        network_env=network_env,
        base_env=base_env,
        platform=platform,
    )
    return run_debug_sandbox_execution_plan_with_exit_status(
        execution_plan,
        runner=runner,
        platform=platform,
        is_unix=is_unix,
    )


def run_debug_sandbox_execution_plan_with_denial_logging(
    plan: DebugSandboxExecutionPlan,
    denial_logger: DebugSandboxDenialLoggerPlan,
    *,
    runner: Callable[..., object] | None = None,
    collector: Callable[[], Sequence[tuple[str, str]]] | None = None,
    platform: str | None = None,
    is_unix: bool = True,
) -> DebugSandboxExecutionWithDenialsResult:
    """Run the shared execution path and finish denial logging after wait."""

    child_exit = run_debug_sandbox_execution_plan_with_exit_status(
        plan,
        runner=runner,
        platform=platform,
        is_unix=is_unix,
    )
    return DebugSandboxExecutionWithDenialsResult(
        child_exit=child_exit,
        denial_log=finish_debug_sandbox_denial_logger_plan(
            denial_logger,
            collector=collector,
        ),
    )


def run_debug_sandbox_entrypoint_plan_with_exit_status(
    plan: DebugSandboxEntrypointPlan,
    *,
    runner: Callable[..., object] | None = None,
    platform: str | None = None,
    is_unix: bool = True,
    backend_args: Sequence[str] | None = None,
    network_sandbox_enabled: bool = True,
    network_env: Mapping[str, str] | None = None,
    base_env: Mapping[str, str] | None = None,
) -> DebugSandboxChildRunExitStatusPlan:
    """Run an entrypoint plan through the shared debug sandbox runner."""

    execution_plan = build_debug_sandbox_execution_plan(
        plan.command,
        cwd=plan.cwd,
        permissions_profile=plan.permissions_profile,
        include_managed_config=(
            plan.managed_requirements_mode is ManagedRequirementsMode.INCLUDE
        ),
        sandbox_type=plan.sandbox_type,
        codex_linux_sandbox_exe=plan.codex_linux_sandbox_exe,
        backend_args=backend_args,
        network_sandbox_enabled=network_sandbox_enabled,
        network_env=network_env,
        base_env=base_env,
        platform=platform,
    )
    return run_debug_sandbox_execution_plan_with_exit_status(
        execution_plan,
        runner=runner,
        platform=platform,
        is_unix=is_unix,
    )


def build_debug_sandbox_exit_status_plan(
    *,
    exit_code: int | None = None,
    signal: int | None = None,
    platform: str | None = None,
) -> DebugSandboxExitStatusPlan:
    """Build the exit-code plan used after waiting for the sandbox child."""

    platform_name = platform or sys.platform
    is_windows = platform_name == "win32"
    if exit_code is not None:
        process_exit_code = exit_code
        used_signal_fallback = False
        used_generic_fallback = False
    elif not is_windows and signal is not None:
        process_exit_code = 128 + signal
        used_signal_fallback = True
        used_generic_fallback = False
    else:
        process_exit_code = 1
        used_signal_fallback = False
        used_generic_fallback = True
    return DebugSandboxExitStatusPlan(
        platform=platform_name,
        child_exit_code=exit_code,
        child_signal=signal,
        process_exit_code=process_exit_code,
        used_signal_fallback=used_signal_fallback,
        used_generic_fallback=used_generic_fallback,
    )


def raise_debug_sandbox_exit_status(plan: DebugSandboxExitStatusPlan) -> None:
    """Raise ``SystemExit`` with the Rust-compatible sandbox exit code."""

    raise SystemExit(plan.process_exit_code)


def raise_debug_sandbox_child_run_exit_status(
    plan: DebugSandboxChildRunExitStatusPlan,
) -> None:
    """Raise ``SystemExit`` for a completed debug sandbox child run."""

    raise_debug_sandbox_exit_status(plan.exit_status)


def windows_stdin_forward_chunks(data: bytes) -> list[bytes]:
    """Return Windows sandbox stdin forwarder chunks for ``data``."""

    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    return [
        data[index : index + WINDOWS_STDIN_FORWARD_CHUNK_SIZE]
        for index in range(0, len(data), WINDOWS_STDIN_FORWARD_CHUNK_SIZE)
    ]


def windows_output_forward_bytes(chunks: list[bytes]) -> bytes:
    """Return bytes written by the Windows sandbox output forwarder."""

    output = bytearray()
    for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise TypeError("chunks must contain bytes")
        output.extend(chunk)
    return bytes(output)


__all__ = [
    "ManagedRequirementsMode",
    "DebugSandboxExecutionPlan",
    "DebugSandboxConfigLoadPlan",
    "DebugSandboxConfigLoadResult",
    "DebugSandboxConfigBuilderResult",
    "DebugSandboxDefaultConfigBuilder",
    "DebugSandboxPlatformImplementationDecision",
    "DebugSandboxNetworkPlan",
    "DebugSandboxNetworkProxyStartResult",
    "DebugSandboxBackendArgsPlan",
    "DebugSandboxBackendArgsBuildResult",
    "DebugSandboxWindowsSessionPlan",
    "DebugSandboxWindowsSessionRunResult",
    "DebugSandboxWindowsSessionControlResult",
    "DebugSandboxWindowsSessionIoBridgeResult",
    "DebugSandboxWindowsSpawnBridgeResult",
    "DebugSandboxDeferredNativeBoundary",
    "DebugSandboxEntrypointPlan",
    "DebugSandboxChildSpawnPlan",
    "DebugSandboxChildRunResult",
    "DebugSandboxChildRunExitStatusPlan",
    "DebugSandboxNetworkEnvApplicationPlan",
    "DebugSandboxDenialLoggerPlan",
    "DebugSandboxDenialLogResult",
    "DebugSandboxExecutionWithDenialsResult",
    "DebugSandboxPidTracker",
    "DebugSandboxRunFlowPlan",
    "DebugSandboxRunFlowExecutionResult",
    "DebugSandboxRunFlowHandlerWiring",
    "DebugSandboxSeatbeltDenial",
    "DebugSandboxExitStatusPlan",
    "WINDOWS_STDIN_FORWARD_CHUNK_SIZE",
    "build_debug_sandbox_entrypoint_plan",
    "build_debug_sandbox_child_spawn_plan",
    "build_debug_sandbox_config_with_loader_overrides_from_plan",
    "build_debug_sandbox_platform_implementation_decisions",
    "build_debug_sandbox_network_env_application_plan",
    "build_debug_sandbox_denial_logger_plan",
    "build_debug_sandbox_run_flow_plan",
    "build_debug_sandbox_run_flow_handler_wiring",
    "build_debug_sandbox_default_run_flow_handlers",
    "execute_debug_sandbox_run_flow_plan",
    "build_debug_sandbox_exit_status_plan",
    "build_debug_sandbox_backend_args_plan",
    "build_debug_sandbox_backend_args_from_plan",
    "build_debug_sandbox_seatbelt_backend_args_from_plan",
    "build_debug_sandbox_landlock_backend_args_from_plan",
    "build_debug_sandbox_config_load_plan",
    "build_debug_sandbox_network_plan",
    "build_debug_sandbox_windows_session_plan",
    "build_debug_sandbox_windows_product_plan",
    "build_debug_sandbox_windows_session_plan_from_config",
    "build_debug_sandbox_deferred_native_boundaries",
    "build_debug_sandbox_execution_plan",
    "cli_overrides_use_legacy_sandbox_mode",
    "collect_debug_sandbox_descendant_pids",
    "collect_debug_sandbox_seatbelt_denials",
    "config_uses_permission_profiles",
    "debug_sandbox_child_arg0",
    "debug_sandbox_child_env",
    "debug_sandbox_child_spawn_plan_from_execution_plan",
    "debug_sandbox_list_child_pids",
    "debug_sandbox_pid_is_alive",
    "debug_sandbox_subprocess_argv",
    "debug_sandbox_seatbelt_env",
    "format_debug_sandbox_denial_summary",
    "format_debug_sandbox_network_proxy_error",
    "finish_debug_sandbox_denial_logger_plan",
    "loader_overrides_with_managed_requirements_mode",
    "load_debug_sandbox_config_with_default_builder",
    "parse_debug_sandbox_seatbelt_denial_message",
    "raise_debug_sandbox_child_run_exit_status",
    "raise_debug_sandbox_exit_status",
    "run_debug_sandbox_child_spawn_plan",
    "run_debug_sandbox_child_spawn_plan_with_exit_status",
    "run_debug_sandbox_backend_args_plan_with_exit_status",
    "run_debug_sandbox_execution_plan_with_denial_logging",
    "run_debug_sandbox_execution_plan_with_exit_status",
    "run_debug_sandbox_entrypoint_plan_with_exit_status",
    "run_debug_sandbox_config_load_plan",
    "run_debug_sandbox_windows_session_plan",
    "run_debug_sandbox_windows_product_session",
    "run_debug_sandbox_windows_session_control_flow",
    "run_debug_sandbox_windows_session_io_bridge",
    "run_debug_sandbox_windows_session_with_stdio_bridge",
    "sandbox_unavailable_error",
    "should_default_legacy_config_to_read_only",
    "start_debug_sandbox_network_proxy_plan",
    "with_permissions_profile_override",
    "windows_stdin_forward_chunks",
    "windows_output_forward_bytes",
]
