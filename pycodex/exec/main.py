"""Entry point for the non-interactive ``codex-exec`` binary."""

from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Iterable

from pycodex.arg0 import Arg0DispatchPaths, arg0_dispatch_or_else
from pycodex.config import ConfigOverride

from .cli import ExecCli, parse_exec_args


@dataclass(frozen=True)
class TopCli:
    config_overrides: tuple[ConfigOverride, ...]
    inner: ExecCli


def parse_top_cli(argv: Iterable[str]) -> TopCli:
    tokens = tuple(argv)
    inner = parse_exec_args(tokens)
    return TopCli(config_overrides=inner.config_overrides, inner=inner)


def main(argv: Iterable[str] | None = None) -> int:
    args = tuple(sys.argv[1:] if argv is None else argv)

    def run(_paths: Arg0DispatchPaths) -> int:
        # Import lazily so the binary wrapper does not create an exec/CLI cycle.
        from pycodex.cli.main import main as cli_main

        return int(cli_main(["exec", *args]) or 0)

    return int(arg0_dispatch_or_else(run, argv=[sys.argv[0], *args]) or 0)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["TopCli", "main", "parse_top_cli"]
