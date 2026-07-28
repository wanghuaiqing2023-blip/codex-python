"""Configured marketplace upgrades for ``codex-core-plugins``."""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pycodex.config import MarketplaceConfigUpdate, record_user_marketplace

from ..installed_marketplaces import marketplace_install_root
from ..marketplace import validate_marketplace_root
from .activation import activate_marketplace_root
from .git import clone_git_source, git_remote_revision


@dataclass(frozen=True)
class ConfiguredMarketplaceUpgradeError:
    marketplace_name: str
    message: str


@dataclass(frozen=True)
class ConfiguredMarketplaceUpgradeOutcome:
    selected_marketplaces: tuple[str, ...] = ()
    upgraded_roots: tuple[Path, ...] = ()
    errors: tuple[ConfiguredMarketplaceUpgradeError, ...] = ()

    def all_succeeded(self) -> bool:
        return not self.errors

    @property
    def upgraded(self) -> bool:
        return bool(self.upgraded_roots)


def configured_git_marketplace_names(config_layer_stack: Any) -> list[str]:
    return sorted(_configured_git_marketplaces(config_layer_stack))


def upgrade_configured_git_marketplaces(
    codex_home: str | Path,
    config_layer_stack: Any,
    marketplace_name: str | None = None,
) -> ConfiguredMarketplaceUpgradeOutcome:
    configured = _configured_git_marketplaces(config_layer_stack)
    selected = [
        name
        for name in sorted(configured)
        if marketplace_name is None or name == marketplace_name
    ]
    upgraded: list[Path] = []
    errors: list[ConfiguredMarketplaceUpgradeError] = []
    install_root = marketplace_install_root(codex_home)
    install_root.mkdir(parents=True, exist_ok=True)
    for name in selected:
        entry = configured[name]
        try:
            revision = git_remote_revision(entry["source"], entry.get("ref"))
            if entry.get("last_revision") == revision:
                continue
            with tempfile.TemporaryDirectory(
                prefix="marketplace-upgrade-",
                dir=install_root,
            ) as temporary:
                staged = Path(temporary) / name
                clone_git_source(
                    entry["source"],
                    entry.get("ref"),
                    tuple(entry.get("sparse_paths", ())),
                    staged,
                )
                validate_marketplace_root(staged)
                destination = install_root / name
                activate_marketplace_root(staged, destination)
                upgraded.append(destination.resolve())
            record_user_marketplace(
                codex_home,
                name,
                MarketplaceConfigUpdate(
                    last_updated=entry.get("last_updated", ""),
                    last_revision=revision,
                    source_type="git",
                    source=entry["source"],
                    ref_name=entry.get("ref"),
                    sparse_paths=tuple(entry.get("sparse_paths", ())),
                ),
            )
        except Exception as exc:
            errors.append(ConfiguredMarketplaceUpgradeError(name, str(exc)))
    return ConfiguredMarketplaceUpgradeOutcome(
        tuple(selected),
        tuple(upgraded),
        tuple(errors),
    )


def _configured_git_marketplaces(config_layer_stack: Any) -> dict[str, dict[str, Any]]:
    reader = getattr(config_layer_stack, "effective_user_config", None)
    config = reader() if callable(reader) else config_layer_stack
    if not isinstance(config, Mapping):
        return {}
    marketplaces = config.get("marketplaces")
    if not isinstance(marketplaces, Mapping):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for name, value in marketplaces.items():
        if (
            isinstance(name, str)
            and isinstance(value, Mapping)
            and value.get("source_type") == "git"
            and isinstance(value.get("source"), str)
        ):
            result[name] = dict(value)
    return result


__all__ = [
    "ConfiguredMarketplaceUpgradeError",
    "ConfiguredMarketplaceUpgradeOutcome",
    "configured_git_marketplace_names",
    "upgrade_configured_git_marketplaces",
]
