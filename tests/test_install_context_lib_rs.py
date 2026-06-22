import os
from pathlib import Path

from pycodex.install_context import (
    BIN_DIRNAME,
    PACKAGE_METADATA_FILENAME,
    PATH_DIRNAME,
    RELEASES_DIRNAME,
    RESOURCES_DIRNAME,
    STANDALONE_PACKAGES_DIRNAME,
    ZSH_DIRNAME,
    CodexPackageLayout,
    InstallContext,
    InstallMethod,
    InstallMethodKind,
    StandalonePlatform,
)
from pycodex.utils.absolute_path import AbsolutePathBuf


TEST_RESOURCE_NAME = "codex-test-helper"


def _exe_name() -> str:
    return "codex.exe" if os.name == "nt" else "codex"


def _rg_name() -> str:
    return "rg.exe" if os.name == "nt" else "rg"


def _release_dir(codex_home: Path) -> Path:
    return codex_home / "packages" / STANDALONE_PACKAGES_DIRNAME / RELEASES_DIRNAME / "1.2.3-test"


def _abs(path: Path) -> AbsolutePathBuf:
    return AbsolutePathBuf.from_absolute_path_checked(path.resolve())


def test_detects_standalone_install_from_release_layout(tmp_path: Path) -> None:
    # Rust: install-context/src/lib.rs::tests::detects_standalone_install_from_release_layout.
    codex_home = tmp_path / "codex-home"
    release_dir = _release_dir(codex_home)
    resources_dir = release_dir / RESOURCES_DIRNAME
    resources_dir.mkdir(parents=True)
    exe_path = release_dir / _exe_name()
    exe_path.write_text("", encoding="utf-8")
    (resources_dir / _rg_name()).write_text("", encoding="utf-8")
    (resources_dir / TEST_RESOURCE_NAME).write_text("", encoding="utf-8")

    context = InstallContext.from_exe_with_codex_home(False, exe_path, False, False, codex_home)

    assert context == InstallContext(
        InstallMethod.Standalone(
            _abs(release_dir),
            _abs(resources_dir),
            StandalonePlatform.WINDOWS if os.name == "nt" else StandalonePlatform.UNIX,
        ),
        None,
    )
    assert context.bundled_resource(TEST_RESOURCE_NAME) == _abs(resources_dir / TEST_RESOURCE_NAME)


def test_standalone_rg_falls_back_when_resources_are_missing(tmp_path: Path) -> None:
    # Rust: standalone_rg_falls_back_when_resources_are_missing.
    codex_home = tmp_path / "codex-home"
    release_dir = _release_dir(codex_home)
    release_dir.mkdir(parents=True)
    exe_path = release_dir / _exe_name()
    exe_path.write_text("", encoding="utf-8")

    context = InstallContext.from_exe_with_codex_home(False, exe_path, False, False, codex_home)

    assert context.rg_command() == Path(_rg_name())


def test_detects_package_layout_independently_from_install_method(tmp_path: Path) -> None:
    # Rust: detects_package_layout_independently_from_install_method.
    package_dir = tmp_path / "package"
    bin_dir = package_dir / BIN_DIRNAME
    resources_dir = package_dir / RESOURCES_DIRNAME
    path_dir = package_dir / PATH_DIRNAME
    bin_dir.mkdir(parents=True)
    resources_dir.mkdir()
    path_dir.mkdir()
    (package_dir / PACKAGE_METADATA_FILENAME).write_text("{}", encoding="utf-8")
    exe_path = bin_dir / _exe_name()
    exe_path.write_text("", encoding="utf-8")
    (resources_dir / TEST_RESOURCE_NAME).write_text("", encoding="utf-8")
    (path_dir / _rg_name()).write_text("", encoding="utf-8")
    if os.name != "nt":
        zsh_path = resources_dir / ZSH_DIRNAME / BIN_DIRNAME / "zsh"
        zsh_path.parent.mkdir(parents=True)
        zsh_path.write_text("", encoding="utf-8")

    package_layout = CodexPackageLayout(
        package_dir=_abs(package_dir),
        bin_dir=_abs(bin_dir),
        resources_dir=_abs(resources_dir),
        path_dir=_abs(path_dir),
    )

    context = InstallContext.from_exe_with_codex_home(False, exe_path, False, False, None)

    assert context == InstallContext(InstallMethod.Other(), package_layout)
    assert context.rg_command() == (path_dir / _rg_name()).resolve()
    assert context.bundled_resource(TEST_RESOURCE_NAME) == _abs(resources_dir / TEST_RESOURCE_NAME)
    if os.name == "nt":
        assert context.bundled_zsh_path() is None
        assert context.bundled_zsh_bin_dir() is None
    else:
        assert context.bundled_zsh_path() == _abs(resources_dir / ZSH_DIRNAME / BIN_DIRNAME / "zsh")
        assert context.bundled_zsh_bin_dir() == _abs(resources_dir / ZSH_DIRNAME / BIN_DIRNAME)


