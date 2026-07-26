"""Cargo binary entrypoint for ``codex-windows-sandbox-setup``."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence

from .win import main as windows_setup_main


def main(argv: Sequence[str] | None = None) -> int:
    if os.name != "nt":
        raise RuntimeError("codex-windows-sandbox-setup is only supported on Windows")
    return windows_setup_main(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
