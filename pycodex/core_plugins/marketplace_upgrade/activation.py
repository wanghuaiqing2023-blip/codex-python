"""Marketplace activation for ``marketplace_upgrade::activation``."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

METADATA_FILE = ".codex-marketplace.json"


def installed_marketplace_metadata_matches(
    root: str | Path,
    expected: dict[str, Any],
) -> bool:
    try:
        value = json.loads(
            (Path(root) / METADATA_FILE).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return False
    return value == expected


def write_installed_marketplace_metadata(
    root: str | Path,
    metadata: dict[str, Any],
) -> None:
    path = Path(root) / METADATA_FILE
    path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def activate_marketplace_root(staged_root: str | Path, destination: str | Path) -> None:
    source = Path(staged_root)
    target = Path(destination)
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    source.replace(target)


__all__ = [
    "activate_marketplace_root",
    "installed_marketplace_metadata_matches",
    "write_installed_marketplace_metadata",
]
