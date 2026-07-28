"""Add configured marketplaces for ``codex-core-plugins::marketplace_add``."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .. import OPENAI_CURATED_MARKETPLACE_NAME
from ..installed_marketplaces import marketplace_install_root
from .install import (
    clone_git_source,
    ensure_marketplace_destination_is_inside_install_root,
    safe_marketplace_dir_name,
)
from .metadata import (
    MarketplaceInstallMetadata,
    find_marketplace_root_by_name,
    installed_marketplace_root_for_source,
    record_added_marketplace_entry,
)
from .source import (
    MarketplaceSourceError,
    parse_marketplace_source,
    validate_marketplace_source_root,
)


@dataclass(frozen=True)
class MarketplaceAddRequest:
    source: str
    ref_name: str | None = None
    sparse_paths: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MarketplaceAddOutcome:
    marketplace_name: str
    source_display: str
    installed_root: Path
    already_added: bool


class MarketplaceAddError(Exception):
    pass


async def add_marketplace(
    codex_home: str | Path,
    request: MarketplaceAddRequest,
) -> MarketplaceAddOutcome:
    try:
        source = parse_marketplace_source(request.source, request.ref_name)
    except MarketplaceSourceError as exc:
        raise MarketplaceAddError(str(exc)) from exc
    if request.sparse_paths and source.kind != "git":
        raise MarketplaceAddError(
            "--sparse is only supported for git marketplace sources"
        )

    install_root = marketplace_install_root(codex_home)
    install_root.mkdir(parents=True, exist_ok=True)
    metadata = MarketplaceInstallMetadata.from_source(source, request.sparse_paths)
    existing = installed_marketplace_root_for_source(
        codex_home,
        install_root,
        metadata,
    )
    if existing is not None:
        marketplace_name = validate_marketplace_source_root(existing)
        record_added_marketplace_entry(codex_home, marketplace_name, metadata)
        return MarketplaceAddOutcome(
            marketplace_name,
            source.display(),
            existing.resolve(),
            True,
        )

    if source.kind == "local":
        assert source.path is not None
        marketplace_name = validate_marketplace_source_root(source.path)
        _validate_name(codex_home, install_root, marketplace_name)
        record_added_marketplace_entry(codex_home, marketplace_name, metadata)
        return MarketplaceAddOutcome(
            marketplace_name,
            source.display(),
            source.path.resolve(),
            False,
        )

    staging = Path(tempfile.mkdtemp(prefix="marketplace-add-", dir=install_root))
    try:
        assert source.url is not None
        clone_git_source(
            source.url,
            source.ref_name,
            request.sparse_paths,
            staging,
        )
        marketplace_name = validate_marketplace_source_root(staging)
        _validate_name(codex_home, install_root, marketplace_name)
        destination = install_root / safe_marketplace_dir_name(marketplace_name)
        ensure_marketplace_destination_is_inside_install_root(install_root, destination)
        if destination.exists():
            raise MarketplaceAddError(
                f"marketplace '{marketplace_name}' is already added from a different "
                "source; remove it before adding this source"
            )
        staging.replace(destination)
        record_added_marketplace_entry(codex_home, marketplace_name, metadata)
        return MarketplaceAddOutcome(
            marketplace_name,
            source.display(),
            destination.resolve(),
            False,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def is_local_marketplace_source(
    source: str,
    explicit_ref: str | None = None,
) -> bool:
    try:
        return parse_marketplace_source(source, explicit_ref).kind == "local"
    except MarketplaceSourceError as exc:
        raise MarketplaceAddError(str(exc)) from exc


def _validate_name(
    codex_home: str | Path,
    install_root: Path,
    marketplace_name: str,
) -> None:
    if marketplace_name == OPENAI_CURATED_MARKETPLACE_NAME:
        raise MarketplaceAddError(
            f"marketplace '{OPENAI_CURATED_MARKETPLACE_NAME}' is reserved and "
            "cannot be added from this source"
        )
    if find_marketplace_root_by_name(
        codex_home,
        install_root,
        marketplace_name,
    ) is not None:
        raise MarketplaceAddError(
            f"marketplace '{marketplace_name}' is already added from a different "
            "source; remove it before adding this source"
        )


__all__ = [
    "MarketplaceAddError",
    "MarketplaceAddOutcome",
    "MarketplaceAddRequest",
    "add_marketplace",
    "is_local_marketplace_source",
]
