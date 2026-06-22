"""Bubblewrap launcher selection helpers.

Port of ``codex/codex-rs/linux-sandbox/src/launcher.rs``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence

from .exec_util import argv_to_cstrings, make_files_inheritable


@dataclass(frozen=True)
class SystemBwrapCapabilities:
    supports_argv0: bool
    supports_perms: bool


@dataclass(frozen=True)
class SystemBwrapLauncher:
    program: Path
    supports_argv0: bool


@dataclass(frozen=True)
class BundledBwrapLauncher:
    program: Path
    expected_sha256: bytes | None = None


class BubblewrapLauncherKind(str, Enum):
    SYSTEM = "system"
    BUNDLED = "bundled"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class BubblewrapLauncher:
    kind: BubblewrapLauncherKind
    system: SystemBwrapLauncher | None = None
    bundled: BundledBwrapLauncher | None = None

    @classmethod
    def system_launcher(cls, launcher: SystemBwrapLauncher) -> "BubblewrapLauncher":
        return cls(BubblewrapLauncherKind.SYSTEM, system=launcher)

    @classmethod
    def bundled_launcher(cls, launcher: BundledBwrapLauncher) -> "BubblewrapLauncher":
        return cls(BubblewrapLauncherKind.BUNDLED, bundled=launcher)

    @classmethod
    def unavailable(cls) -> "BubblewrapLauncher":
        return cls(BubblewrapLauncherKind.UNAVAILABLE)


CapabilitiesProbe = Callable[[Path], SystemBwrapCapabilities | None]
BundledLauncherProbe = Callable[[], BundledBwrapLauncher | None]


def exec_bwrap(argv: Sequence[str], preserved_files: Sequence[object] = ()) -> None:
    launcher = preferred_bwrap_launcher()
    if launcher.kind == BubblewrapLauncherKind.SYSTEM:
        if launcher.system is None:
            raise RuntimeError("system bubblewrap launcher missing program")
        exec_system_bwrap(launcher.system.program, argv, preserved_files)
    if launcher.kind == BubblewrapLauncherKind.BUNDLED:
        if launcher.bundled is None:
            raise RuntimeError("bundled bubblewrap launcher missing program")
        exec_system_bwrap(launcher.bundled.program, argv, preserved_files)
    raise RuntimeError(
        "bubblewrap is unavailable: no system bwrap was found on PATH and no bundled "
        "codex-resources/bwrap binary was found next to the Codex executable"
    )


def preferred_bwrap_launcher(
    *,
    system_bwrap_path: Path | str | None = None,
    bundled_launcher: BundledLauncherProbe | None = None,
    capabilities_probe: CapabilitiesProbe | None = None,
) -> BubblewrapLauncher:
    path = Path(system_bwrap_path) if system_bwrap_path is not None else find_system_bwrap_in_path()
    if path is not None:
        launcher = system_bwrap_launcher_for_path_with_probe(
            path,
            capabilities_probe or system_bwrap_capabilities,
        )
        if launcher is not None:
            return BubblewrapLauncher.system_launcher(launcher)

    if bundled_launcher is None:
        from . import bundled_bwrap

        bundled_launcher = bundled_bwrap.launcher
    bundled = bundled_launcher()
    if bundled is not None:
        bundled_program = getattr(bundled, "program", None)
        if isinstance(bundled, BundledBwrapLauncher):
            return BubblewrapLauncher.bundled_launcher(bundled)
        if bundled_program is not None:
            return BubblewrapLauncher.bundled_launcher(BundledBwrapLauncher(Path(bundled_program)))
    return BubblewrapLauncher.unavailable()


def preferred_bwrap_supports_argv0(
    launcher: BubblewrapLauncher | None = None,
    **preferred_kwargs: object,
) -> bool:
    launcher = preferred_bwrap_launcher(**preferred_kwargs) if launcher is None else launcher
    if launcher.kind == BubblewrapLauncherKind.SYSTEM:
        if launcher.system is None:
            raise RuntimeError("system bubblewrap launcher missing program")
        return launcher.system.supports_argv0
    return True


def system_bwrap_launcher_for_path(path: Path | str) -> SystemBwrapLauncher | None:
    return system_bwrap_launcher_for_path_with_probe(Path(path), system_bwrap_capabilities)


def system_bwrap_launcher_for_path_with_probe(
    path: Path | str,
    capabilities_probe: CapabilitiesProbe,
) -> SystemBwrapLauncher | None:
    system_bwrap_path = Path(path)
    if not system_bwrap_path.is_file():
        return None
    capabilities = capabilities_probe(system_bwrap_path)
    if capabilities is None or not capabilities.supports_perms:
        return None
    if not system_bwrap_path.is_absolute():
        raise RuntimeError(f"failed to normalize system bubblewrap path {system_bwrap_path}")
    return SystemBwrapLauncher(
        program=system_bwrap_path,
        supports_argv0=capabilities.supports_argv0,
    )


def system_bwrap_capabilities(path: Path | str) -> SystemBwrapCapabilities | None:
    try:
        output = subprocess.run(
            [str(path), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    combined = f"{output.stdout}\n{output.stderr}"
    return SystemBwrapCapabilities(
        supports_argv0="--argv0" in combined,
        supports_perms="--perms" in combined,
    )


def exec_system_bwrap(
    program: Path | str,
    argv: Sequence[str],
    preserved_files: Sequence[object] = (),
) -> None:
    make_files_inheritable(preserved_files)
    argv_to_cstrings(argv)
    try:
        os.execv(str(program), list(argv))
    except OSError as err:
        raise RuntimeError(f"failed to exec system bubblewrap {program}: {err}") from err


def find_system_bwrap_in_path() -> Path | None:
    found = shutil.which("bwrap")
    if found is None:
        return None
    return Path(found)


__all__ = [
    "BubblewrapLauncher",
    "BubblewrapLauncherKind",
    "BundledBwrapLauncher",
    "SystemBwrapCapabilities",
    "SystemBwrapLauncher",
    "exec_bwrap",
    "exec_system_bwrap",
    "find_system_bwrap_in_path",
    "preferred_bwrap_launcher",
    "preferred_bwrap_supports_argv0",
    "system_bwrap_capabilities",
    "system_bwrap_launcher_for_path",
    "system_bwrap_launcher_for_path_with_probe",
]
