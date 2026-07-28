from __future__ import annotations

import json

from pycodex.core_plugins.installed_marketplaces import (
    installed_marketplace_roots_from_layer_stack,
    marketplace_install_root,
    resolve_configured_marketplace_root,
)
from pycodex.core_plugins.manifest import load_plugin_manifest
from pycodex.core_plugins.toggles import collect_plugin_enabled_candidates


def test_collect_plugin_enabled_candidates_tracks_writes_and_last_value() -> None:
    # Rust: core-plugins/src/toggles.rs unit tests.
    assert collect_plugin_enabled_candidates(
        [
            ("plugins.sample@test.enabled", True),
            ("plugins.other@test", {"enabled": False, "ignored": True}),
            (
                "plugins",
                {
                    "nested@test": {"enabled": True},
                    "skip@test": {"name": "skip"},
                },
            ),
            ("plugins.sample@test", {"enabled": False}),
        ]
    ) == {
        "nested@test": True,
        "other@test": False,
        "sample@test": False,
    }


def test_installed_marketplace_roots_resolve_local_and_installed(tmp_path) -> None:
    # Rust: core-plugins/src/installed_marketplaces.rs source contract.
    local = tmp_path / "local"
    installed = marketplace_install_root(tmp_path) / "curated"
    for root in (local, installed):
        (root / ".agents" / "plugins").mkdir(parents=True)
        (root / ".agents" / "plugins" / "marketplace.json").write_text(
            "{}",
            encoding="utf-8",
        )
    config = {
        "marketplaces": {
            "local": {"source_type": "local", "source": str(local)},
            "curated": {"source_type": "git", "source": "ignored"},
        }
    }

    assert installed_marketplace_roots_from_layer_stack(config, tmp_path) == sorted(
        [local.resolve(), installed.resolve()],
        key=str,
    )
    assert resolve_configured_marketplace_root(
        "missing",
        {"source_type": "local", "source": ""},
        tmp_path,
    ) is None


def test_manifest_normalizes_interface_prompts_paths_and_version(tmp_path) -> None:
    # Rust: manifest.rs tests for prompt normalization, max count, paths, and
    # trimmed versions.
    root = tmp_path / "demo-plugin"
    (root / ".codex-plugin").mkdir(parents=True)
    (root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "demo-plugin",
                "version": " 1.2.3-beta+7 ",
                "keywords": ["api-key", "developer tools"],
                "skills": "./skills",
                "mcpServers": "../outside.json",
                "interface": {
                    "displayName": "Demo Plugin",
                    "defaultPrompt": [
                        " Summarize   my inbox ",
                        123,
                        "Draft the reply",
                        "Find my next action",
                        "ignored fourth prompt",
                    ],
                    "logo": "./assets/logo.png",
                },
            }
        ),
        encoding="utf-8",
    )

    manifest = load_plugin_manifest(root)

    assert manifest is not None
    assert manifest.version == "1.2.3-beta+7"
    assert manifest.keywords == ("api-key", "developer tools")
    assert manifest.paths.skills == (root / "skills").resolve()
    assert manifest.paths.mcp_servers is None
    assert manifest.interface is not None
    assert manifest.interface.default_prompt == (
        "Summarize my inbox",
        "Draft the reply",
        "Find my next action",
    )
    assert manifest.interface.logo == (root / "assets" / "logo.png").resolve()


def test_manifest_uses_alternate_discoverable_path_and_directory_name(tmp_path) -> None:
    # Rust: plugin_manifest_uses_alternate_discoverable_path.
    root = tmp_path / "fallback-name"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(
        '{"name": "", "version": " 2.0.0 "}',
        encoding="utf-8",
    )

    manifest = load_plugin_manifest(root)

    assert manifest is not None
    assert manifest.name == "fallback-name"
    assert manifest.version == "2.0.0"
