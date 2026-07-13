"""Elevated setup helper entrypoint for the Python Windows sandbox backend.

Rust owner: ``windows-sandbox-rs/src/bin/setup_main/win.rs`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .acl import (
    WRITE_ALLOW_MASK,
    FILE_GENERIC_EXECUTE,
    FILE_GENERIC_READ,
    add_deny_read_ace,
    add_deny_write_ace,
    ensure_allow_mask_aces,
    ensure_allow_write_aces,
    path_mask_allows,
)
from .cap import workspace_write_cap_sid_for_root
from .deny_read_state import sync_persistent_deny_read_acls
from .dpapi import protect
from .firewall import install_offline_firewall_rules
from .wfp import install_wfp_filters_for_account
from .local_accounts import (
    SANDBOX_USERS_GROUP,
    provision_sandbox_users,
    resolve_account_sid_string,
)
from .logging import log_note
from .setup import (
    SETUP_VERSION,
    sandbox_dir,
    sandbox_bin_dir,
    sandbox_secrets_dir,
    sandbox_users_path,
    setup_marker_path,
)
from .setup_error import SetupErrorCode, SetupErrorReport, SetupFailure, write_setup_error_report
from .token import LocalSid


def decode_payload(encoded: str) -> dict[str, object]:
    try:
        value = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SetupFailure(SetupErrorCode.HELPER_REQUEST_ARGS_FAILED, f"invalid setup payload: {exc}") from exc
    if not isinstance(value, dict) or value.get("version") != SETUP_VERSION:
        raise SetupFailure(
            SetupErrorCode.HELPER_REQUEST_ARGS_FAILED,
            f"setup version mismatch: expected {SETUP_VERSION}, got {value.get('version') if isinstance(value, dict) else None}",
        )
    return value


def run_setup_payload(payload: dict[str, object]) -> None:
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

    sandbox_dir(codex_home).mkdir(parents=True, exist_ok=True)
    sandbox_secrets_dir(codex_home).mkdir(parents=True, exist_ok=True)

    if refresh_only:
        _apply_acls(codex_home, command_cwd, read_roots, write_roots, deny_read_paths, deny_write_paths)
        _lock_setup_dirs(codex_home)
        return

    offline_password, online_password = provision_sandbox_users(offline_username, online_username)
    offline_sid = resolve_account_sid_string(offline_username)
    install_offline_firewall_rules(offline_sid, proxy_ports, allow_local_binding)
    try:
        installed_filter_count = install_wfp_filters_for_account(offline_username)
    except OSError as exc:
        # Fixed Rust treats WFP defense-filter setup as best effort; the
        # account-scoped outbound firewall rule remains the primary block.
        log_note(
            f"WFP setup failed for {offline_username}: {exc}; continuing elevated setup",
            sandbox_dir(codex_home),
        )
    else:
        log_note(
            f"WFP setup succeeded for {offline_username} with {installed_filter_count} installed filters",
            sandbox_dir(codex_home),
        )
    _apply_acls(codex_home, command_cwd, read_roots, write_roots, deny_read_paths, deny_write_paths)
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


def _apply_acls(
    codex_home: Path,
    command_cwd: Path,
    read_roots: tuple[Path, ...],
    write_roots: tuple[Path, ...],
    deny_read_paths: tuple[Path, ...],
    deny_write_paths: tuple[Path, ...],
) -> None:
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
                    root, builtin_readers, FILE_GENERIC_READ | FILE_GENERIC_EXECUTE
                ):
                    ensure_allow_mask_aces(root, (group_sid,), FILE_GENERIC_READ | FILE_GENERIC_EXECUTE)
        sync_persistent_deny_read_acls(codex_home, group_sid_text, deny_read_paths, group_sid)

    capability_sids: list[LocalSid] = []
    try:
        with LocalSid(group_sid_text) as group_sid:
            for root in write_roots:
                if not root.exists():
                    continue
                sid_text = workspace_write_cap_sid_for_root(codex_home, command_cwd, root)
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
    """Apply the fixed-Rust setup directory visibility contract."""

    group_sid_text = resolve_account_sid_string(SANDBOX_USERS_GROUP)
    with LocalSid(group_sid_text) as group_sid:
        bin_dir = sandbox_bin_dir(codex_home)
        state_dir = sandbox_dir(codex_home)
        secrets_dir = sandbox_secrets_dir(codex_home)
        for path in (bin_dir, state_dir, secrets_dir):
            path.mkdir(parents=True, exist_ok=True)
        ensure_allow_mask_aces(bin_dir, (group_sid,), FILE_GENERIC_READ | FILE_GENERIC_EXECUTE)
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
            "password": base64.b64encode(protect(offline_password.encode("utf-8"))).decode("ascii"),
        },
        "online": {
            "username": online_username,
            "password": base64.b64encode(protect(online_password.encode("utf-8"))).decode("ascii"),
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
    sandbox_users_path(codex_home).write_text(json.dumps(users, indent=2), encoding="utf-8")
    setup_marker_path(codex_home).write_text(json.dumps(marker, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    codex_home: Path | None = None
    try:
        if len(args) != 1:
            raise SetupFailure(SetupErrorCode.HELPER_REQUEST_ARGS_FAILED, "expected payload argument")
        payload = decode_payload(args[0])
        codex_home = _path(payload, "codex_home")
        run_setup_payload(payload)
        return 0
    except BaseException as exc:
        failure = exc if isinstance(exc, SetupFailure) else SetupFailure(SetupErrorCode.HELPER_UNKNOWN_ERROR, str(exc))
        if codex_home is not None:
            try:
                write_setup_error_report(codex_home, SetupErrorReport(failure.code, failure.message))
            except OSError:
                pass
        print(str(failure), file=sys.stderr)
        return 1


def _text(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise SetupFailure(SetupErrorCode.HELPER_REQUEST_ARGS_FAILED, f"{key} must be a non-empty string")
    return item


def _path(value: dict[str, object], key: str) -> Path:
    return Path(_text(value, key))


def _paths(value: dict[str, object], key: str) -> tuple[Path, ...]:
    items = value.get(key, [])
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise SetupFailure(SetupErrorCode.HELPER_REQUEST_ARGS_FAILED, f"{key} must be a string list")
    return tuple(Path(item) for item in items)


def _ports(value: object) -> tuple[int, ...]:
    if not isinstance(value, list) or any(isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= 65535 for item in value):
        raise SetupFailure(SetupErrorCode.HELPER_REQUEST_ARGS_FAILED, "proxy_ports must contain valid ports")
    return tuple(sorted(set(value)))


if __name__ == "__main__":
    raise SystemExit(main())
