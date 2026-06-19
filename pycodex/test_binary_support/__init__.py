"""Test-binary dispatch helpers ported from ``codex-rs/test-binary-support``."""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from pycodex.arg0 import Arg0DispatchPaths, Arg0PathEntryGuard, arg0_dispatch


class TestBinaryDispatchMode(Enum):
    __test__ = False

    DISPATCH_ARG0_ONLY = "DispatchArg0Only"
    SKIP = "Skip"
    INSTALL_ALIASES = "InstallAliases"


@dataclass
class TestBinaryDispatchGuard:
    __test__ = False

    _codex_home: tempfile.TemporaryDirectory[str]
    arg0: Arg0PathEntryGuard
    _previous_codex_home: str | None

    @property
    def paths(self) -> Arg0DispatchPaths:
        return self.arg0.paths

    def close(self) -> None:
        try:
            self.arg0.close()
        finally:
            self._codex_home.cleanup()

    def __enter__(self) -> "TestBinaryDispatchGuard":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


Classifier = Callable[[str, str | None], TestBinaryDispatchMode]


def configure_test_binary_dispatch(
    codex_home_prefix: str,
    classify: Classifier,
    *,
    argv: list[str] | None = None,
    handlers: dict[str, object] | None = None,
    current_exe: str | Path | None = None,
) -> TestBinaryDispatchGuard | None:
    if not isinstance(codex_home_prefix, str):
        raise TypeError("codex_home_prefix must be a string")

    argv = list(sys.argv if argv is None else argv)
    argv0 = argv[0] if argv else ""
    exe_name = Path(argv0).name
    argv1 = argv[1] if len(argv) > 1 else None

    mode = classify(exe_name, argv1)
    if not isinstance(mode, TestBinaryDispatchMode):
        raise TypeError("classify must return TestBinaryDispatchMode")

    if mode is TestBinaryDispatchMode.DISPATCH_ARG0_ONLY:
        guard = arg0_dispatch(
            argv=argv,
            handlers=handlers,
            codex_home=None,
            current_exe=current_exe,
        )
        if guard is not None:
            guard.close()
        return None

    if mode is TestBinaryDispatchMode.SKIP:
        return None

    codex_home = tempfile.TemporaryDirectory(prefix=codex_home_prefix)
    previous_codex_home = os.environ.get("CODEX_HOME")
    os.environ["CODEX_HOME"] = codex_home.name
    try:
        arg0 = arg0_dispatch(
            argv=argv,
            handlers=handlers,
            codex_home=codex_home.name,
            current_exe=current_exe,
        )
        if arg0 is None:
            raise RuntimeError("failed to configure arg0 dispatch aliases for test binary")
    finally:
        if previous_codex_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = previous_codex_home

    return TestBinaryDispatchGuard(codex_home, arg0, previous_codex_home)


__all__ = [
    "TestBinaryDispatchGuard",
    "TestBinaryDispatchMode",
    "configure_test_binary_dispatch",
]
