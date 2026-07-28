"""CLI port of ``codex-app-server-protocol/src/bin/export.rs``."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from ..export import (
    GenerateTsOptions,
    generate_json_with_experimental,
    generate_ts_with_options,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate TypeScript bindings and JSON Schemas for the Codex app-server protocol"
    )
    parser.add_argument("-o", "--out", required=True, type=Path, dest="out_dir")
    parser.add_argument("-p", "--prettier", type=Path)
    parser.add_argument("--experimental", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    options = GenerateTsOptions(experimental_api=args.experimental)
    generate_ts_with_options(args.out_dir, args.prettier, options)
    generate_json_with_experimental(args.out_dir, args.experimental)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

