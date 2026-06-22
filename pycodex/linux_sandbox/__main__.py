"""Binary entrypoint for ``codex-linux-sandbox``.

Rust source: ``codex/codex-rs/linux-sandbox/src/main.rs``.
"""

from __future__ import annotations

from typing import NoReturn

from . import run_main


def main() -> NoReturn:
    """Delegate to the crate-root helper entrypoint."""

    return run_main()


if __name__ == "__main__":
    main()
