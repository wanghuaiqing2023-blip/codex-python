"""CLI port of ``codex-app-server-protocol/src/bin/write_schema_fixtures.rs``."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from ..schema_fixtures import SchemaFixtureOptions, write_schema_fixtures_with_options


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Regenerate vendored app-server schema fixtures")
    parser.add_argument("--schema-root", type=Path)
    parser.add_argument("-p", "--prettier", type=Path)
    parser.add_argument("--experimental", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    schema_root = args.schema_root
    if schema_root is None:
        schema_root = Path(__file__).resolve().parents[3] / "codex" / "codex-rs" / "app-server-protocol" / "schema"
    write_schema_fixtures_with_options(
        schema_root,
        args.prettier,
        SchemaFixtureOptions(experimental_api=args.experimental),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

