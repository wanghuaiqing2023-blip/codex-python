"""Marketplace installation helpers for ``marketplace_add::install``."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pycodex.plugin import validate_plugin_segment


def clone_git_source(
    url: str,
    ref_name: str | None,
    sparse_paths: list[str] | tuple[str, ...],
    destination: str | Path,
) -> None:
    target = Path(destination)
    command = ["git", "clone", "--depth", "1"]
    if ref_name:
        command.extend(["--branch", ref_name])
    if sparse_paths:
        command.append("--filter=blob:none")
        command.append("--sparse")
    command.extend(["--", url, str(target)])
    subprocess.run(command, check=True, capture_output=True, text=True)
    if sparse_paths:
        subprocess.run(
            ["git", "-C", str(target), "sparse-checkout", "set", "--", *sparse_paths],
            check=True,
            capture_output=True,
            text=True,
        )


def safe_marketplace_dir_name(marketplace_name: str) -> str:
    validate_plugin_segment(marketplace_name, "marketplace name")
    return marketplace_name


def ensure_marketplace_destination_is_inside_install_root(
    install_root: str | Path,
    destination: str | Path,
) -> None:
    root = Path(install_root).resolve()
    target = Path(destination).resolve()
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise ValueError("marketplace destination must stay inside install root") from exc
    if len(relative.parts) != 1:
        raise ValueError("marketplace destination must be a direct child of install root")


def replace_marketplace_root(source: str | Path, target: str | Path) -> None:
    source_path = Path(source)
    target_path = Path(target)
    if target_path.exists():
        if target_path.is_dir():
            shutil.rmtree(target_path)
        else:
            target_path.unlink()
    source_path.replace(target_path)


def marketplace_staging_root(install_root: str | Path) -> Path:
    return Path(install_root) / ".staging"


__all__ = [
    "clone_git_source",
    "ensure_marketplace_destination_is_inside_install_root",
    "marketplace_staging_root",
    "replace_marketplace_root",
    "safe_marketplace_dir_name",
]
