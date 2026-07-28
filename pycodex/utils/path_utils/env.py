"""Environment detection owned by ``codex-utils-path::env``."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path


def is_wsl(
    *,
    env: Mapping[str, str] | None = None,
    proc_version_path: str | Path = "/proc/version",
    platform: str | None = None,
) -> bool:
    platform = sys.platform if platform is None else platform
    if not str(platform).startswith("linux"):
        return False
    environment = os.environ if env is None else env
    if "WSL_DISTRO_NAME" in environment:
        return True
    try:
        version = Path(proc_version_path).read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except OSError:
        return False
    return "microsoft" in version.lower()


__all__ = ["is_wsl"]
