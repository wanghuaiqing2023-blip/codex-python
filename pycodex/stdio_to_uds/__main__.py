"""Binary entrypoint for ``codex-stdio-to-uds``."""

from __future__ import annotations

import asyncio
import sys
from typing import Sequence

from . import run


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("Usage: codex-stdio-to-uds <socket-path>", file=sys.stderr)
        return 1
    if len(args) > 1:
        print("Expected exactly one argument: <socket-path>", file=sys.stderr)
        return 1

    asyncio.run(run(args[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