def test_standalone_package_layout_keeps_standalone_install_method(tmp_path: Path) -> None:
    # Rust: standalone_package_layout_keeps_standalone_install_method.
    codex_home = tmp_path / "codex-home"
    package_dir = _release_dir(codex_home)
    bin_dir = package_dir / BIN_DIRNAME
    resources_dir = package_dir / RESOURCES_DIRNAME
    path_dir = package_dir / PATH_DIRNAME
    bin_dir.mkdir(parents=True)
    resources_dir.mkdir()
    path_dir.mkdir()
    (package_dir / PACKAGE_METADATA_FILENAME).write_text("{}", encoding="utf-8")
    exe_path = bin_dir / _exe_name()
    exe_path.write_text("", encoding="utf-8")
    (resources_dir / TEST_RESOURCE_NAME).write_text("", encoding="utf-8")
    (path_dir / _rg_name()).write_text("", encoding="utf-8")

    context = InstallContext.from_exe_with_codex_home(False, exe_path, False, False, codex_home)

    assert context.method == InstallMethod.Standalone(
        _abs(package_dir),
        _abs(resources_dir),
        StandalonePlatform.WINDOWS if os.name == "nt" else StandalonePlatform.UNIX,
    )
    assert context.package_layout == CodexPackageLayout(
        package_dir=_abs(package_dir),
        bin_dir=_abs(bin_dir),
        resources_dir=_abs(resources_dir),
        path_dir=_abs(path_dir),
    )
    assert context.rg_command() == (path_dir / _rg_name()).resolve()
    assert context.bundled_resource(TEST_RESOURCE_NAME) == _abs(resources_dir / TEST_RESOURCE_NAME)


def test_npm_managed_package_keeps_package_layout(tmp_path: Path) -> None:
    # Rust: npm_managed_package_keeps_package_layout.
    package_dir = tmp_path / "package"
    bin_dir = package_dir / BIN_DIRNAME
    path_dir = package_dir / PATH_DIRNAME
    bin_dir.mkdir(parents=True)
    path_dir.mkdir()
    (package_dir / PACKAGE_METADATA_FILENAME).write_text("{}", encoding="utf-8")
    exe_path = bin_dir / _exe_name()
    exe_path.write_text("", encoding="utf-8")
    (path_dir / _rg_name()).write_text("", encoding="utf-8")

    context = InstallContext.from_exe_with_codex_home(False, exe_path, True, False, None)

    assert context.method == InstallMethod.Npm()
    assert context.package_layout is not None
    assert context.rg_command() == (path_dir / _rg_name()).resolve()


def test_standalone_package_rg_falls_back_when_codex_path_is_missing(tmp_path: Path) -> None:
    # Rust: standalone_package_rg_falls_back_when_codex_path_is_missing.
    package_dir = tmp_path / "package"
    bin_dir = package_dir / BIN_DIRNAME
    bin_dir.mkdir(parents=True)
    (package_dir / PACKAGE_METADATA_FILENAME).write_text("{}", encoding="utf-8")
    exe_path = bin_dir / _exe_name()
    exe_path.write_text("", encoding="utf-8")

    context = InstallContext.from_exe_with_codex_home(False, exe_path, False, False, None)

    assert context.rg_command() == Path(_rg_name())


def test_bundled_file_lookups_ignore_directories(tmp_path: Path) -> None:
    # Rust: bundled_file_lookups_ignore_directories.
    package_dir = tmp_path / "package"
    bin_dir = package_dir / BIN_DIRNAME
    resources_dir = package_dir / RESOURCES_DIRNAME
    path_dir = package_dir / PATH_DIRNAME
    bin_dir.mkdir(parents=True)
    (resources_dir / TEST_RESOURCE_NAME).mkdir(parents=True)
    (path_dir / _rg_name()).mkdir(parents=True)
    (package_dir / PACKAGE_METADATA_FILENAME).write_text("{}", encoding="utf-8")
    exe_path = bin_dir / _exe_name()
    exe_path.write_text("", encoding="utf-8")

    context = InstallContext.from_exe_with_codex_home(False, exe_path, False, False, None)

    assert context.rg_command() == Path(_rg_name())
    assert context.bundled_resource(TEST_RESOURCE_NAME) is None


def test_npm_and_bun_take_precedence() -> None:
    # Rust: npm_and_bun_take_precedence.
    npm_context = InstallContext.from_exe_with_codex_home(False, Path("/tmp/codex"), True, False, None)
    assert npm_context == InstallContext(InstallMethod.Npm(), None)

    bun_context = InstallContext.from_exe_with_codex_home(False, Path("/tmp/codex"), False, True, None)
    assert bun_context == InstallContext(InstallMethod.Bun(), None)


def test_brew_is_detected_on_macos_prefixes() -> None:
    # Rust: brew_is_detected_on_macos_prefixes.
    context = InstallContext.from_exe_with_codex_home(
        True,
        Path("/opt/homebrew/bin/codex"),
        False,
        False,
        None,
    )

    assert context == InstallContext(InstallMethod.Brew(), None)


def test_public_constants_match_rust_layout_names() -> None:
    assert BIN_DIRNAME == "bin"
    assert PACKAGE_METADATA_FILENAME == "codex-package.json"
    assert PATH_DIRNAME == "codex-path"
    assert RELEASES_DIRNAME == "releases"
    assert RESOURCES_DIRNAME == "codex-resources"
    assert STANDALONE_PACKAGES_DIRNAME == "standalone"
    assert ZSH_DIRNAME == "zsh"
