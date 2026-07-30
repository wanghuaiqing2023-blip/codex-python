"""Binary entrypoint owned by ``mcp-server/src/main.rs``."""

from __future__ import annotations

import asyncio
import io
import sys
from typing import Iterable, TextIO

from . import run_main


def run_command(
    command_args: Iterable[str],
    *,
    stdout: TextIO,
    stderr: TextIO,
    stdin: TextIO | None,
) -> int:
    args = tuple(command_args)
    if any(arg in {"-h", "--help"} for arg in args):
        print("Usage: codex mcp-server [--strict-config]", file=stdout)
        return 0
    if stdin is None:
        print("pycodex: mcp-server requires stdin.", file=stderr)
        return 1
    if isinstance(stdin, str):
        stdin = io.StringIO(stdin)
    elif isinstance(stdin, (bytes, bytearray)):
        stdin = io.BytesIO(bytes(stdin))
    try:
        asyncio.run(
            run_main(
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                strict_config="--strict-config" in args,
            )
        )
    except (OSError, ValueError) as exc:
        print(f"pycodex: mcp-server failed: {exc}", file=stderr)
        return 1
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    return run_command(
        tuple(sys.argv[1:] if argv is None else argv),
        stdout=sys.stdout,
        stderr=sys.stderr,
        stdin=sys.stdin,
    )


if __name__ == "__main__":
    raise SystemExit(main())
