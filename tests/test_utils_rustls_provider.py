from __future__ import annotations

from pycodex.utils.rustls_provider import (
    ensure_rustls_crypto_provider,
    reset_rustls_crypto_provider_for_tests,
    rustls_crypto_provider_installed,
)


def setup_function() -> None:
    reset_rustls_crypto_provider_for_tests()


def teardown_function() -> None:
    reset_rustls_crypto_provider_for_tests()


def test_provider_starts_uninstalled() -> None:
    # Source: codex/codex-rs/utils/rustls-provider/src/lib.rs
    # Contract: provider installation is process-wide and initially not observed in Python.
    assert not rustls_crypto_provider_installed()


def test_ensure_provider_marks_installed_without_installer() -> None:
    # Source: codex/codex-rs/utils/rustls-provider/src/lib.rs
    # Contract: ensure_rustls_crypto_provider completes successfully and records initialization.
    ensure_rustls_crypto_provider()

    assert rustls_crypto_provider_installed()


def test_installer_runs_only_once() -> None:
    # Source: codex/codex-rs/utils/rustls-provider/src/lib.rs
    # Contract: Rust uses Once::call_once, so the provider install closure runs once per process.
    calls: list[str] = []

    ensure_rustls_crypto_provider(lambda: calls.append("install"))
    ensure_rustls_crypto_provider(lambda: calls.append("install-again"))

    assert calls == ["install"]
    assert rustls_crypto_provider_installed()


def test_reset_test_helper_allows_reinitialization() -> None:
    # Source: codex/codex-rs/utils/rustls-provider/src/lib.rs
    # Python test support: reset makes the process-wide facade observable in focused tests.
    calls: list[str] = []
    ensure_rustls_crypto_provider(lambda: calls.append("first"))

    reset_rustls_crypto_provider_for_tests()
    ensure_rustls_crypto_provider(lambda: calls.append("second"))

    assert calls == ["first", "second"]
