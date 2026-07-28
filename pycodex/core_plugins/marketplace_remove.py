"""Remove configured marketplaces for ``codex-core-plugins``."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from pycodex.config import (
    RemoveMarketplaceConfigOutcome,
    remove_user_marketplace_config,
)
from pycodex.plugin import PluginIdError, validate_plugin_segment

from .installed_marketplaces import marketplace_install_root


@dataclass(frozen=True)
class MarketplaceRemoveRequest:
    marketplace_name: str


@dataclass(frozen=True)
class MarketplaceRemoveOutcome:
    marketplace_name: str
    removed_installed_root: Path | None


class MarketplaceRemoveError(Exception):
    pass


async def remove_marketplace(
    codex_home: str | Path,
    request: MarketplaceRemoveRequest,
) -> MarketplaceRemoveOutcome:
    name = request.marketplace_name
    try:
        validate_plugin_segment(name, "marketplace name")
    except PluginIdError as exc:
        raise MarketplaceRemoveError(str(exc)) from exc

    destination = marketplace_install_root(codex_home) / name
    config_result = remove_user_marketplace_config(codex_home, name)
    if config_result.outcome is RemoveMarketplaceConfigOutcome.NAME_CASE_MISMATCH:
        raise MarketplaceRemoveError(
            f"marketplace `{name}` does not match configured marketplace "
            f"`{config_result.configured_name}` exactly"
        )

    removed_root: Path | None = None
    if destination.exists():
        removed_root = destination.resolve()
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    if (
        removed_root is None
        and config_result.outcome is not RemoveMarketplaceConfigOutcome.REMOVED
    ):
        raise MarketplaceRemoveError(
            f"marketplace `{name}` is not configured or installed"
        )
    return MarketplaceRemoveOutcome(name, removed_root)


__all__ = [
    "MarketplaceRemoveError",
    "MarketplaceRemoveOutcome",
    "MarketplaceRemoveRequest",
    "remove_marketplace",
]
