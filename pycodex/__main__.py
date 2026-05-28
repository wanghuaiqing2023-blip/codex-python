"""Module entry point for ``python -m pycodex``."""

import sys

from .cli import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            stdin=getattr(sys.stdin, "buffer", sys.stdin),
            stdin_is_terminal=sys.stdin.isatty(),
        )
    )
