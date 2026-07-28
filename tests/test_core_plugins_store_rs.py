from __future__ import annotations

import json

import pytest

from pycodex.core_plugins.store import (
    DEFAULT_PLUGIN_VERSION,
    PluginStore,
    PluginStoreError,
    plugin_version_for_source,
    validate_plugin_version_segment,
)
from pycodex.plugin import PluginId


def _write_plugin(root, *, name="sample", version=None):
    manifest_dir = root / ".codex-plugin"
    manifest_dir.mkdir(parents=True)
    manifest = {"name": name}
    if version is not None:
        manifest["version"] = version
    (manifest_dir / "plugin.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (root / "payload.txt").write_text("payload", encoding="utf-8")


def test_plugin_store_paths_and_default_version(tmp_path) -> None:
    # Rust: store_tests::plugin_root_derives_path_from_key_and_version and
    # plugin_data_root_derives_path_from_key.
    store = PluginStore.try_new(tmp_path.resolve())
    plugin_id = PluginId.parse("sample@curated")

    assert store.plugin_root(plugin_id, "1.2.3") == (
        tmp_path / "plugins" / "cache" / "curated" / "sample" / "1.2.3"
    )
    assert store.plugin_data_root(plugin_id) == (
        tmp_path / "plugins" / "data" / "sample-curated"
    )


def test_install_uses_manifest_version_and_prunes_old_versions(tmp_path) -> None:
    # Rust: install_uses_manifest_version_when_present and
    # install_with_new_version_keeps_existing_plugin_root_and_prunes_old_versions.
    source = tmp_path / "source"
    _write_plugin(source, version="1.2.3")
    store = PluginStore.new(tmp_path.resolve())
    plugin_id = PluginId.parse("sample@curated")

    first = store.install(source, plugin_id)
    assert first.plugin_version == "1.2.3"
    assert (first.installed_path / "payload.txt").is_file()

    second = store.install_with_version(source, plugin_id, "2.0.0")
    assert store.active_plugin_version(plugin_id) == "2.0.0"
    assert second.installed_path.is_dir()
    assert not store.plugin_root(plugin_id, "1.2.3").exists()


def test_local_version_is_preferred_and_uninstall_removes_plugin(tmp_path) -> None:
    # Rust: active_plugin_version_prefers_default_local_version and uninstall.
    store = PluginStore.new(tmp_path.resolve())
    plugin_id = PluginId.parse("sample@curated")
    for version in ("9.0.0", DEFAULT_PLUGIN_VERSION):
        store.plugin_root(plugin_id, version).mkdir(parents=True)

    assert store.active_plugin_version(plugin_id) == DEFAULT_PLUGIN_VERSION
    store.uninstall(plugin_id)
    assert not store.is_installed(plugin_id)


@pytest.mark.parametrize("value", ["", ".", "..", "../escape", "bad/value", "bad value"])
def test_validate_plugin_version_segment_rejects_unsafe_values(value) -> None:
    # Rust: validate_plugin_version_segment source contract.
    with pytest.raises(PluginStoreError):
        validate_plugin_version_segment(value)


def test_manifest_version_validation_and_name_match(tmp_path) -> None:
    # Rust: install_rejects_blank_manifest_version and name mismatch tests.
    source = tmp_path / "source"
    _write_plugin(source, name="different", version=" ")
    store = PluginStore.new(tmp_path.resolve())

    with pytest.raises(PluginStoreError, match="must not be blank"):
        plugin_version_for_source(source)

    (source / ".codex-plugin" / "plugin.json").write_text(
        '{"name":"different","version":"1.0.0"}',
        encoding="utf-8",
    )
    with pytest.raises(PluginStoreError, match="does not match"):
        store.install(source, PluginId.parse("sample@curated"))
