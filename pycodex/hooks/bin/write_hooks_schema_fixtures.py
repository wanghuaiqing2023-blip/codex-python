"""Python port of ``write_hooks_schema_fixtures.rs``."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

from ..schema import write_schema_fixtures


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        raise SystemExit("usage: write_hooks_schema_fixtures <schema-root>")
    write_schema_fixtures(Path(args[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
