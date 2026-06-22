"""Bazel runfiles lookup for the linux sandbox ``bwrap`` binary.

Port of ``codex/codex-rs/linux-sandbox/src/bazel_bwrap.rs``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath

BAZEL_BWRAP_ENV_VAR = "CARGO_BIN_EXE_bwrap"
RUNFILES_ENV_VARS = ("RUNFILES_DIR", "TEST_SRCDIR", "RUNFILES_MANIFEST_FILE")

PathExists = Callable[[Path], bool]


def candidate(
    env: Mapping[str, str] | None = None,
    *,
    debug_assertions: bool = True,
    bazel_package_present: bool | None = None,
    exists: PathExists | None = None,
) -> Path | None:
    """Return the Bazel-provided ``bwrap`` path when Rust would expose one.

    Rust gates this module with ``cfg(debug_assertions)`` and the compile-time
    ``option_env!("BAZEL_PACKAGE")``. Python has no equivalent compile-time
    environment, so callers may pass ``bazel_package_present`` explicitly; when
    omitted, ``BAZEL_PACKAGE`` in ``env`` is used as a practical test shim.
    """

    env = os.environ if env is None else env
    exists = _path_exists if exists is None else exists
    if not debug_assertions:
        return None
    if bazel_package_present is None:
        bazel_package_present = "BAZEL_PACKAGE" in env
    if not bazel_package_present or not runfiles_env_present(env):
        return None

    raw = env.get(BAZEL_BWRAP_ENV_VAR)
    if raw is None:
        return None
    if _is_absolute(raw):
        return Path(raw)
    return resolve_runfile(raw, env=env, exists=exists)


def runfiles_env_present(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return any(name in env for name in RUNFILES_ENV_VARS)


def resolve_runfile(
    logical_path: str,
    env: Mapping[str, str] | None = None,
    *,
    exists: PathExists | None = None,
) -> Path | None:
    env = os.environ if env is None else env
    exists = _path_exists if exists is None else exists
    logical_paths = [logical_path]
    workspace = env.get("TEST_WORKSPACE")
    if workspace:
        logical_paths.append(f"{workspace}/{logical_path}")

    for root_env in ("RUNFILES_DIR", "TEST_SRCDIR"):
        root = env.get(root_env)
        if root is None:
            continue
        root_path = Path(root)
        for item in logical_paths:
            candidate_path = root_path.joinpath(*_posix_parts(item))
            if exists(candidate_path):
                return candidate_path

    manifest = env.get("RUNFILES_MANIFEST_FILE")
    if manifest is None:
        return None
    try:
        lines = Path(manifest).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        key, sep, value = line.partition(" ")
        if sep and key in logical_paths:
            return Path(value)
    return None


def _is_absolute(raw: str) -> bool:
    return Path(raw).is_absolute() or raw.startswith("/")


def _path_exists(path: Path) -> bool:
    return path.exists()


def _posix_parts(value: str) -> tuple[str, ...]:
    return tuple(part for part in PurePosixPath(value).parts if part not in {"", "."})


__all__ = [
    "BAZEL_BWRAP_ENV_VAR",
    "RUNFILES_ENV_VARS",
    "candidate",
    "resolve_runfile",
    "runfiles_env_present",
]
