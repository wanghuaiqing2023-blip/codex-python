from pathlib import Path

from pycodex.linux_sandbox import launcher


def test_prefers_system_bwrap_when_help_lists_argv0(tmp_path: Path) -> None:
    # Rust source: launcher.rs prefers a system bwrap that supports --perms
    # and records whether --argv0 is supported.
    fake_bwrap = tmp_path / "bwrap"
    fake_bwrap.write_text("#!/bin/sh\n", encoding="utf-8")

    result = launcher.system_bwrap_launcher_for_path_with_probe(
        fake_bwrap,
        lambda _path: launcher.SystemBwrapCapabilities(
            supports_argv0=True,
            supports_perms=True,
        ),
    )

    assert result == launcher.SystemBwrapLauncher(fake_bwrap, supports_argv0=True)


def test_prefers_system_bwrap_when_system_bwrap_lacks_argv0(tmp_path: Path) -> None:
    # Rust source: --argv0 support is optional for accepting a system bwrap.
    fake_bwrap = tmp_path / "bwrap"
    fake_bwrap.write_text("#!/bin/sh\n", encoding="utf-8")

    result = launcher.system_bwrap_launcher_for_path_with_probe(
        fake_bwrap,
        lambda _path: launcher.SystemBwrapCapabilities(
            supports_argv0=False,
            supports_perms=True,
        ),
    )

    assert result == launcher.SystemBwrapLauncher(fake_bwrap, supports_argv0=False)


def test_ignores_system_bwrap_when_system_bwrap_lacks_perms(tmp_path: Path) -> None:
    # Rust source: a system bwrap without --perms is ignored.
    fake_bwrap = tmp_path / "bwrap"
    fake_bwrap.write_text("#!/bin/sh\n", encoding="utf-8")

    assert (
        launcher.system_bwrap_launcher_for_path_with_probe(
            fake_bwrap,
            lambda _path: launcher.SystemBwrapCapabilities(
                supports_argv0=False,
                supports_perms=False,
            ),
        )
        is None
    )


def test_ignores_system_bwrap_when_system_bwrap_is_missing() -> None:
    # Rust source: missing system bwrap paths are ignored.
    assert launcher.system_bwrap_launcher_for_path(Path("/definitely/not/a/bwrap")) is None


def test_preferred_bwrap_supports_argv0_defaults_true_for_unavailable() -> None:
    # Rust source: bundled and unavailable launchers report argv0 support true.
    assert launcher.preferred_bwrap_supports_argv0(launcher.BubblewrapLauncher.unavailable()) is True
