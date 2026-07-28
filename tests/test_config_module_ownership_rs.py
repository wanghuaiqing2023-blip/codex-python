"""Rust-derived module ownership tests for ``codex-config`` child modules."""

from __future__ import annotations

import pytest


def test_loader_layer_io_symbols_have_rust_aligned_owner() -> None:
    # Rust: codex-config/src/loader/mod.rs declares private child module layer_io.
    from pycodex.config.loader.layer_io import LoadedConfigLayers
    from pycodex.config.loader.layer_io import ManagedConfigFromFile
    from pycodex.config.loader.layer_io import ManagedConfigFromMdm
    from pycodex.config.loader.layer_io import load_config_layers_internal
    from pycodex.config.loader.layer_io import managed_config_default_path
    from pycodex.config.loader.layer_io import read_config_from_path

    for item in (
        LoadedConfigLayers,
        ManagedConfigFromFile,
        ManagedConfigFromMdm,
        load_config_layers_internal,
        managed_config_default_path,
        read_config_from_path,
    ):
        assert item.__module__ == "pycodex.config.loader.layer_io"


def test_loader_macos_symbols_have_rust_aligned_owner() -> None:
    # Rust: codex-config/src/loader/mod.rs declares cfg(target_os = "macos") child module macos.
    from pycodex.config.loader.macos import load_managed_admin_requirements_toml
    from pycodex.config.loader.macos import managed_preferences_requirements_source

    assert (
        load_managed_admin_requirements_toml.__module__
        == "pycodex.config.loader.macos"
    )
    assert (
        managed_preferences_requirements_source.__module__
        == "pycodex.config.loader.macos"
    )


def test_thread_config_remote_symbols_have_rust_aligned_owner() -> None:
    # Rust: thread_config.rs declares remote and re-exports RemoteThreadConfigLoader.
    from pycodex.config.thread_config.remote import RemoteThreadConfigLoader
    from pycodex.config.thread_config.remote import load_thread_config_request
    from pycodex.config.thread_config.remote import remote_status_to_error

    assert (
        RemoteThreadConfigLoader.__module__
        == "pycodex.config.thread_config.remote"
    )
    assert (
        load_thread_config_request.__module__
        == "pycodex.config.thread_config.remote"
    )
    assert remote_status_to_error.__module__ == "pycodex.config.thread_config.remote"


def test_option_duration_secs_has_rust_aligned_serde_owner() -> None:
    # Rust: mcp_types.rs inline module option_duration_secs serializes Option<Duration>.
    from pycodex.config.mcp_types.option_duration_secs import deserialize
    from pycodex.config.mcp_types.option_duration_secs import serialize

    assert serialize(None) is None
    assert serialize(1.25) == 1.25
    assert deserialize(None) is None
    assert deserialize(1) == 1.0
    with pytest.raises(ValueError, match="non-negative"):
        deserialize(-0.1)
