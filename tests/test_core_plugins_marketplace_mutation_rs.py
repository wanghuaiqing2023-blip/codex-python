from __future__ import annotations

import asyncio
import json

import pytest

from pycodex.core_plugins.marketplace_add import (
    MarketplaceAddError,
    MarketplaceAddRequest,
    add_marketplace,
    is_local_marketplace_source,
)
from pycodex.core_plugins.marketplace_add.install import (
    ensure_marketplace_destination_is_inside_install_root,
    safe_marketplace_dir_name,
)
from pycodex.core_plugins.marketplace_add.source import parse_marketplace_source
from pycodex.core_plugins.marketplace_remove import (
    MarketplaceRemoveError,
    MarketplaceRemoveRequest,
    remove_marketplace,
)


def _write_marketplace(root, name="debug"):
    path = root / ".agents" / "plugins" / "marketplace.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"name": name, "plugins": []}),
        encoding="utf-8",
    )


def test_marketplace_source_parses_github_ref_and_local_directory(tmp_path) -> None:
    # Rust: marketplace_add::source parser tests.
    git = parse_marketplace_source("owner/repo@main")
    assert git.kind == "git"
    assert git.url == "https://github.com/owner/repo.git"
    assert git.ref_name == "main"

    _write_marketplace(tmp_path)
    local = parse_marketplace_source(str(tmp_path.resolve()))
    assert local.kind == "local"
    assert local.path == tmp_path.resolve()
    assert is_local_marketplace_source(str(tmp_path.resolve())) is True


def test_add_local_marketplace_records_config_and_detects_existing(tmp_path) -> None:
    # Rust: add_marketplace_sync_installs_local_directory_source_and_updates_config
    # and treats_existing_local_directory_source_as_already_added.
    codex_home = tmp_path / "home"
    source = tmp_path / "marketplace"
    _write_marketplace(source)
    request = MarketplaceAddRequest(str(source.resolve()))

    first = asyncio.run(add_marketplace(codex_home, request))
    second = asyncio.run(add_marketplace(codex_home, request))

    assert first.marketplace_name == "debug"
    assert first.installed_root == source.resolve()
    assert first.already_added is False
    assert second.already_added is True
    config = (codex_home / "config.toml").read_text(encoding="utf-8")
    assert "[marketplaces.debug]" in config
    assert 'source_type = "local"' in config


def test_add_local_rejects_sparse_and_reserved_name(tmp_path) -> None:
    # Rust: sparse checkout for local source and curated-name reservation.
    source = tmp_path / "marketplace"
    _write_marketplace(source, "openai-curated")
    with pytest.raises(MarketplaceAddError, match="sparse"):
        asyncio.run(
            add_marketplace(
                tmp_path / "home",
                MarketplaceAddRequest(str(source.resolve()), sparse_paths=("plugins",)),
            )
        )
    with pytest.raises(MarketplaceAddError, match="reserved"):
        asyncio.run(
            add_marketplace(
                tmp_path / "home",
                MarketplaceAddRequest(str(source.resolve())),
            )
        )


def test_remove_marketplace_removes_config_and_installed_root(tmp_path) -> None:
    # Rust: remove_marketplace_sync_removes_config_and_installed_root.
    codex_home = tmp_path / "home"
    source = tmp_path / "marketplace"
    _write_marketplace(source)
    asyncio.run(add_marketplace(codex_home, MarketplaceAddRequest(str(source.resolve()))))
    installed = codex_home / ".tmp" / "marketplaces" / "debug"
    installed.mkdir(parents=True)

    outcome = asyncio.run(
        remove_marketplace(codex_home, MarketplaceRemoveRequest("debug"))
    )

    assert outcome.removed_installed_root == installed.resolve()
    assert not installed.exists()
    assert "marketplaces.debug" not in (
        codex_home / "config.toml"
    ).read_text(encoding="utf-8")


def test_remove_unknown_marketplace_and_destination_escape_are_rejected(tmp_path) -> None:
    with pytest.raises(MarketplaceRemoveError, match="not configured or installed"):
        asyncio.run(
            remove_marketplace(tmp_path, MarketplaceRemoveRequest("unknown"))
        )
    with pytest.raises(ValueError, match="inside install root"):
        ensure_marketplace_destination_is_inside_install_root(
            tmp_path / "inside",
            tmp_path / "outside",
        )
    with pytest.raises(Exception):
        safe_marketplace_dir_name("../escape")
