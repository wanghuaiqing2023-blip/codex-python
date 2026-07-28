"""Git transport for ``marketplace_upgrade::git``."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git_remote_revision(
    source: str,
    ref_name: str | None = None,
    timeout: float = 30.0,
) -> str:
    reference = ref_name or "HEAD"
    result = subprocess.run(
        ["git", "ls-remote", source, reference],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    line = next((line for line in result.stdout.splitlines() if line.strip()), "")
    sha = line.split(maxsplit=1)[0] if line else ""
    if not sha:
        raise RuntimeError(f"git remote did not return revision for {reference}")
    return sha


def clone_git_source(
    source: str,
    ref_name: str | None,
    sparse_paths: list[str] | tuple[str, ...],
    destination: str | Path,
    timeout: float = 30.0,
) -> None:
    command = ["git", "clone", "--depth", "1"]
    if ref_name:
        command.extend(["--branch", ref_name])
    if sparse_paths:
        command.extend(["--filter=blob:none", "--sparse"])
    command.extend(["--", source, str(destination)])
    subprocess.run(command, check=True, timeout=timeout)
    if sparse_paths:
        subprocess.run(
            ["git", "-C", str(destination), "sparse-checkout", "set", "--", *sparse_paths],
            check=True,
            timeout=timeout,
        )


__all__ = ["clone_git_source", "git_remote_revision"]
