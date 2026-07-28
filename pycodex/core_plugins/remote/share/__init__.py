"""Remote plugin sharing models and operations.

Rust owner: ``codex-core-plugins::remote::share``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.core_plugins.plugin_bundle_archive import pack_plugin_bundle_tar_gz

from .checkout import RemotePluginShareCheckoutResult
from .checkout import checkout_remote_plugin_share
from .local_paths import load_plugin_share_local_paths
from .local_paths import record_plugin_share_local_path
from .local_paths import remove_plugin_share_local_path

REMOTE_PLUGIN_SHARE_MAX_ARCHIVE_BYTES = 50 * 1024 * 1024


class RemotePluginShareDiscoverability(str, Enum):
    LISTED = "LISTED"
    UNLISTED = "UNLISTED"
    PRIVATE = "PRIVATE"


class RemotePluginShareUpdateDiscoverability(str, Enum):
    UNLISTED = "UNLISTED"
    PRIVATE = "PRIVATE"


class RemotePluginSharePrincipalType(str, Enum):
    USER = "user"
    GROUP = "group"
    WORKSPACE = "workspace"


class RemotePluginShareTargetRole(str, Enum):
    READER = "reader"
    EDITOR = "editor"


class RemotePluginSharePrincipalRole(str, Enum):
    READER = "reader"
    EDITOR = "editor"
    OWNER = "owner"


@dataclass(frozen=True)
class RemotePluginShareTarget:
    principal_type: RemotePluginSharePrincipalType
    principal_id: str
    role: RemotePluginShareTargetRole


@dataclass(frozen=True)
class RemotePluginSharePrincipal:
    principal_type: RemotePluginSharePrincipalType
    principal_id: str
    role: RemotePluginSharePrincipalRole
    name: str


@dataclass(frozen=True)
class RemotePluginShareSaveResult:
    remote_plugin_id: str
    share_url: str | None


@dataclass(frozen=True)
class RemotePluginShareAccessPolicy:
    discoverability: RemotePluginShareDiscoverability
    principals: tuple[RemotePluginSharePrincipal, ...] = ()


@dataclass(frozen=True)
class RemotePluginShareUpdateTargetsResult:
    remote_plugin_id: str
    discoverability: RemotePluginShareDiscoverability
    principals: tuple[RemotePluginSharePrincipal, ...] = ()


def archive_plugin_for_upload(
    plugin_path: Path,
    max_bytes: int = REMOTE_PLUGIN_SHARE_MAX_ARCHIVE_BYTES,
) -> bytes:
    return pack_plugin_bundle_tar_gz(Path(plugin_path), max_bytes)


async def save_remote_plugin_share(*args: Any, **kwargs: Any) -> Any:
    transport = kwargs.pop("transport", None)
    if transport is None:
        raise RuntimeError("remote plugin share transport is required")
    return await transport.save_remote_plugin_share(*args, **kwargs)


async def list_remote_plugin_shares(*args: Any, **kwargs: Any) -> Any:
    transport = kwargs.pop("transport", None)
    if transport is None:
        raise RuntimeError("remote plugin share transport is required")
    return await transport.list_remote_plugin_shares(*args, **kwargs)


async def delete_remote_plugin_share(*args: Any, **kwargs: Any) -> Any:
    transport = kwargs.pop("transport", None)
    if transport is None:
        raise RuntimeError("remote plugin share transport is required")
    return await transport.delete_remote_plugin_share(*args, **kwargs)


async def update_remote_plugin_share_targets(*args: Any, **kwargs: Any) -> Any:
    transport = kwargs.pop("transport", None)
    if transport is None:
        raise RuntimeError("remote plugin share transport is required")
    return await transport.update_remote_plugin_share_targets(*args, **kwargs)


def load_plugin_share_remote_ids_by_local_path(
    codex_home: Path,
) -> dict[Path, str]:
    return {
        plugin_path: remote_id
        for remote_id, plugin_path in load_plugin_share_local_paths(codex_home).items()
    }


__all__ = [
    "REMOTE_PLUGIN_SHARE_MAX_ARCHIVE_BYTES",
    "RemotePluginShareAccessPolicy",
    "RemotePluginShareCheckoutResult",
    "RemotePluginShareDiscoverability",
    "RemotePluginSharePrincipal",
    "RemotePluginSharePrincipalRole",
    "RemotePluginSharePrincipalType",
    "RemotePluginShareSaveResult",
    "RemotePluginShareTarget",
    "RemotePluginShareTargetRole",
    "RemotePluginShareUpdateDiscoverability",
    "RemotePluginShareUpdateTargetsResult",
    "archive_plugin_for_upload",
    "checkout_remote_plugin_share",
    "delete_remote_plugin_share",
    "list_remote_plugin_shares",
    "load_plugin_share_remote_ids_by_local_path",
    "record_plugin_share_local_path",
    "remove_plugin_share_local_path",
    "save_remote_plugin_share",
    "update_remote_plugin_share_targets",
]
