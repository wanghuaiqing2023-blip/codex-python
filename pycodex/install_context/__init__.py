"""Python port of ``codex-install-context`` public API.

Rust source:
- ``codex/codex-rs/install-context/src/lib.rs``
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pycodex.utils.absolute_path import AbsolutePathBuf
from pycodex.utils.home_dir import find_codex_home

BIN_DIRNAME = "bin"
PACKAGE_METADATA_FILENAME = "codex-package.json"
PATH_DIRNAME = "codex-path"
RELEASES_DIRNAME = "releases"
RESOURCES_DIRNAME = "codex-resources"
STANDALONE_PACKAGES_DIRNAME = "standalone"
ZSH_DIRNAME = "zsh"


class StandalonePlatform(str, Enum):
    UNIX = "unix"
    WINDOWS = "windows"


class InstallMethodKind(str, Enum):
    STANDALONE = "standalone"
    NPM = "npm"
    BUN = "bun"
    BREW = "brew"
    OTHER = "other"


@dataclass(frozen=True)
class InstallMethod:
    kind: InstallMethodKind
    release_dir: AbsolutePathBuf | None = None
    resources_dir: AbsolutePathBuf | None = None
    platform: StandalonePlatform | None = None

    @classmethod
    def Standalone(
        cls,
        release_dir: AbsolutePathBuf,
        resources_dir: AbsolutePathBuf | None,
        platform: StandalonePlatform,
    ) -> "InstallMethod":
        return cls(InstallMethodKind.STANDALONE, release_dir, resources_dir, platform)

    @classmethod
    def Npm(cls) -> "InstallMethod":
        return cls(InstallMethodKind.NPM)

    @classmethod
    def Bun(cls) -> "InstallMethod":
        return cls(InstallMethodKind.BUN)

    @classmethod
    def Brew(cls) -> "InstallMethod":
        return cls(InstallMethodKind.BREW)

    @classmethod
    def Other(cls) -> "InstallMethod":
        return cls(InstallMethodKind.OTHER)


@dataclass(frozen=True)
class CodexPackageLayout:
    package_dir: AbsolutePathBuf
    bin_dir: AbsolutePathBuf
    resources_dir: AbsolutePathBuf | None
    path_dir: AbsolutePathBuf | None

    @classmethod
    def from_exe(cls, exe_path: str | os.PathLike[str]) -> "CodexPackageLayout | None":
        canonical_exe = _canonical_absolute_path(exe_path)
        if canonical_exe is None:
            return None
        bin_dir_path = canonical_exe.as_path().parent
        if bin_dir_path.name != BIN_DIRNAME:
            return None
        package_dir_path = bin_dir_path.parent
        if not (package_dir_path / PACKAGE_METADATA_FILENAME).is_file():
            return None
        package_dir = AbsolutePathBuf.from_absolute_path_checked(package_dir_path)
        return cls(
            package_dir=package_dir,
            bin_dir=AbsolutePathBuf.from_absolute_path_checked(bin_dir_path),
            resources_dir=_existing_dir(package_dir.join(RESOURCES_DIRNAME)),
            path_dir=_existing_dir(package_dir.join(PATH_DIRNAME)),
        )


@dataclass(frozen=True)
class InstallContext:
    method: InstallMethod
    package_layout: CodexPackageLayout | None = None

    @classmethod
    def from_exe(
        cls,
        is_macos: bool,
        current_exe: str | os.PathLike[str] | None,
        managed_by_npm: bool,
        managed_by_bun: bool,
    ) -> "InstallContext":
        try:
            codex_home = find_codex_home()
        except (FileNotFoundError, NotADirectoryError):
            codex_home = None
        return cls.from_exe_with_codex_home(
            is_macos,
            current_exe,
            managed_by_npm,
            managed_by_bun,
            codex_home,
        )

    @classmethod
    def from_exe_with_codex_home(
        cls,
        is_macos: bool,
        current_exe: str | os.PathLike[str] | None,
        managed_by_npm: bool,
        managed_by_bun: bool,
        codex_home: str | os.PathLike[str] | None,
    ) -> "InstallContext":
        package_layout = CodexPackageLayout.from_exe(current_exe) if current_exe is not None else None
        if managed_by_npm:
            method = InstallMethod.Npm()
        elif managed_by_bun:
            method = InstallMethod.Bun()
        elif current_exe is not None:
            method = _install_method_from_exe(Path(current_exe), codex_home, package_layout, is_macos)
        else:
            method = InstallMethod.Other()
        return cls(method, package_layout)

    @classmethod
    def current(cls) -> "InstallContext":
        return cls.from_exe(
            sys.platform == "darwin",
            Path(sys.executable),
            "CODEX_MANAGED_BY_NPM" in os.environ,
            "CODEX_MANAGED_BY_BUN" in os.environ,
        )

    def rg_command(self) -> Path:
        if self.package_layout is not None and self.package_layout.path_dir is not None:
            bundled_rg = self.package_layout.path_dir.join(_default_rg_command())
            if bundled_rg.as_path().is_file():
                return bundled_rg.into_path_buf()

        if self.method.kind == InstallMethodKind.STANDALONE and self.method.resources_dir is not None:
            bundled_rg = self.method.resources_dir.join(_default_rg_command())
            if bundled_rg.as_path().is_file():
                return bundled_rg.into_path_buf()

        return _default_rg_command()

    def bundled_resource(self, file_name: str | os.PathLike[str]) -> AbsolutePathBuf | None:
        if self.package_layout is not None and self.package_layout.resources_dir is not None:
            resource = self.package_layout.resources_dir.join(file_name)
            if resource.as_path().is_file():
                return resource
        if self.method.kind == InstallMethodKind.STANDALONE and self.method.resources_dir is not None:
            resource = self.method.resources_dir.join(file_name)
            if resource.as_path().is_file():
                return resource
        return None

    def bundled_zsh_path(self) -> AbsolutePathBuf | None:
        if os.name == "nt":
            return None
        return self.bundled_resource(_zsh_resource_path())

    def bundled_zsh_bin_dir(self) -> AbsolutePathBuf | None:
        path = self.bundled_zsh_path()
        return path.parent() if path is not None else None


def _install_method_from_exe(
    exe_path: Path,
    codex_home: str | os.PathLike[str] | None,
    package_layout: CodexPackageLayout | None,
    is_macos: bool,
) -> InstallMethod:
    standalone = _standalone_install_method(exe_path, codex_home, package_layout)
    if standalone is not None:
        return standalone
    exe_text = str(exe_path).replace("\\", "/")
    if is_macos and (exe_text.startswith("/opt/homebrew") or exe_text.startswith("/usr/local")):
        return InstallMethod.Brew()
    return InstallMethod.Other()


def _standalone_install_method(
    exe_path: Path,
    codex_home: str | os.PathLike[str] | None,
    package_layout: CodexPackageLayout | None,
) -> InstallMethod | None:
    if codex_home is None:
        return None
    canonical_codex_home = _canonical_absolute_path(codex_home)
    if canonical_codex_home is None:
        return None
    if package_layout is not None:
        release_dir = package_layout.package_dir
    else:
        canonical_exe = _canonical_absolute_path(exe_path)
        if canonical_exe is None:
            return None
        release_parent = canonical_exe.as_path().parent
        release_dir = AbsolutePathBuf.from_absolute_path_checked(release_parent)

    releases_root = canonical_codex_home.join("packages").join(STANDALONE_PACKAGES_DIRNAME).join(RELEASES_DIRNAME)
    try:
        release_dir.as_path().relative_to(releases_root.as_path())
    except ValueError:
        return None
    resources_dir = release_dir.join(RESOURCES_DIRNAME)
    return InstallMethod.Standalone(
        release_dir,
        resources_dir if resources_dir.as_path().is_dir() else None,
        _standalone_platform(),
    )


def _canonical_absolute_path(path: str | os.PathLike[str]) -> AbsolutePathBuf | None:
    try:
        return AbsolutePathBuf.from_absolute_path_checked(Path(path).resolve(strict=True))
    except (OSError, ValueError):
        return None


def _existing_dir(path: AbsolutePathBuf) -> AbsolutePathBuf | None:
    return path if path.as_path().is_dir() else None


def _standalone_platform() -> StandalonePlatform:
    return StandalonePlatform.WINDOWS if os.name == "nt" else StandalonePlatform.UNIX


def _default_rg_command() -> Path:
    return Path("rg.exe" if os.name == "nt" else "rg")


def _zsh_resource_path() -> Path:
    return Path(ZSH_DIRNAME) / BIN_DIRNAME / "zsh"


__all__ = [
    "CodexPackageLayout",
    "InstallContext",
    "InstallMethod",
    "InstallMethodKind",
    "StandalonePlatform",
]
