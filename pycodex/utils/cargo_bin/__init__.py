"""Cargo/Bazel test binary and resource helpers.

Port of ``codex-rs/utils/cargo-bin`` using Python standard-library path and
environment handling.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

RUNFILES_MANIFEST_ONLY_ENV = "RUNFILES_MANIFEST_ONLY"


class CargoBinError(Exception):
    pass


class CurrentExeError(CargoBinError):
    def __init__(self, source: BaseException) -> None:
        self.source = source
        super().__init__("failed to read current exe")


class CurrentDirError(CargoBinError):
    def __init__(self, source: BaseException) -> None:
        self.source = source
        super().__init__("failed to read current directory")


class ResolvedPathDoesNotExistError(CargoBinError):
    def __init__(self, key: str, path: Path | str) -> None:
        self.key = key
        self.path = Path(path)
        super().__init__(f"CARGO_BIN_EXE env var {key} resolved to {self.path!r}, but it does not exist")


class CargoBinNotFoundError(CargoBinError):
    def __init__(self, name: str, env_keys: list[str], fallback: str) -> None:
        self.name = name
        self.env_keys = env_keys
        self.fallback = fallback
        super().__init__(f"could not locate binary {name!r}; tried env vars {env_keys!r}; {fallback}")


@dataclass(frozen=True)
class RunfileResolver:
    root: Path

    def rlocation(self, path: Path | str) -> Path | None:
        candidate = Path(path)
        if candidate.is_absolute() and candidate.exists():
            return candidate
        resolved = self.root / candidate
        return resolved if resolved.exists() else None


def cargo_bin(name: str) -> Path:
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    env_keys = cargo_bin_env_keys(name)
    for key in env_keys:
        value = os.environ.get(key)
        if value is not None:
            return resolve_bin_from_env(key, value)
    fallback = shutil.which(name)
    if fallback is not None:
        path = Path(fallback)
        return path if path.is_absolute() else Path.cwd() / path
    raise CargoBinNotFoundError(name, env_keys, "PATH lookup failed")


def cargo_bin_env_keys(name: str) -> list[str]:
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    keys = [f"CARGO_BIN_EXE_{name}"]
    underscore = name.replace("-", "_")
    if underscore != name:
        keys.append(f"CARGO_BIN_EXE_{underscore}")
    return keys


def runfiles_available() -> bool:
    return os.environ.get(RUNFILES_MANIFEST_ONLY_ENV) is not None


def resolve_bin_from_env(key: str, value: str | os.PathLike[str]) -> Path:
    raw = Path(value)
    if runfiles_available():
        resolved = _resolve_runfile(raw)
        if resolved is not None:
            return resolved if resolved.is_absolute() else Path.cwd() / resolved
    elif raw.is_absolute() and raw.exists():
        return raw
    raise ResolvedPathDoesNotExistError(key, raw)


def resolve_bazel_runfile(bazel_package: str | None, resource: Path | str) -> Path:
    if bazel_package is None:
        raise FileNotFoundError("BAZEL_PACKAGE was not set at compile time")
    runfile_path = normalize_runfile_path(Path("_main") / bazel_package / Path(resource))
    resolved = _resolve_runfile(runfile_path)
    if resolved is not None and resolved.exists():
        return resolved
    raise FileNotFoundError(f"runfile does not exist at: {runfile_path}")


def resolve_cargo_runfile(resource: Path | str, manifest_dir: Path | str | None = None) -> Path:
    base = Path(manifest_dir) if manifest_dir is not None else Path(os.environ.get("CARGO_MANIFEST_DIR", Path.cwd()))
    return base / Path(resource)


def find_resource(resource: Path | str, bazel_package: str | None = None, manifest_dir: Path | str | None = None) -> Path:
    if runfiles_available():
        return resolve_bazel_runfile(bazel_package, resource)
    return resolve_cargo_runfile(resource, manifest_dir)


def repo_root(marker: Path | str | None = None) -> Path:
    if marker is None:
        if runfiles_available():
            marker_env = os.environ.get("CODEX_REPO_ROOT_MARKER")
            if marker_env is None:
                raise FileNotFoundError("CODEX_REPO_ROOT_MARKER was not set at compile time")
            resolved = _resolve_runfile(Path(marker_env))
            if resolved is None:
                raise FileNotFoundError("repo_root.marker not available in runfiles")
            marker_path = resolved
        else:
            marker_path = resolve_cargo_runfile("repo_root.marker")
    else:
        marker_path = Path(marker)
    root = marker_path
    for _ in range(4):
        parent = root.parent
        if parent == root:
            raise FileNotFoundError("repo_root.marker did not have expected parent depth")
        root = parent
    return root


def normalize_runfile_path(path: Path | str) -> Path:
    parts: list[str] = []
    for part in Path(path).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            else:
                parts.append(part)
        else:
            parts.append(part)
    return Path(*parts) if parts else Path()


def _resolve_runfile(path: Path) -> Path | None:
    roots = [
        os.environ.get("RUNFILES_DIR"),
        os.environ.get("TEST_SRCDIR"),
        os.environ.get("RUNFILES_MANIFEST_FILE"),
    ]
    for root_value in roots:
        if not root_value:
            continue
        root = Path(root_value)
        if root.is_file():
            resolved = _resolve_manifest_runfile(root, path)
        else:
            resolved = root / path
        if resolved is not None and resolved.exists():
            return resolved
    return path if path.is_absolute() and path.exists() else None


def _resolve_manifest_runfile(manifest: Path, path: Path) -> Path | None:
    target = str(path).replace("\\", "/")
    try:
        for line in manifest.read_text(encoding="utf-8", errors="replace").splitlines():
            key, sep, value = line.partition(" ")
            if sep and key == target:
                return Path(value)
    except OSError:
        return None
    return None


__all__ = [
    "CargoBinError",
    "CargoBinNotFoundError",
    "CurrentDirError",
    "CurrentExeError",
    "RUNFILES_MANIFEST_ONLY_ENV",
    "ResolvedPathDoesNotExistError",
    "RunfileResolver",
    "cargo_bin",
    "cargo_bin_env_keys",
    "find_resource",
    "normalize_runfile_path",
    "repo_root",
    "resolve_bazel_runfile",
    "resolve_bin_from_env",
    "resolve_cargo_runfile",
    "runfiles_available",
]
