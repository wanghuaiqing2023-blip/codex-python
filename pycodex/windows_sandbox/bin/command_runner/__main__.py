"""Executable entry point for the Windows sandbox command runner."""

from __future__ import annotations

import os

from .win import main as windows_main


def main(argv: list[str] | None = None) -> int:
    if os.name != "nt":
        raise RuntimeError("codex-command-runner is Windows-only")
    return windows_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
