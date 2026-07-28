from __future__ import annotations

from pycodex.core_plugins.marketplace_upgrade import (
    ConfiguredMarketplaceUpgradeError,
    ConfiguredMarketplaceUpgradeOutcome,
    configured_git_marketplace_names,
)
from pycodex.core_plugins.marketplace_upgrade.activation import (
    activate_marketplace_root,
    installed_marketplace_metadata_matches,
    write_installed_marketplace_metadata,
)


def test_configured_git_marketplace_names_filters_and_sorts() -> None:
    # Rust: configured_git_marketplace_names source contract.
    config = {
        "marketplaces": {
            "zeta": {"source_type": "git", "source": "https://example/zeta.git"},
            "local": {"source_type": "local", "source": "/tmp/local"},
            "alpha": {"source_type": "git", "source": "https://example/alpha.git"},
            "missing": {"source_type": "git"},
        }
    }
    assert configured_git_marketplace_names(config) == ["alpha", "zeta"]


def test_upgrade_outcome_reports_all_succeeded() -> None:
    assert ConfiguredMarketplaceUpgradeOutcome().all_succeeded() is True
    assert (
        ConfiguredMarketplaceUpgradeOutcome(
            errors=(ConfiguredMarketplaceUpgradeError("bad", "failed"),)
        ).all_succeeded()
        is False
    )


def test_activation_metadata_and_root_replacement(tmp_path) -> None:
    # Rust: marketplace_upgrade::activation metadata and atomic activation.
    staged = tmp_path / "staged"
    destination = tmp_path / "active"
    staged.mkdir()
    (staged / "new.txt").write_text("new", encoding="utf-8")
    destination.mkdir()
    (destination / "old.txt").write_text("old", encoding="utf-8")
    metadata = {"source": "https://example/repo.git", "revision": "abc"}

    write_installed_marketplace_metadata(staged, metadata)
    assert installed_marketplace_metadata_matches(staged, metadata) is True
    activate_marketplace_root(staged, destination)

    assert (destination / "new.txt").is_file()
    assert not (destination / "old.txt").exists()
