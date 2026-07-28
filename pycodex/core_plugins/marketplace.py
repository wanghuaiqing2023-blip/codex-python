"""Marketplace loading for ``codex-core-plugins::marketplace``."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any

from pycodex.plugin import PluginId, PluginIdError

from .manifest import PluginManifest, PluginManifestInterface, load_plugin_manifest

MARKETPLACE_MANIFEST_RELATIVE_PATHS = (
    ".agents/plugins/marketplace.json",
    ".claude-plugin/marketplace.json",
)


class MarketplacePluginInstallPolicy(str, Enum):
    NOT_AVAILABLE = "NOT_AVAILABLE"
    AVAILABLE = "AVAILABLE"
    INSTALLED_BY_DEFAULT = "INSTALLED_BY_DEFAULT"


class MarketplacePluginAuthPolicy(str, Enum):
    ON_INSTALL = "ON_INSTALL"
    ON_USE = "ON_USE"


@dataclass(frozen=True)
class MarketplacePluginPolicy:
    installation: MarketplacePluginInstallPolicy = MarketplacePluginInstallPolicy.AVAILABLE
    authentication: MarketplacePluginAuthPolicy = MarketplacePluginAuthPolicy.ON_INSTALL
    products: tuple[str, ...] | None = None


@dataclass(frozen=True)
class MarketplacePluginSource:
    kind: str
    path: Path | str | None = None
    url: str | None = None
    ref_name: str | None = None
    sha: str | None = None

    @classmethod
    def local(cls, path: str | Path) -> "MarketplacePluginSource":
        return cls("local", path=Path(path))

    @classmethod
    def git(
        cls,
        url: str,
        *,
        path: str | None = None,
        ref_name: str | None = None,
        sha: str | None = None,
    ) -> "MarketplacePluginSource":
        return cls("git", path=path, url=url, ref_name=ref_name, sha=sha)


@dataclass(frozen=True)
class ResolvedMarketplacePlugin:
    plugin_id: PluginId
    source: MarketplacePluginSource
    policy: MarketplacePluginPolicy
    interface: PluginManifestInterface | None
    manifest: PluginManifest | None


@dataclass(frozen=True)
class MarketplacePlugin:
    name: str
    local_version: str | None
    source: MarketplacePluginSource
    policy: MarketplacePluginPolicy
    interface: PluginManifestInterface | None
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketplaceInterface:
    display_name: str | None = None


@dataclass(frozen=True)
class Marketplace:
    name: str
    path: Path
    interface: MarketplaceInterface | None
    plugins: tuple[MarketplacePlugin, ...]


@dataclass(frozen=True)
class MarketplaceListError:
    path: Path
    message: str


@dataclass(frozen=True)
class MarketplaceListOutcome:
    marketplaces: tuple[Marketplace, ...] = ()
    errors: tuple[MarketplaceListError, ...] = ()


class MarketplaceError(Exception):
    pass


def find_marketplace_manifest_path(root: str | Path) -> Path | None:
    root_path = Path(root)
    for relative_path in MARKETPLACE_MANIFEST_RELATIVE_PATHS:
        candidate = root_path / relative_path
        if candidate.is_file():
            return candidate.resolve()
    return None


def marketplace_root_dir(marketplace_path: str | Path) -> Path:
    path = Path(marketplace_path).resolve()
    for relative in MARKETPLACE_MANIFEST_RELATIVE_PATHS:
        parts = Path(relative).parts
        if tuple(path.parts[-len(parts) :]) == parts:
            return Path(*path.parts[: -len(parts)])
    raise MarketplaceError(
        f"invalid marketplace file `{path}`: marketplace file is not in a supported location"
    )


def validate_marketplace_root(root: str | Path) -> str:
    path = find_marketplace_manifest_path(root)
    if path is None:
        raise MarketplaceError(
            f"invalid marketplace file `{root}`: marketplace root does not contain "
            "a supported manifest"
        )
    return load_marketplace(path).name


def find_marketplace_plugin(
    marketplace_path: str | Path,
    plugin_name: str,
) -> ResolvedMarketplacePlugin:
    path = Path(marketplace_path)
    raw = _load_raw_marketplace(path)
    for plugin in raw["plugins"]:
        if isinstance(plugin, dict) and plugin.get("name") == plugin_name:
            try:
                resolved = _resolve_plugin(path, raw["name"], plugin)
            except (MarketplaceError, PluginIdError):
                resolved = None
            if resolved is not None:
                return resolved
    raise MarketplaceError(
        f"plugin `{plugin_name}` was not found in marketplace `{raw['name']}`"
    )


def find_installable_marketplace_plugin(
    marketplace_path: str | Path,
    plugin_name: str,
    restriction_product: str | None = None,
) -> ResolvedMarketplacePlugin:
    resolved = find_marketplace_plugin(marketplace_path, plugin_name)
    products = resolved.policy.products
    allowed = products is None or (
        bool(products) and restriction_product is not None and restriction_product in products
    )
    if (
        resolved.policy.installation is MarketplacePluginInstallPolicy.NOT_AVAILABLE
        or not allowed
    ):
        raise MarketplaceError(
            f"plugin `{plugin_name}` is not available for install in marketplace "
            f"`{resolved.plugin_id.marketplace_name}`"
        )
    return resolved


def load_marketplace(path: str | Path) -> Marketplace:
    marketplace_path = Path(path).resolve()
    raw = _load_raw_marketplace(marketplace_path)
    plugins: list[MarketplacePlugin] = []
    for entry in raw["plugins"]:
        if not isinstance(entry, dict):
            continue
        try:
            resolved = _resolve_plugin(marketplace_path, raw["name"], entry)
        except (MarketplaceError, PluginIdError):
            continue
        if resolved is None:
            continue
        plugins.append(
            MarketplacePlugin(
                name=resolved.plugin_id.plugin_name,
                local_version=(
                    resolved.manifest.version if resolved.manifest is not None else None
                ),
                source=resolved.source,
                policy=resolved.policy,
                interface=resolved.interface,
                keywords=(
                    resolved.manifest.keywords if resolved.manifest is not None else ()
                ),
            )
        )
    raw_interface = raw.get("interface")
    display_name = (
        raw_interface.get("displayName")
        if isinstance(raw_interface, dict)
        and isinstance(raw_interface.get("displayName"), str)
        else None
    )
    return Marketplace(
        name=raw["name"],
        path=marketplace_path,
        interface=MarketplaceInterface(display_name) if display_name is not None else None,
        plugins=tuple(plugins),
    )


def list_marketplaces(
    additional_roots: list[Path] | tuple[Path, ...],
) -> MarketplaceListOutcome:
    return list_marketplaces_with_home(additional_roots, _home_dir())


def list_marketplaces_with_home(
    additional_roots: list[Path] | tuple[Path, ...],
    home_dir: Path | None,
) -> MarketplaceListOutcome:
    paths: list[Path] = []
    if home_dir is not None and (path := find_marketplace_manifest_path(home_dir)):
        paths.append(path)
    for root in additional_roots:
        if (path := find_marketplace_manifest_path(root)) and path not in paths:
            paths.append(path)
    marketplaces: list[Marketplace] = []
    errors: list[MarketplaceListError] = []
    for path in paths:
        try:
            marketplaces.append(load_marketplace(path))
        except MarketplaceError as exc:
            errors.append(MarketplaceListError(path, str(exc)))
    return MarketplaceListOutcome(tuple(marketplaces), tuple(errors))


def plugin_interface_with_marketplace_category(
    interface: PluginManifestInterface | None,
    category: str | None,
) -> PluginManifestInterface | None:
    if category is None:
        return interface
    return replace(interface or PluginManifestInterface(), category=category)


def _load_raw_marketplace(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise MarketplaceError(f"marketplace file `{path}` does not exist")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MarketplaceError(f"invalid marketplace file `{path}`: {exc}") from exc
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("name"), str)
        or not isinstance(raw.get("plugins"), list)
    ):
        raise MarketplaceError(f"invalid marketplace file `{path}`: invalid schema")
    return raw


def _resolve_plugin(
    marketplace_path: Path,
    marketplace_name: str,
    raw: dict[str, Any],
) -> ResolvedMarketplacePlugin | None:
    name = raw.get("name")
    if not isinstance(name, str):
        return None
    source = _resolve_source(marketplace_path, raw.get("source"))
    if source is None:
        return None
    manifest = (
        load_plugin_manifest(source.path)
        if source.kind == "local" and isinstance(source.path, Path)
        else None
    )
    raw_policy = raw.get("policy", {})
    if not isinstance(raw_policy, dict):
        raw_policy = {}
    try:
        installation = MarketplacePluginInstallPolicy(
            raw_policy.get("installation", "AVAILABLE")
        )
        authentication = MarketplacePluginAuthPolicy(
            raw_policy.get("authentication", "ON_INSTALL")
        )
    except ValueError as exc:
        raise MarketplaceError(f"invalid plugin policy: {exc}") from exc
    products_value = raw_policy.get("products")
    products = (
        tuple(item for item in products_value if isinstance(item, str))
        if isinstance(products_value, list)
        else None
    )
    interface = plugin_interface_with_marketplace_category(
        manifest.interface if manifest is not None else None,
        raw.get("category") if isinstance(raw.get("category"), str) else None,
    )
    return ResolvedMarketplacePlugin(
        PluginId.parse(f"{name}@{marketplace_name}"),
        source,
        MarketplacePluginPolicy(installation, authentication, products),
        interface,
        manifest,
    )


def _resolve_source(path: Path, value: Any) -> MarketplacePluginSource | None:
    if isinstance(value, str):
        return MarketplacePluginSource.local(_local_source_path(path, value))
    if not isinstance(value, dict):
        return None
    source_type = value.get("source")
    if source_type == "local":
        return MarketplacePluginSource.local(
            _local_source_path(path, value.get("path"))
        )
    if source_type in {"url", "git-subdir"}:
        url = _normalize_git_url(path, value.get("url"))
        subdir = value.get("path")
        if source_type == "git-subdir" and not isinstance(subdir, str):
            raise MarketplaceError("git plugin source path must not be empty")
        normalized_subdir = _safe_relative(subdir, allow_dot_prefix=True) if subdir else None
        return MarketplacePluginSource.git(
            url,
            path=normalized_subdir,
            ref_name=_trimmed(value.get("ref")),
            sha=_trimmed(value.get("sha")),
        )
    return None


def _local_source_path(marketplace_path: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.startswith("./"):
        raise MarketplaceError("local plugin source path must start with `./`")
    relative = _safe_relative(value, allow_dot_prefix=True)
    return (marketplace_root_dir(marketplace_path) / relative).resolve()


def _safe_relative(value: str, *, allow_dot_prefix: bool) -> str:
    normalized = value[2:] if allow_dot_prefix and value.startswith("./") else value
    path = PurePosixPath(normalized.replace("\\", "/"))
    if not normalized or normalized in {".", "./"} or ".." in path.parts or path.is_absolute():
        raise MarketplaceError("plugin source path must stay within the marketplace root")
    return path.as_posix()


def _normalize_git_url(marketplace_path: Path, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketplaceError("git plugin source url must not be empty")
    url = value.strip()
    if url.startswith("./") or url.startswith(".\\"):
        relative = _safe_relative(url, allow_dot_prefix=True)
        return str((marketplace_root_dir(marketplace_path) / relative).resolve())
    if "://" in url or url.startswith("git@") or url.startswith("/") or url.startswith("file://"):
        return url + ".git" if url.startswith("https://github.com/") and not url.endswith(".git") else url
    parts = url.split("/")
    if len(parts) == 2 and all(parts):
        return f"https://github.com/{parts[0]}/{parts[1].removesuffix('.git')}.git"
    raise MarketplaceError(f"invalid git plugin source url: {url}")


def _trimmed(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _home_dir() -> Path | None:
    for name in ("HOME", "USERPROFILE"):
        value = os.environ.get(name)
        if value and Path(value).is_absolute():
            return Path(value)
    return None


__all__ = [
    "MARKETPLACE_MANIFEST_RELATIVE_PATHS",
    "Marketplace",
    "MarketplaceError",
    "MarketplaceInterface",
    "MarketplaceListError",
    "MarketplaceListOutcome",
    "MarketplacePlugin",
    "MarketplacePluginAuthPolicy",
    "MarketplacePluginInstallPolicy",
    "MarketplacePluginPolicy",
    "MarketplacePluginSource",
    "ResolvedMarketplacePlugin",
    "find_installable_marketplace_plugin",
    "find_marketplace_manifest_path",
    "find_marketplace_plugin",
    "list_marketplaces",
    "list_marketplaces_with_home",
    "load_marketplace",
    "marketplace_root_dir",
    "plugin_interface_with_marketplace_category",
    "validate_marketplace_root",
]
