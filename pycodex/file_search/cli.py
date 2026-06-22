"""CLI argument shape ported from Rust ``codex-file-search/src/cli.rs``."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class Cli:
    json: bool = False
    limit: int = 64
    cwd: Path | None = None
    compute_indices: bool = False
    threads: int = 2
    exclude: list[str] = field(default_factory=list)
    pattern: str | None = None

    def __post_init__(self) -> None:
        if int(self.limit) <= 0:
            raise ValueError("limit must be non-zero")
        if int(self.threads) <= 0:
            raise ValueError("threads must be non-zero")
        object.__setattr__(self, "limit", int(self.limit))
        object.__setattr__(self, "threads", int(self.threads))
        if self.cwd is not None and not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        object.__setattr__(self, "exclude", [str(item) for item in self.exclude])
        if self.pattern is not None:
            object.__setattr__(self, "pattern", str(self.pattern))

    @classmethod
    def parse_args(cls, argv: Sequence[str] | None = None) -> "Cli":
        parser = argparse.ArgumentParser(
            prog="codex-file-search",
            description="Fuzzy matches filenames under a directory.",
        )
        parser.add_argument("--json", action="store_true", default=False)
        parser.add_argument("--limit", "-l", type=_nonzero_int, default=64)
        parser.add_argument("--cwd", "-C", type=Path, default=None)
        parser.add_argument("--compute-indices", action="store_true", default=False)
        parser.add_argument("--threads", type=_nonzero_int, default=2)
        parser.add_argument("--exclude", "-e", action="append", default=[])
        parser.add_argument("pattern", nargs="?")
        namespace = parser.parse_args(argv)
        return cls(
            json=namespace.json,
            limit=namespace.limit,
            cwd=namespace.cwd,
            compute_indices=namespace.compute_indices,
            threads=namespace.threads,
            exclude=list(namespace.exclude),
            pattern=namespace.pattern,
        )


def _nonzero_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be non-zero")
    return parsed


__all__ = ["Cli"]

