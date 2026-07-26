"""Stable CWD junction creation for the elevated command runner.

Rust owner: ``bin::codex-command-runner::win::cwd_junction``.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from ....logging import log_note


def junction_name_for_path(path: str | Path) -> str:
    value = os.fspath(path).encode("utf-8", errors="surrogatepass")
    return hashlib.blake2b(value, digest_size=8).hexdigest()


def junction_root_for_userprofile(userprofile: str | Path) -> Path:
    return Path(userprofile) / ".codex" / ".sandbox" / "cwd"


def create_cwd_junction(
    requested_cwd: str | Path,
    log_dir: str | Path | None,
) -> Path | None:
    userprofile = os.environ.get("USERPROFILE")
    if not userprofile:
        return None
    requested = Path(requested_cwd)
    log_path = Path(log_dir) if log_dir is not None else None
    root = junction_root_for_userprofile(userprofile)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log_note(f"junction: failed to create {root}: {exc}", log_path)
        return None

    junction = root / junction_name_for_path(requested)
    if junction.exists():
        is_junction = getattr(os.path, "isjunction", lambda _path: False)
        try:
            if is_junction(junction) or junction.is_symlink():
                log_note(
                    f"junction: reusing existing {junction}",
                    log_path,
                )
                return junction
            log_note(
                "junction: existing path is not a reparse point, recreating "
                f"{junction}",
                log_path,
            )
            junction.rmdir()
        except OSError as exc:
            log_note(
                f"junction: failed to remove existing {junction}: {exc}",
                log_path,
            )
            return None

    log_note(
        f'junction: creating via cmd /c mklink /J "{junction}" "{requested}"',
        log_path,
    )
    try:
        result = subprocess.run(
            [
                "cmd.exe",
                "/d",
                "/c",
                "mklink",
                "/J",
                str(junction),
                str(requested),
            ],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        log_note(f"junction: mklink failed to run: {exc}", log_path)
        return None
    if result.returncode == 0 and junction.exists():
        log_note(
            f"junction: created {junction} -> {requested}",
            log_path,
        )
        return junction
    stdout = result.stdout.decode(errors="replace").strip()
    stderr = result.stderr.decode(errors="replace").strip()
    log_note(
        "junction: mklink failed "
        f"status={result.returncode} stdout={stdout} stderr={stderr}",
        log_path,
    )
    return None


__all__ = [
    "create_cwd_junction",
    "junction_name_for_path",
    "junction_root_for_userprofile",
]
