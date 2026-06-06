"""Path helpers ported from ``codex-utils-path-utils``."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Mapping


@dataclass(frozen=True)
class SymlinkWritePaths:
    read_path: Path | None
    write_path: Path

    def __post_init__(self) -> None:
        if self.read_path is not None and not isinstance(self.read_path, Path):
            object.__setattr__(self, "read_path", Path(self.read_path))
        if not isinstance(self.write_path, Path):
            object.__setattr__(self, "write_path", Path(self.write_path))


def is_wsl(
    *,
    env: Mapping[str, str] | None = None,
    proc_version_path: str | Path = "/proc/version",
    platform: str | None = None,
) -> bool:
    if platform is None:
        platform = sys.platform
    if not str(platform).startswith("linux"):
        return False
    if env is None:
        env = os.environ
    if "WSL_DISTRO_NAME" in env:
        return True
    try:
        version = Path(proc_version_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "microsoft" in version.lower()


def normalize_for_path_comparison(path: str | Path) -> Path:
    return normalize_for_wsl(Path(path).resolve(strict=True))


def paths_match_after_normalization(left: str | Path, right: str | Path) -> bool:
    left_path = Path(left)
    right_path = Path(right)
    try:
        return normalize_for_path_comparison(left_path) == normalize_for_path_comparison(right_path)
    except OSError:
        return left_path == right_path


def normalize_for_native_workdir(path: str | Path) -> Path:
    return normalize_for_native_workdir_with_flag(Path(path), os.name == "nt")


def normalize_for_native_workdir_with_flag(path: str | Path, is_windows: bool) -> Path:
    result = Path(path)
    if not is_windows:
        return result
    text = str(result)
    if text.startswith("\\\\?\\UNC\\") or text.startswith("\\\\.\\UNC\\"):
        return Path("\\\\" + text[8:])
    if text.startswith("\\\\?\\") or text.startswith("\\\\.\\"):
        return Path(text[4:])
    return result


def normalize_for_wsl(path: str | Path) -> Path:
    return normalize_for_wsl_with_flag(Path(path), is_wsl())


def normalize_for_wsl_with_flag(
    path: str | Path,
    is_wsl_value: bool,
    *,
    is_linux: bool | None = None,
) -> Path:
    result = Path(path)
    if is_linux is None:
        is_linux = sys.platform.startswith("linux")
    if not is_wsl_value or not is_linux:
        return result
    if not _is_wsl_case_insensitive_path(result):
        return result
    return Path(_lower_ascii(str(result)))


def resolve_symlink_write_paths(path: str | Path) -> SymlinkWritePaths:
    root = Path(path)
    current = root
    visited: set[Path] = set()

    while True:
        try:
            stat_result = os.lstat(current)
        except FileNotFoundError:
            return SymlinkWritePaths(read_path=current, write_path=current)
        except OSError:
            return SymlinkWritePaths(read_path=None, write_path=root)

        if not _is_symlink_stat(stat_result):
            return SymlinkWritePaths(read_path=current, write_path=current)

        if current in visited:
            return SymlinkWritePaths(read_path=None, write_path=root)
        visited.add(current)

        try:
            target = Path(os.readlink(current))
        except OSError:
            return SymlinkWritePaths(read_path=None, write_path=root)

        if target.is_absolute():
            current = Path(os.path.normpath(str(target)))
            continue
        parent = current.parent
        if not str(parent):
            return SymlinkWritePaths(read_path=None, write_path=root)
        current = Path(os.path.normpath(str(parent / target)))


def write_atomically(write_path: str | Path, contents: str) -> None:
    path = Path(write_path)
    parent = path.parent
    if not str(parent):
        raise OSError(f"path {path} has no parent directory")
    parent.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=parent, delete=False) as tmp:
            tmp_name = tmp.name
            tmp.write(contents)
        os.replace(tmp_name, path)
        tmp_name = None
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def _is_symlink_stat(stat_result: os.stat_result) -> bool:
    return stat.S_ISLNK(stat_result.st_mode)


def _is_wsl_case_insensitive_path(path: Path) -> bool:
    parts = path.as_posix().split("/")
    return (
        len(parts) >= 4
        and parts[0] == ""
        and parts[1].lower() == "mnt"
        and len(parts[2]) == 1
        and parts[2].isascii()
        and parts[2].isalpha()
    )


def _lower_ascii(value: str) -> str:
    return "".join(character.lower() if character.isascii() else character for character in value)


__all__ = [
    "SymlinkWritePaths",
    "is_wsl",
    "normalize_for_native_workdir",
    "normalize_for_native_workdir_with_flag",
    "normalize_for_path_comparison",
    "normalize_for_wsl",
    "normalize_for_wsl_with_flag",
    "paths_match_after_normalization",
    "resolve_symlink_write_paths",
    "write_atomically",
]
