"""Platform entrypoint for codex-execve-wrapper."""

from __future__ import annotations

import asyncio
import os
import sys

from ..unix.execve_wrapper import main_execve_wrapper


def main(
    argv: list[str] | tuple[str, ...] | None = None,
    *,
    platform: str | None = None,
) -> int:
    current_platform = os.name if platform is None else platform
    if current_platform != "posix":
        print(
            "codex-execve-wrapper is only implemented for UNIX",
            file=sys.stderr,
        )
        return 1
    return asyncio.run(main_execve_wrapper(argv))


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
