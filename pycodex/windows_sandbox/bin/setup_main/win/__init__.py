"""Windows implementation of the elevated sandbox setup binary."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from datetime import datetime, timezone
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import TextIO

from ....acl import (
    WRITE_ALLOW_MASK,
    FILE_GENERIC_EXECUTE,
    FILE_GENERIC_READ,
    add_deny_read_ace,
    add_deny_write_ace,
    ensure_allow_mask_aces,
    ensure_allow_write_aces,
    path_mask_allows,
)
from ....cap import workspace_write_cap_sid_for_root
from ....deny_read_state import sync_persistent_deny_read_acls
from ....dpapi import protect
from ....firewall import install_offline_firewall_rules
from ....hide_users import hide_newly_created_users
from ....local_accounts import (
    SANDBOX_USERS_GROUP,
    provision_sandbox_users,
    resolve_account_sid_string,
)
from ....logging import log_note, log_writer
from ....setup import (
    SETUP_VERSION,
    sandbox_bin_dir,
    sandbox_dir,
    sandbox_secrets_dir,
    sandbox_users_path,
    setup_marker_path,
)
from ....setup_error import (
    SetupErrorCode,
    SetupErrorReport,
    SetupFailure,
    write_setup_error_report,
)
from ....token import LocalSid
from ....wfp_setup import install_wfp_filters
from ....workspace_acl import is_command_cwd_root
from .read_acl_mutex import acquire_read_acl_mutex, read_acl_mutex_exists
from .setup_runtime_bin import ensure_codex_app_runtime_bin_readable


class SetupMode(str, Enum):
    FULL = "full"
    READ_ACLS_ONLY = "read-acls-only"


def decode_payload(encoded: str) -> dict[str, object]:
    try:
        value = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SetupFailure(
            SetupErrorCode.HELPER_REQUEST_ARGS_FAILED,
            f"invalid setup payload: {exc}",
        ) from exc
    if not isinstance(value, dict) or value.get("version") != SETUP_VERSION:
        actual = value.get("version") if isinstance(value, dict) else None
        raise SetupFailure(
            SetupErrorCode.HELPER_REQUEST_ARGS_FAILED,
            f"setup version mismatch: expected {SETUP_VERSION}, got {actual}",
        )
    mode = value.get("mode", SetupMode.FULL.value)
    try:
        value["mode"] = SetupMode(mode).value
    except ValueError as exc:
        raise SetupFailure(
            SetupErrorCode.HELPER_REQUEST_ARGS_FAILED,
            f"invalid setup mode: {mode}",
        ) from exc
    return value


def run_setup_payload(payload: dict[str, object]) -> None:
    codex_home = _path(payload, "codex_home")
    sandbox_dir(codex_home).mkdir(parents=True, exist_ok=True)
    stream = log_writer(sandbox_dir(codex_home)) or StringIO()
    try:
        mode = SetupMode(str(payload.get("mode", SetupMode.FULL.value)))
        if mode is SetupMode.READ_ACLS_ONLY:
            _run_read_acl_only(payload, stream)
        else:
            _run_setup_full(payload, stream)
    finally:
        stream.close()


def _run_read_acl_only(payload: dict[str, object], log: TextIO) -> None:
    guard = acquire_read_acl_mutex()
    if guard is None:
        _log_line(log, "read ACL helper already running; skipping")
        return
    with guard:
        _log_line(log, "read-acl-only mode: applying read ACLs")
        _apply_read_acl_grants(_paths(payload, "read_roots"))
        _log_line(log, "read ACL run completed")


def _run_setup_full(payload: dict[str, object], log: TextIO) -> None:
    codex_home = _path(payload, "codex_home")
    offline_username = _text(payload, "offline_username")
    online_username = _text(payload, "online_username")
    command_cwd = _path(payload, "command_cwd")
    read_roots = _paths(payload, "read_roots")
    write_roots = _paths(payload, "write_roots")
    deny_read_paths = _paths(payload, "deny_read_paths")
    deny_write_paths = _paths(payload, "deny_write_paths")
    proxy_ports = _ports(payload.get("proxy_ports", []))
    allow_local_binding = bool(payload.get("allow_local_binding", False))
    refresh_only = bool(payload.get("refresh_only", False))

    sandbox_secrets_dir(codex_home).mkdir(parents=True, exist_ok=True)
    offline_password = ""
    online_password = ""
    if not refresh_only:
        offline_password, online_password = provision_sandbox_users(
            offline_username,
            online_username,
        )
        hide_newly_created_users(
            (offline_username, online_username),
            sandbox_dir(codex_home),
        )
        offline_sid = resolve_account_sid_string(offline_username)
        install_offline_firewall_rules(
            offline_sid,
            proxy_ports,
            allow_local_binding,
        )
        install_wfp_filters(
            codex_home,
            offline_username,
            payload.get("otel"),
            lambda message: log_note(message, sandbox_dir(codex_home)),
        )

    _apply_deny_read_acls(codex_home, deny_read_paths)
    _spawn_read_acl_helper_if_needed(payload, read_roots, log)

    group_sid_text = resolve_account_sid_string(SANDBOX_USERS_GROUP)
    refresh_errors: list[str] = []
    if refresh_only:
        with LocalSid(group_sid_text) as group_sid:
            ensure_codex_app_runtime_bin_readable(
                group_sid,
                refresh_errors,
                log,
            )

    _apply_write_acls(
        codex_home,
        command_cwd,
        write_roots,
        deny_write_paths,
    )
    if not refresh_only:
        _write_setup_state(
            codex_home,
            offline_username,
            offline_password,
            online_username,
            online_password,
            proxy_ports,
            allow_local_binding,
            read_roots,
            write_roots,
        )
    _lock_setup_dirs(codex_home)
    if refresh_only and refresh_errors:
        raise SetupFailure(
            SetupErrorCode.HELPER_ACL_APPLY_FAILED,
            f"refresh completed with errors: {refresh_errors}",
        )


def _spawn_read_acl_helper_if_needed(
    payload: dict[str, object],
    read_roots: tuple[Path, ...],
    log: TextIO,
) -> None:
    if not read_roots:
        _log_line(log, "no read roots to grant; skipping read ACL helper")
        return
    try:
        running = read_acl_mutex_exists()
    except OSError as exc:
        _log_line(log, f"read ACL mutex check failed: {exc}; spawning anyway")
        running = False
    if running:
        _log_line(log, "read ACL helper already running; skipping spawn")
        return

    read_payload = dict(payload)
    read_payload["mode"] = SetupMode.READ_ACLS_ONLY.value
    read_payload["refresh_only"] = True
    encoded = base64.b64encode(
        json.dumps(read_payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    try:
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "pycodex.windows_sandbox.bin.setup_main",
                encoded,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise SetupFailure(
            SetupErrorCode.HELPER_READ_ACL_HELPER_SPAWN_FAILED,
            f"spawn read ACL helper failed: {exc}",
        ) from exc


def _apply_read_acl_grants(read_roots: tuple[Path, ...]) -> None:
    group_sid_text = resolve_account_sid_string(SANDBOX_USERS_GROUP)
    with LocalSid(group_sid_text) as group_sid:
        with (
            LocalSid("S-1-5-32-545") as users_sid,
            LocalSid("S-1-5-11") as authenticated_users_sid,
            LocalSid("S-1-1-0") as everyone_sid,
        ):
            builtin_readers = (users_sid, authenticated_users_sid, everyone_sid)
            for root in read_roots:
                if root.exists() and not path_mask_allows(
                    root,
                    builtin_readers,
                    FILE_GENERIC_READ | FILE_GENERIC_EXECUTE,
                ):
                    ensure_allow_mask_aces(
                        root,
                        (group_sid,),
                        FILE_GENERIC_READ | FILE_GENERIC_EXECUTE,
                    )


def _apply_deny_read_acls(
    codex_home: Path,
    deny_read_paths: tuple[Path, ...],
) -> None:
    group_sid_text = resolve_account_sid_string(SANDBOX_USERS_GROUP)
    with LocalSid(group_sid_text) as group_sid:
        sync_persistent_deny_read_acls(
            codex_home,
            group_sid_text,
            deny_read_paths,
            group_sid,
        )


def _apply_write_acls(
    codex_home: Path,
    command_cwd: Path,
    write_roots: tuple[Path, ...],
    deny_write_paths: tuple[Path, ...],
) -> None:
    group_sid_text = resolve_account_sid_string(SANDBOX_USERS_GROUP)
    capability_sids: list[LocalSid] = []
    canonical_command_cwd = command_cwd.resolve(strict=False)
    try:
        with LocalSid(group_sid_text) as group_sid:
            for root in write_roots:
                if not root.exists():
                    continue
                capability_root = (
                    command_cwd
                    if is_command_cwd_root(root, canonical_command_cwd)
                    else root
                )
                sid_text = workspace_write_cap_sid_for_root(
                    codex_home,
                    command_cwd,
                    capability_root,
                )
                capability = LocalSid(sid_text)
                capability_sids.append(capability)
                ensure_allow_mask_aces(root, (group_sid,), WRITE_ALLOW_MASK)
                ensure_allow_write_aces(root, (capability,))
            for path in deny_write_paths:
                if not path.exists():
                    path.mkdir(parents=True, exist_ok=True)
                for capability in capability_sids:
                    add_deny_write_ace(path, capability)
    finally:
        for capability in capability_sids:
            capability.close()


def _lock_setup_dirs(codex_home: Path) -> None:
    group_sid_text = resolve_account_sid_string(SANDBOX_USERS_GROUP)
    with LocalSid(group_sid_text) as group_sid:
        bin_dir = sandbox_bin_dir(codex_home)
        state_dir = sandbox_dir(codex_home)
        secrets_dir = sandbox_secrets_dir(codex_home)
        for path in (bin_dir, state_dir, secrets_dir):
            path.mkdir(parents=True, exist_ok=True)
        ensure_allow_mask_aces(
            bin_dir,
            (group_sid,),
            FILE_GENERIC_READ | FILE_GENERIC_EXECUTE,
        )
        ensure_allow_mask_aces(state_dir, (group_sid,), WRITE_ALLOW_MASK)
        add_deny_read_ace(secrets_dir, group_sid)
        add_deny_write_ace(secrets_dir, group_sid)


def _write_setup_state(
    codex_home: Path,
    offline_username: str,
    offline_password: str,
    online_username: str,
    online_password: str,
    proxy_ports: tuple[int, ...],
    allow_local_binding: bool,
    read_roots: tuple[Path, ...],
    write_roots: tuple[Path, ...],
) -> None:
    users = {
        "version": SETUP_VERSION,
        "offline": {
            "username": offline_username,
            "password": base64.b64encode(
                protect(offline_password.encode("utf-8"))
            ).decode("ascii"),
        },
        "online": {
            "username": online_username,
            "password": base64.b64encode(
                protect(online_password.encode("utf-8"))
            ).decode("ascii"),
        },
    }
    marker = {
        "version": SETUP_VERSION,
        "offline_username": offline_username,
        "online_username": online_username,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proxy_ports": list(proxy_ports),
        "allow_local_binding": allow_local_binding,
        "read_roots": [str(path) for path in read_roots],
        "write_roots": [str(path) for path in write_roots],
    }
    sandbox_users_path(codex_home).write_text(
        json.dumps(users, indent=2),
        encoding="utf-8",
    )
    setup_marker_path(codex_home).write_text(
        json.dumps(marker, indent=2),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    codex_home: Path | None = None
    try:
        if len(args) != 1:
            raise SetupFailure(
                SetupErrorCode.HELPER_REQUEST_ARGS_FAILED,
                "expected payload argument",
            )
        payload = decode_payload(args[0])
        codex_home = _path(payload, "codex_home")
        run_setup_payload(payload)
        return 0
    except BaseException as exc:
        failure = (
            exc
            if isinstance(exc, SetupFailure)
            else SetupFailure(SetupErrorCode.HELPER_UNKNOWN_ERROR, str(exc))
        )
        if codex_home is not None:
            try:
                write_setup_error_report(
                    codex_home,
                    SetupErrorReport(failure.code, failure.message),
                )
            except OSError:
                pass
        print(str(failure), file=sys.stderr)
        return 1


def _log_line(log: TextIO, message: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    log.write(f"[{timestamp}] {message}\n")


def _text(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise SetupFailure(
            SetupErrorCode.HELPER_REQUEST_ARGS_FAILED,
            f"{key} must be a non-empty string",
        )
    return item


def _path(value: dict[str, object], key: str) -> Path:
    return Path(_text(value, key))


def _paths(value: dict[str, object], key: str) -> tuple[Path, ...]:
    items = value.get(key, [])
    if not isinstance(items, list) or not all(
        isinstance(item, str) for item in items
    ):
        raise SetupFailure(
            SetupErrorCode.HELPER_REQUEST_ARGS_FAILED,
            f"{key} must be a string list",
        )
    return tuple(Path(item) for item in items)


def _ports(value: object) -> tuple[int, ...]:
    if not isinstance(value, list) or any(
        isinstance(item, bool)
        or not isinstance(item, int)
        or not 1 <= item <= 65535
        for item in value
    ):
        raise SetupFailure(
            SetupErrorCode.HELPER_REQUEST_ARGS_FAILED,
            "proxy_ports must contain valid ports",
        )
    return tuple(sorted(set(value)))


__all__ = [
    "SetupMode",
    "decode_payload",
    "main",
    "run_setup_payload",
]
