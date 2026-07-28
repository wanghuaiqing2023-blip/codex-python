"""Test path helpers from ``codex-utils-absolute-path::test_support``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import AbsolutePathBuf


@dataclass(frozen=True)
class TestPathBuf:
    path: Path

    def abs(self) -> AbsolutePathBuf:
        return AbsolutePathBuf.from_absolute_path_checked(self.path)

    def display(self) -> str:
        return str(self.path)

    def __fspath__(self) -> str:
        return str(self.path)

    def __str__(self) -> str:
        return str(self.path)


TestPathBuf.__test__ = False


class PathExt:
    @staticmethod
    def abs(path: str | Path | TestPathBuf) -> AbsolutePathBuf:
        value = path.path if isinstance(path, TestPathBuf) else Path(path)
        return AbsolutePathBuf.from_absolute_path_checked(value)


class PathBufExt(PathExt):
    pass


def test_path_buf(unix_path: str) -> TestPathBuf:
    if os.name == "nt":
        drive = Path.cwd().drive or "C:"
        segments = [part for part in unix_path.lstrip("/").split("/") if part]
        return TestPathBuf(Path(f"{drive}\\", *segments))
    return TestPathBuf(Path(unix_path))


test_path_buf.__test__ = False


__all__ = ["PathBufExt", "PathExt", "TestPathBuf", "test_path_buf"]
