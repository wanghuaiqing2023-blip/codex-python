"""Marketplace source parsing for ``marketplace_add::source``."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


class MarketplaceSourceError(ValueError):
    pass


@dataclass(frozen=True)
class MarketplaceSource:
    kind: str
    url: str | None = None
    ref_name: str | None = None
    path: Path | None = None

    def display(self) -> str:
        return str(self.path) if self.kind == "local" else str(self.url)


def parse_marketplace_source(
    source: str,
    explicit_ref: str | None = None,
) -> MarketplaceSource:
    source = source.strip()
    if not source:
        raise MarketplaceSourceError("marketplace source must not be empty")
    base, parsed_ref = _split_source_ref(source)
    ref_name = explicit_ref or parsed_ref
    if _looks_like_local_path(base):
        if ref_name is not None:
            raise MarketplaceSourceError(
                "--ref is only supported for git marketplace sources"
            )
        path = _resolve_local_source_path(base)
        if path.is_file():
            raise MarketplaceSourceError(
                "local marketplace source must be a directory, not a file"
            )
        return MarketplaceSource("local", path=path)
    if _is_git_url(base):
        return MarketplaceSource("git", url=_normalize_git_url(base), ref_name=ref_name)
    if re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", base):
        return MarketplaceSource(
            "git",
            url=f"https://github.com/{base.removesuffix('.git')}.git",
            ref_name=ref_name,
        )
    raise MarketplaceSourceError(
        "invalid marketplace source format; expected owner/repo, a git URL, "
        "or a local marketplace path"
    )


def validate_marketplace_source_root(root: str | Path) -> str:
    from ..marketplace import validate_marketplace_root
    from pycodex.plugin import validate_plugin_segment

    name = validate_marketplace_root(root)
    validate_plugin_segment(name, "marketplace name")
    return name


def _split_source_ref(source: str) -> tuple[str, str | None]:
    if "#" in source:
        base, ref_name = source.rsplit("#", 1)
        return base, ref_name.strip() or None
    if "://" not in source and not source.startswith("git@") and "@" in source:
        base, ref_name = source.rsplit("@", 1)
        return base, ref_name.strip() or None
    return source, None


def _looks_like_local_path(source: str) -> bool:
    return (
        Path(source).is_absolute()
        or re.match(r"^[A-Za-z]:[\\/]", source) is not None
        or source.startswith("\\\\")
        or source.startswith(("./", ".\\", "../", "..\\", "~/"))
        or source in {".", ".."}
    )


def _resolve_local_source_path(source: str) -> Path:
    if source.startswith("~/"):
        home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
        path = Path(home) / source[2:] if home else Path(source)
    else:
        path = Path(source)
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise MarketplaceSourceError(
            f"failed to resolve local marketplace source path: {exc}"
        ) from exc


def _is_git_url(source: str) -> bool:
    return source.startswith(("http://", "https://", "ssh://", "git@"))


def _normalize_git_url(url: str) -> str:
    url = url.rstrip("/")
    return (
        f"{url}.git"
        if url.startswith("https://github.com/") and not url.endswith(".git")
        else url
    )


__all__ = [
    "MarketplaceSource",
    "MarketplaceSourceError",
    "parse_marketplace_source",
    "validate_marketplace_source_root",
]
