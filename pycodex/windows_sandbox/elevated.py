"""Setup-backed elevated Windows sandbox capture backend.

Rust owners: ``elevated_impl``, ``identity``, and command-runner ``win`` at
fixed commit ``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping, Sequence
from dataclasses import dataclass

from pycodex.protocol import PermissionProfile

from .cap import load_or_create_cap_sids, workspace_write_cap_sid_for_root
from .env import ensure_non_interactive_pager, inherit_path_env, normalize_null_device_env
from .identity import select_identity, setup_mismatch_reason
from .process import ProcessCaptureResult
from .runner_transport import RunnerBackedPopen, spawn_runner_popen
from .resolved_permissions import ResolvedWindowsSandboxPermissions
from .setup import SandboxNetworkIdentity, build_elevation_payload, effective_write_roots_for_permissions
from .setup_orchestrator import is_elevated, run_setup_helper


@dataclass(frozen=True)
class ElevatedSandboxProfileCaptureRequest:
    permission_profile: PermissionProfile
    permission_profile_cwd: Path
    codex_home: Path
    command: tuple[str, ...]
    cwd: Path
    env_map: Mapping[str, str]
    timeout_ms: int | None = None
    use_private_desktop: bool = True
    proxy_enforced: bool = False
    read_roots_override: tuple[Path, ...] | None = None
    read_roots_include_platform_defaults: bool = False
    write_roots_override: tuple[Path, ...] | None = None
    deny_read_paths_override: tuple[Path, ...] = ()
    deny_write_paths_override: tuple[Path, ...] = ()


def _read_process_stream(process: object, name: str) -> bytes:
    stream = getattr(process, name, None)
    read = getattr(stream, "read", None)
    if not callable(read):
        return b""
    value = read()
    return value if isinstance(value, bytes) else str(value).encode("utf-8", errors="replace")


def run_elevated_capture(
    permission_profile: PermissionProfile,
    permission_profile_cwd: str | Path,
    codex_home: str | Path,
    command: Sequence[str],
    cwd: str | Path,
    env_map: Mapping[str, str],
    timeout_ms: int | None,
    *,
    use_private_desktop: bool,
    proxy_enforced: bool,
    additional_deny_read_paths: Sequence[str | Path] = (),
    additional_deny_write_paths: Sequence[str | Path] = (),
    is_cancelled: Callable[[], bool] | None = None,
) -> ProcessCaptureResult:
    permissions = ResolvedWindowsSandboxPermissions.try_from_permission_profile_for_cwd(
        permission_profile, permission_profile_cwd
    )
    environment = dict(env_map)
    normalize_null_device_env(environment)
    ensure_non_interactive_pager(environment)
    inherit_path_env(environment)
    environment["GIT_CONFIG_COUNT"] = "1"
    environment["GIT_CONFIG_KEY_0"] = "safe.directory"
    environment["GIT_CONFIG_VALUE_0"] = str(Path(cwd))

    identity_kind = SandboxNetworkIdentity.from_permissions(permissions, proxy_enforced)
    common = dict(
        proxy_enforced=proxy_enforced,
        deny_read_paths=additional_deny_read_paths,
        deny_write_paths=additional_deny_write_paths,
    )
    if setup_mismatch_reason(codex_home, identity_kind, environment) is not None:
        payload = build_elevation_payload(
            permissions, cwd, environment, codex_home, refresh_only=False, **common
        )
        run_setup_helper(payload, elevate=not is_elevated())

    creds = select_identity(identity_kind, codex_home)
    if creds is None:
        raise RuntimeError(
            "Windows sandbox setup is missing or out of date; rerun the sandbox setup with elevation"
        )
    refresh = build_elevation_payload(
        permissions, cwd, environment, codex_home, refresh_only=True, **common
    )
    run_setup_helper(refresh, elevate=False)

    process = spawn_runner_popen(
        creds,
        command,
        cwd,
        environment,
        permission_profile=permission_profile,
        permission_profile_cwd=permission_profile_cwd,
        codex_home=codex_home,
        cap_sids=_capability_sid_texts(permissions, cwd, environment, codex_home),
        stdin_open=False,
        tty=False,
        merge_stderr=False,
        use_private_desktop=use_private_desktop,
    )
    chunks: list[bytes] = []
    error_chunks: list[bytes] = []
    import threading
    import time

    reader = threading.Thread(target=lambda: chunks.append(_read_process_stream(process, "stdout")), daemon=True)
    reader.start()
    error_reader = threading.Thread(
        target=lambda: error_chunks.append(_read_process_stream(process, "stderr")),
        daemon=True,
    )
    error_reader.start()
    started = time.monotonic()
    timed_out = False
    cancelled = False
    try:
        while process.poll() is None:
            if is_cancelled is not None and is_cancelled():
                cancelled = True
                process.terminate()
                break
            if timeout_ms is not None and (time.monotonic() - started) * 1000 >= timeout_ms:
                timed_out = True
                process.terminate()
                break
            time.sleep(0.02)
        exit_code = process.wait(timeout=5)
        reader.join(5)
        error_reader.join(5)
        return ProcessCaptureResult(
            192 if timed_out else 1 if cancelled else exit_code,
            b"".join(chunks),
            b"".join(error_chunks),
            timed_out,
            cancelled,
        )
    finally:
        process.close()


def spawn_elevated_popen(
    permission_profile: PermissionProfile,
    permission_profile_cwd: str | Path,
    codex_home: str | Path,
    command: Sequence[str],
    cwd: str | Path,
    env_map: Mapping[str, str],
    *,
    stdin_open: bool,
    tty: bool = False,
    merge_stderr: bool = True,
    use_private_desktop: bool,
    proxy_enforced: bool,
    additional_deny_read_paths: Sequence[str | Path] = (),
    additional_deny_write_paths: Sequence[str | Path] = (),
) -> RunnerBackedPopen:
    permissions = ResolvedWindowsSandboxPermissions.try_from_permission_profile_for_cwd(
        permission_profile, permission_profile_cwd
    )
    environment = dict(env_map)
    normalize_null_device_env(environment)
    ensure_non_interactive_pager(environment)
    inherit_path_env(environment)
    environment["GIT_CONFIG_COUNT"] = "1"
    environment["GIT_CONFIG_KEY_0"] = "safe.directory"
    environment["GIT_CONFIG_VALUE_0"] = str(Path(cwd))
    identity_kind = SandboxNetworkIdentity.from_permissions(permissions, proxy_enforced)
    common = dict(
        proxy_enforced=proxy_enforced,
        deny_read_paths=additional_deny_read_paths,
        deny_write_paths=additional_deny_write_paths,
    )
    if setup_mismatch_reason(codex_home, identity_kind, environment) is not None:
        payload = build_elevation_payload(permissions, cwd, environment, codex_home, refresh_only=False, **common)
        run_setup_helper(payload, elevate=not is_elevated())
    creds = select_identity(identity_kind, codex_home)
    if creds is None:
        raise RuntimeError("Windows sandbox setup is missing or out of date")
    refresh = build_elevation_payload(permissions, cwd, environment, codex_home, refresh_only=True, **common)
    run_setup_helper(refresh, elevate=False)
    return spawn_runner_popen(
        creds,
        command,
        cwd,
        environment,
        permission_profile=permission_profile,
        permission_profile_cwd=permission_profile_cwd,
        codex_home=codex_home,
        cap_sids=_capability_sid_texts(permissions, cwd, environment, codex_home),
        stdin_open=stdin_open,
        tty=tty,
        merge_stderr=merge_stderr,
        use_private_desktop=use_private_desktop,
    )


def _capability_sid_texts(
    permissions: ResolvedWindowsSandboxPermissions,
    cwd: str | Path,
    env_map: Mapping[str, str],
    codex_home: str | Path,
) -> tuple[str, ...]:
    if not permissions.uses_write_capabilities_for_cwd(cwd, env_map):
        return (load_or_create_cap_sids(codex_home).readonly,)
    roots = effective_write_roots_for_permissions(permissions, cwd, env_map, codex_home)
    values = tuple(workspace_write_cap_sid_for_root(codex_home, cwd, root) for root in roots)
    if not values:
        raise RuntimeError("workspace-write sandbox has no writable root capability SIDs")
    return values


__all__ = ["ElevatedSandboxProfileCaptureRequest", "run_elevated_capture", "spawn_elevated_popen"]
