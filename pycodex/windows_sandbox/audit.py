"""World-writable directory audit and capability deny application.

Rust owner: ``codex-windows-sandbox::audit``.
"""

from __future__ import annotations

import os
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from .acl import add_deny_write_ace, path_mask_allows
from .cap import (
    load_or_create_cap_sids,
    workspace_write_cap_sid_for_root,
    workspace_write_root_contains_path,
)
from .logging import debug_log, log_note
from .path_normalization import canonical_path_key
from .setup import effective_write_roots_for_permissions
from .token import LocalSid


MAX_ITEMS_PER_DIR = 1000
AUDIT_TIME_LIMIT_SECS = 2.0
MAX_CHECKED_LIMIT = 50_000
WORLD_WRITE_MASK = 0x00000002 | 0x00000004 | 0x00000010 | 0x00000100
SKIP_DIR_SUFFIXES = (
    "/windows/installer",
    "/windows/registration",
    "/programdata",
)
_SYSTEM_ROOTS: tuple[Path, ...] = (Path("C:/"), Path("C:/Windows"))


def _unique_push(
    seen: set[str],
    output: list[Path],
    path: str | Path,
) -> None:
    try:
        absolute = Path(path).resolve(strict=True)
    except OSError:
        return
    key = canonical_path_key(absolute)
    if key not in seen:
        seen.add(key)
        output.append(absolute)


def _gather_candidates(
    cwd: str | Path,
    env: Mapping[str, str],
) -> list[Path]:
    seen: set[str] = set()
    output: list[Path] = []
    _unique_push(seen, output, cwd)
    for key in ("TEMP", "TMP"):
        value = env.get(key) or os.environ.get(key)
        if value:
            _unique_push(seen, output, value)
    for key in ("USERPROFILE", "PUBLIC"):
        value = os.environ.get(key)
        if value:
            _unique_push(seen, output, value)
    path_value = env.get("PATH") or os.environ.get("PATH")
    if path_value:
        for entry in path_value.split(os.pathsep):
            if entry:
                _unique_push(seen, output, entry)
    for root in _SYSTEM_ROOTS:
        _unique_push(seen, output, root)
    return output


def _path_has_world_write_allow(path: str | Path) -> bool:
    with LocalSid("S-1-1-0") as world:
        return path_mask_allows(
            path,
            (world,),
            WORLD_WRITE_MASK,
            require_all_bits=False,
        )


def audit_everyone_writable(
    cwd: str | Path,
    env: Mapping[str, str],
    logs_base_dir: str | Path | None = None,
) -> list[Path]:
    started = time.monotonic()
    cwd_path = Path(cwd)
    flagged: list[Path] = []
    seen: set[str] = set()
    checked = 0

    def expired() -> bool:
        return (
            time.monotonic() - started > AUDIT_TIME_LIMIT_SECS
            or checked > MAX_CHECKED_LIMIT
        )

    def check(path: Path) -> None:
        nonlocal checked
        checked += 1
        try:
            writable = _path_has_world_write_allow(path)
        except OSError as exc:
            debug_log(
                "AUDIT: treating unreadable ACL as not world-writable: "
                f"{path} ({exc})",
                logs_base_dir,
            )
            return
        if not writable:
            return
        key = canonical_path_key(path)
        if key not in seen:
            seen.add(key)
            flagged.append(path)

    try:
        immediate = list(cwd_path.iterdir())
    except OSError:
        immediate = []
    for path in immediate[:MAX_ITEMS_PER_DIR]:
        if expired():
            break
        try:
            if path.is_symlink() or not path.is_dir():
                continue
        except OSError:
            continue
        check(path)

    for root in _gather_candidates(cwd_path, env):
        if expired():
            break
        check(root)
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for path in children[:MAX_ITEMS_PER_DIR]:
            if expired():
                break
            try:
                if path.is_symlink() or not path.is_dir():
                    continue
            except OSError:
                continue
            normalized = str(path).replace("\\", "/").lower()
            if any(
                normalized.endswith(suffix)
                for suffix in SKIP_DIR_SUFFIXES
            ):
                continue
            check(path)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    if flagged:
        paths = "".join(f"\n - {path}" for path in flagged)
        log_note(
            "AUDIT: world-writable scan FAILED; "
            f"cwd={cwd_path!r}; checked={checked}; "
            f"duration_ms={elapsed_ms}; flagged:{paths}",
            logs_base_dir,
        )
    else:
        log_note(
            "AUDIT: world-writable scan OK; "
            f"checked={checked}; duration_ms={elapsed_ms}",
            logs_base_dir,
        )
    return flagged


def apply_world_writable_scan_and_denies_for_permissions(
    codex_home: str | Path,
    cwd: str | Path,
    env_map: Mapping[str, str],
    permissions: object,
    logs_base_dir: str | Path | None = None,
) -> None:
    flagged = audit_everyone_writable(cwd, env_map, logs_base_dir)
    if not flagged:
        return
    try:
        _apply_capability_denies_for_world_writable_for_permissions(
            Path(codex_home),
            flagged,
            permissions,
            Path(cwd),
            env_map,
            logs_base_dir,
        )
    except OSError as exc:
        log_note(
            f"AUDIT: failed to apply capability deny ACEs: {exc}",
            logs_base_dir,
        )


def _apply_capability_denies_for_world_writable_for_permissions(
    codex_home: Path,
    flagged: Sequence[Path],
    permissions: object,
    cwd: Path,
    env_map: Mapping[str, str],
    logs_base_dir: str | Path | None,
) -> None:
    if not flagged:
        return
    codex_home.mkdir(parents=True, exist_ok=True)
    caps = load_or_create_cap_sids(codex_home)
    if not permissions.is_enforceable_by_windows_sandbox():
        return

    active_sids: list[LocalSid] = []
    workspace_roots: tuple[Path, ...] = ()
    try:
        if permissions.uses_write_capabilities_for_cwd(cwd, env_map):
            workspace_roots = effective_write_roots_for_permissions(
                permissions,
                cwd,
                env_map,
                codex_home,
            )
            active_sids.extend(
                LocalSid(
                    workspace_write_cap_sid_for_root(
                        codex_home,
                        cwd,
                        root,
                    )
                )
                for root in workspace_roots
            )
        else:
            active_sids.append(LocalSid(caps.readonly))

        for path in flagged:
            if any(
                workspace_write_root_contains_path(root, path)
                for root in workspace_roots
            ):
                continue
            for active_sid in active_sids:
                try:
                    changed = add_deny_write_ace(path, active_sid)
                except OSError as exc:
                    log_note(
                        "AUDIT: failed to apply capability deny ACE to "
                        f"{path}: {exc}",
                        logs_base_dir,
                    )
                else:
                    if changed:
                        log_note(
                            "AUDIT: applied capability deny ACE to "
                            f"{path}",
                            logs_base_dir,
                        )
    finally:
        for active_sid in active_sids:
            active_sid.close()


__all__ = [
    "AUDIT_TIME_LIMIT_SECS",
    "MAX_CHECKED_LIMIT",
    "MAX_ITEMS_PER_DIR",
    "audit_everyone_writable",
    "apply_world_writable_scan_and_denies_for_permissions",
]
