"""Codex Desktop app command helpers.

Ported from ``codex/codex-rs/cli/src/app_cmd.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppCommand:
    path: Path = Path(".")
    download_url_override: str | None = None


def workspace_for_app_command(path: str | Path = ".") -> Path:
    """Return the workspace path passed to the desktop app launcher."""

    workspace = Path(path)
    try:
        return workspace.resolve(strict=True)
    except OSError:
        return workspace
