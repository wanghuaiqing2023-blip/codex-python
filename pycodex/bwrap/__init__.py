"""Python port of Rust ``codex-bwrap`` binary entry module.

Rust source:
- ``codex/codex-rs/bwrap/src/main.rs``
"""

from __future__ import annotations

import platform
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import NoReturn


BWRAP_UNAVAILABLE_MESSAGE = """bubblewrap is not available in this build.
Notes:
- ensure the target OS is Linux
- libcap headers must be available via pkg-config
- bubblewrap sources expected at codex-rs/vendor/bubblewrap (default)"""

NON_LINUX_MESSAGE = "bwrap is only supported on Linux"


@dataclass(frozen=True)
class BwrapMainPlan:
    """Testable plan for the Rust cfg-gated ``main`` branches."""

    branch: str
    argv: tuple[str | bytes, ...]
    message: str | None = None


def build_bwrap_main_plan(
    argv: Iterable[str | bytes] | None = None,
    *,
    target_os: str | None = None,
    bwrap_available: bool = False,
) -> BwrapMainPlan:
    """Return the Rust ``src/main.rs`` branch selected by cfg flags."""

    target = (target_os or platform.system()).lower()
    argv_tuple = tuple(sys.argv if argv is None else argv)
    if target != "linux":
        return BwrapMainPlan("unsupported_os", argv_tuple, NON_LINUX_MESSAGE)
    if not bwrap_available:
        return BwrapMainPlan("unavailable", argv_tuple, BWRAP_UNAVAILABLE_MESSAGE)
    _validate_argv_for_cstring(argv_tuple)
    return BwrapMainPlan("call_bwrap_main", argv_tuple, None)


def run_bwrap_main(
    argv: Iterable[str | bytes] | None = None,
    *,
    target_os: str | None = None,
    bwrap_available: bool = False,
    runner: Callable[[tuple[str | bytes, ...]], int] | None = None,
) -> int:
    """Execute the selected branch and return the Rust-equivalent exit code."""

    plan = build_bwrap_main_plan(argv, target_os=target_os, bwrap_available=bwrap_available)
    if plan.branch == "unsupported_os":
        _panic(plan.message or NON_LINUX_MESSAGE)
    if plan.branch == "unavailable":
        _panic(plan.message or BWRAP_UNAVAILABLE_MESSAGE)
    if runner is None:
        _panic("bwrap_main runner is not available")
    return int(runner(plan.argv))


def _validate_argv_for_cstring(argv: Iterable[str | bytes]) -> None:
    for arg in argv:
        raw = arg if isinstance(arg, bytes) else arg.encode(errors="surrogateescape")
        if b"\x00" in raw:
            _panic("failed to convert argv to CString: nul byte found in provided data")


def _panic(message: str) -> NoReturn:
    raise RuntimeError(message)


__all__ = [
    "BWRAP_UNAVAILABLE_MESSAGE",
    "BwrapMainPlan",
    "NON_LINUX_MESSAGE",
    "build_bwrap_main_plan",
    "run_bwrap_main",
]
