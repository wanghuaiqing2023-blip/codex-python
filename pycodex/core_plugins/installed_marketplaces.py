"""Installed marketplace paths for ``codex-core-plugins``."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pycodex.plugin import PluginIdError, validate_plugin_segment

from .marketplace import find_marketplace_manifest_path

INSTALLED_MARKETPLACES_DIR = ".tmp/marketplaces"

_LOG = logging.getLogger(__name__)


def marketplace_install_root(codex_home: str | Path) -> Path:
    return Path(codex_home) / INSTALLED_MARKETPLACES_DIR


def installed_marketplace_roots_from_layer_stack(
    config_layer_stack: Any,
    codex_home: str | Path,
) -> list[Path]:
    reader = getattr(config_layer_stack, "effective_user_config", None)
    user_config = reader() if callable(reader) else config_layer_stack
    if not isinstance(user_config, Mapping):
        return []
    marketplaces = user_config.get("marketplaces")
    if marketplaces is None:
        return []
    if not isinstance(marketplaces, Mapping):
        _LOG.warning("invalid marketplaces config: expected table")
        return []

    default_root = marketplace_install_root(codex_home)
    roots: list[Path] = []
    for marketplace_name, marketplace in marketplaces.items():
        if not isinstance(marketplace_name, str) or not isinstance(marketplace, Mapping):
            continue
        try:
            validate_plugin_segment(marketplace_name, "marketplace name")
        except PluginIdError:
            continue
        path = resolve_configured_marketplace_root(
            marketplace_name,
            marketplace,
            default_root,
        )
        if path is not None and find_marketplace_manifest_path(path) is not None:
            roots.append(path.resolve())
    return sorted(set(roots), key=str)


def resolve_configured_marketplace_root(
    marketplace_name: str,
    marketplace: Mapping[str, Any],
    default_install_root: str | Path,
) -> Path | None:
    if marketplace.get("source_type") == "local":
        source = marketplace.get("source")
        return Path(source) if isinstance(source, str) and source else None
    return Path(default_install_root) / marketplace_name


__all__ = [
    "INSTALLED_MARKETPLACES_DIR",
    "installed_marketplace_roots_from_layer_stack",
    "marketplace_install_root",
    "resolve_configured_marketplace_root",
]
