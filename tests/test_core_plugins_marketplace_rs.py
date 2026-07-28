from __future__ import annotations

import json

import pytest

from pycodex.core_plugins.marketplace import (
    MarketplaceError,
    MarketplacePluginInstallPolicy,
    find_installable_marketplace_plugin,
    find_marketplace_plugin,
    list_marketplaces_with_home,
    load_marketplace,
    marketplace_root_dir,
)


def _write_marketplace(root, payload, *, alternate=False):
    relative = (
        ".claude-plugin/marketplace.json"
        if alternate
        else ".agents/plugins/marketplace.json"
    )
    path = root / relative
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_local_plugin_source_resolves_from_marketplace_root(tmp_path) -> None:
    # Rust: find_marketplace_plugin_resolves_local_source.
    plugin_root = tmp_path / "plugins" / "local-plugin"
    (plugin_root / ".codex-plugin").mkdir(parents=True)
    (plugin_root / ".codex-plugin" / "plugin.json").write_text(
        '{"name":"local-plugin","version":"1.2.3","keywords":["tools"]}',
        encoding="utf-8",
    )
    path = _write_marketplace(
        tmp_path,
        {
            "name": "codex-curated",
            "plugins": [
                {
                    "name": "local-plugin",
                    "source": {"source": "local", "path": "./plugins/local-plugin"},
                }
            ],
        },
    )

    resolved = find_marketplace_plugin(path, "local-plugin")
    marketplace = load_marketplace(path)

    assert resolved.plugin_id.as_key() == "local-plugin@codex-curated"
    assert resolved.source.path == plugin_root.resolve()
    assert marketplace.plugins[0].local_version == "1.2.3"
    assert marketplace.plugins[0].keywords == ("tools",)
    assert marketplace_root_dir(path) == tmp_path.resolve()


def test_alternate_layout_and_string_source_are_supported(tmp_path) -> None:
    # Rust: find_marketplace_plugin_supports_alternate_layout_and_string_local_source.
    path = _write_marketplace(
        tmp_path,
        {
            "name": "alternate-marketplace",
            "plugins": [
                {
                    "name": "string-source-plugin",
                    "source": "./plugins/string-source-plugin",
                }
            ],
        },
        alternate=True,
    )

    resolved = find_marketplace_plugin(path, "string-source-plugin")

    assert resolved.source.path == (
        tmp_path / "plugins" / "string-source-plugin"
    ).resolve()


def test_git_subdir_and_github_shorthand_are_normalized(tmp_path) -> None:
    # Rust: find_marketplace_plugin_supports_git_subdir_sources.
    path = _write_marketplace(
        tmp_path,
        {
            "name": "curated",
            "plugins": [
                {
                    "name": "remote",
                    "source": {
                        "source": "git-subdir",
                        "url": "owner/repo",
                        "path": "./plugins/toolkit",
                        "ref": " main ",
                    },
                }
            ],
        },
    )

    resolved = find_marketplace_plugin(path, "remote")

    assert resolved.source.url == "https://github.com/owner/repo.git"
    assert resolved.source.path == "plugins/toolkit"
    assert resolved.source.ref_name == "main"


def test_install_policy_and_products_reject_unavailable_plugin(tmp_path) -> None:
    # Rust: find_installable_marketplace_plugin policy contract.
    path = _write_marketplace(
        tmp_path,
        {
            "name": "curated",
            "plugins": [
                {
                    "name": "hidden",
                    "source": "./plugins/hidden",
                    "policy": {"installation": "NOT_AVAILABLE"},
                }
            ],
        },
    )

    with pytest.raises(MarketplaceError, match="not available"):
        find_installable_marketplace_plugin(path, "hidden")

    resolved = find_marketplace_plugin(path, "hidden")
    assert resolved.policy.installation is MarketplacePluginInstallPolicy.NOT_AVAILABLE


def test_list_marketplaces_keeps_distinct_roots_with_same_name(tmp_path) -> None:
    # Rust: list_marketplaces_keeps_distinct_entries_for_same_name.
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    payload = {"name": "curated", "plugins": []}
    _write_marketplace(home, payload)
    _write_marketplace(repo, payload)

    outcome = list_marketplaces_with_home([repo], home)

    assert [marketplace.name for marketplace in outcome.marketplaces] == [
        "curated",
        "curated",
    ]
    assert outcome.errors == ()


def test_local_source_rejects_parent_traversal(tmp_path) -> None:
    path = _write_marketplace(
        tmp_path,
        {
            "name": "curated",
            "plugins": [{"name": "bad", "source": "./../outside"}],
        },
    )

    with pytest.raises(MarketplaceError, match="not found"):
        find_marketplace_plugin(path, "bad")
