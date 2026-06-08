"""Bin target ported from ``codex-core::bin::config_schema``."""

from __future__ import annotations

import argparse
from pathlib import Path
from collections.abc import Sequence

from pycodex.config.schema import write_config_schema


COMMAND_NAME = "codex-write-config-schema"


def default_output_path() -> Path:
    """Return the upstream core crate config schema fixture path."""

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "codex" / "codex-rs" / "core" / "config.schema.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("codex/codex-rs/core/config.schema.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=COMMAND_NAME,
        description="Generate the JSON Schema for config.toml and write it to config.schema.json.",
    )
    parser.add_argument("-o", "--out", metavar="PATH", type=Path)
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def run(argv: Sequence[str] | None = None) -> Path:
    args = parse_args(argv)
    out_path = args.out if args.out is not None else default_output_path()
    write_config_schema(out_path)
    return out_path


def main(argv: Sequence[str] | None = None) -> int:
    run(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "COMMAND_NAME",
    "build_parser",
    "default_output_path",
    "main",
    "parse_args",
    "run",
]
