"""Marketplace config metadata for ``marketplace_add::metadata``."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pycodex.config import MarketplaceConfigUpdate, record_user_marketplace

from ..installed_marketplaces import resolve_configured_marketplace_root
from ..marketplace import validate_marketplace_root
from .source import MarketplaceSource


@dataclass(frozen=True)
class MarketplaceInstallMetadata:
    source_type: str
    source: str
    ref_name: str | None = None
    sparse_paths: tuple[str, ...] = ()

    @classmethod
    def from_source(
        cls,
        source: MarketplaceSource,
        sparse_paths: list[str] | tuple[str, ...],
    ) -> "MarketplaceInstallMetadata":
        return cls(
            source.kind,
            str(source.path) if source.kind == "local" else str(source.url),
            source.ref_name,
            tuple(sparse_paths),
        )


def record_added_marketplace_entry(
    codex_home: str | Path,
    marketplace_name: str,
    metadata: MarketplaceInstallMetadata,
) -> None:
    record_user_marketplace(
        codex_home,
        marketplace_name,
        MarketplaceConfigUpdate(
            last_updated=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source_type=metadata.source_type,
            source=metadata.source,
            ref_name=metadata.ref_name,
            sparse_paths=metadata.sparse_paths,
        ),
    )


def installed_marketplace_root_for_source(
    codex_home: str | Path,
    install_root: str | Path,
    metadata: MarketplaceInstallMetadata,
) -> Path | None:
    for name, entry in _configured_marketplaces(codex_home).items():
        if not isinstance(entry, dict) or not _matches(metadata, entry):
            continue
        root = resolve_configured_marketplace_root(name, entry, install_root)
        if root is not None:
            try:
                validate_marketplace_root(root)
            except Exception:
                continue
            return root
    return None


def find_marketplace_root_by_name(
    codex_home: str | Path,
    install_root: str | Path,
    marketplace_name: str,
) -> Path | None:
    entry = _configured_marketplaces(codex_home).get(marketplace_name)
    if not isinstance(entry, dict):
        return None
    root = resolve_configured_marketplace_root(
        marketplace_name,
        entry,
        install_root,
    )
    if root is None:
        return None
    try:
        validate_marketplace_root(root)
    except Exception:
        return None
    return root


def _configured_marketplaces(codex_home: str | Path) -> dict:
    path = Path(codex_home) / "config.toml"
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    marketplaces = value.get("marketplaces")
    return marketplaces if isinstance(marketplaces, dict) else {}


def _matches(metadata: MarketplaceInstallMetadata, entry: dict) -> bool:
    return (
        entry.get("source_type") == metadata.source_type
        and entry.get("source") == metadata.source
        and entry.get("ref") == metadata.ref_name
        and tuple(entry.get("sparse_paths", ())) == metadata.sparse_paths
    )


__all__ = [
    "MarketplaceInstallMetadata",
    "find_marketplace_root_by_name",
    "installed_marketplace_root_for_source",
    "record_added_marketplace_entry",
]
