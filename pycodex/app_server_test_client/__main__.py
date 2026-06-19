"""Port of Rust ``codex-app-server-test-client/src/main.rs``."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from . import run

T = TypeVar("T")


def main(run_callable: Callable[[], Awaitable[T]] = run) -> T:
    return asyncio.run(run_callable())


if __name__ == "__main__":
    main()
