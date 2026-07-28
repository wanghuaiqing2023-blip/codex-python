"""Checkout a remote shared plugin into the personal marketplace.

Rust owner: ``codex-core-plugins::remote::share::checkout``.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.app_server_protocol import PluginAuthPolicy, PluginInstallPolicy
from pycodex.plugin import PluginId, PluginIdError

from .local_paths import (
    load_plugin_share_local_paths,
    record_plugin_share_local_path,
)

PERSONAL_MARKETPLACE_NAME = "codex-curated"
PERSONAL_MARKETPLACE_DISPLAY_NAME = "Personal"
PERSONAL_MARKETPLACE_RELATIVE_PATH = ".agents/plugins/marketplace.json"


class InvalidCheckoutPathError(RuntimeError):
    pass


@dataclass(frozen=True)
class RemotePluginShareCheckoutResult:
    remote_plugin_id: str
    plugin_id: str
    plugin_name: str
    plugin_path: Path
    marketplace_name: str
    marketplace_path: Path
    remote_version: str | None


@dataclass(frozen=True)
class PersonalMarketplaceUpdate:
    name: str
    path: Path


async def checkout_remote_plugin_share(
    codex_home: Path,
    config: Any,
    auth: Any,
    remote_plugin_id: str,
    *,
    fetch_detail: Any | None = None,
    extract_bundle: Any | None = None,
    home: Path | None = None,
) -> RemotePluginShareCheckoutResult:
    from .. import (
        REMOTE_WORKSPACE_SHARED_WITH_ME_MARKETPLACE_NAME,
        REMOTE_WORKSPACE_SHARED_WITH_ME_PRIVATE_MARKETPLACE_NAME,
        REMOTE_WORKSPACE_SHARED_WITH_ME_UNLISTED_MARKETPLACE_NAME,
        fetch_remote_plugin_detail,
    )
    from ...remote_bundle import (
        download_and_extract_remote_plugin_bundle_to_path,
        validate_remote_plugin_bundle,
    )

    detail_fetcher = fetch_detail or fetch_remote_plugin_detail
    detail = await detail_fetcher(
        config,
        auth,
        REMOTE_WORKSPACE_SHARED_WITH_ME_PRIVATE_MARKETPLACE_NAME,
        remote_plugin_id,
    )
    marketplace_name = str(_field(detail, "marketplace_name", ""))
    share_context = _field(_field(detail, "summary", {}), "share_context", None)
    if marketplace_name not in {
        REMOTE_WORKSPACE_SHARED_WITH_ME_MARKETPLACE_NAME,
        REMOTE_WORKSPACE_SHARED_WITH_ME_PRIVATE_MARKETPLACE_NAME,
        REMOTE_WORKSPACE_SHARED_WITH_ME_UNLISTED_MARKETPLACE_NAME,
    } or share_context is None:
        raise InvalidCheckoutPathError(
            f"remote plugin `{remote_plugin_id}` is not available for plugin/share/checkout"
        )

    summary = _field(detail, "summary", {})
    plugin_name = str(_field(summary, "name", ""))
    remote_version = _field(detail, "release_version", None)
    checkout_home = (home or Path.home()).resolve()
    mappings = _load_paths_best_effort(Path(codex_home))
    existing = mappings.get(remote_plugin_id)
    if existing is not None and existing.exists():
        local_path = existing
        already_checked_out = True
    else:
        local_path = existing or checkout_home / "plugins" / plugin_name
        already_checked_out = False
        if local_path.exists():
            raise InvalidCheckoutPathError(
                f"cannot check out remote plugin `{remote_plugin_id}` because "
                "the local plugin path already exists"
            )
    personal_marketplace_relative_plugin_path(checkout_home, local_path)

    created_path = False
    try:
        if not already_checked_out:
            bundle = validate_remote_plugin_bundle(
                remote_plugin_id,
                marketplace_name,
                plugin_name,
                remote_version,
                _field(detail, "bundle_download_url", None),
                None,
            )
            extractor = extract_bundle or download_and_extract_remote_plugin_bundle_to_path
            await extractor(bundle, local_path)
            created_path = True

        marketplace = update_personal_marketplace(
            checkout_home,
            plugin_name,
            local_path,
            _field(summary, "install_policy", PluginInstallPolicy.AVAILABLE),
            _field(summary, "auth_policy", PluginAuthPolicy.ON_USE),
            _interface_category(_field(summary, "interface", None)),
        )
        record_plugin_share_local_path(
            Path(codex_home),
            remote_plugin_id,
            local_path,
        )
    except BaseException:
        if created_path:
            if local_path.is_dir():
                shutil.rmtree(local_path, ignore_errors=True)
            elif local_path.exists():
                local_path.unlink()
        raise

    try:
        plugin_id = PluginId.parse(f"{plugin_name}@{marketplace.name}").as_key()
    except PluginIdError as exc:
        raise InvalidCheckoutPathError(
            f"failed to build checked out plugin id: {exc}"
        ) from exc
    return RemotePluginShareCheckoutResult(
        remote_plugin_id=remote_plugin_id,
        plugin_id=plugin_id,
        plugin_name=plugin_name,
        plugin_path=local_path,
        marketplace_name=marketplace.name,
        marketplace_path=marketplace.path,
        remote_version=remote_version,
    )


def update_personal_marketplace(
    home: Path,
    plugin_name: str,
    local_plugin_path: Path,
    install_policy: PluginInstallPolicy,
    auth_policy: PluginAuthPolicy,
    category: str | None,
) -> PersonalMarketplaceUpdate:
    home = Path(home).resolve()
    local_plugin_path = Path(local_plugin_path).resolve()
    marketplace_path = home / PERSONAL_MARKETPLACE_RELATIVE_PATH
    relative_path = personal_marketplace_relative_plugin_path(home, local_plugin_path)
    marketplace = _read_or_create_personal_marketplace(marketplace_path)
    if not isinstance(marketplace, dict):
        raise InvalidCheckoutPathError(
            "personal marketplace file must contain a JSON object"
        )

    marketplace_name = marketplace.setdefault("name", PERSONAL_MARKETPLACE_NAME)
    if not isinstance(marketplace_name, str) or not marketplace_name:
        raise InvalidCheckoutPathError("marketplace name must be a string")
    plugins = marketplace.setdefault("plugins", [])
    if not isinstance(plugins, list):
        raise InvalidCheckoutPathError("marketplace plugins must be an array")

    entry: dict[str, Any] = {
        "name": plugin_name,
        "source": {"source": "local", "path": relative_path},
        "policy": {
            "installation": _enum_value(install_policy),
            "authentication": _enum_value(auth_policy),
        },
    }
    if category is not None and category.strip():
        entry["category"] = category

    existing = next(
        (
            item
            for item in plugins
            if isinstance(item, dict) and item.get("name") == plugin_name
        ),
        None,
    )
    if existing is not None:
        source = existing.get("source")
        existing_path = source.get("path") if isinstance(source, dict) else None
        if existing_path != relative_path:
            raise InvalidCheckoutPathError(
                f"marketplace already contains plugin `{plugin_name}` with a "
                "different source path"
            )
        existing.clear()
        existing.update(entry)
    else:
        plugins.append(entry)

    _write_json_atomically(marketplace_path, marketplace)
    return PersonalMarketplaceUpdate(marketplace_name, marketplace_path)


def personal_marketplace_relative_plugin_path(
    home: Path,
    local_plugin_path: Path,
) -> str:
    home = Path(home).resolve()
    local_plugin_path = Path(local_plugin_path).resolve()
    try:
        relative = local_plugin_path.relative_to(home)
    except ValueError as exc:
        raise InvalidCheckoutPathError(
            "local plugin path must be inside the home directory to be listed "
            "in the personal marketplace"
        ) from exc
    if not relative.parts:
        raise InvalidCheckoutPathError(
            "local plugin path must not be the home directory"
        )
    return f"./{relative.as_posix()}"


def _read_or_create_personal_marketplace(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "name": PERSONAL_MARKETPLACE_NAME,
            "interface": {"displayName": PERSONAL_MARKETPLACE_DISPLAY_NAME},
            "plugins": [],
        }
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidCheckoutPathError(
            f"failed to parse personal marketplace file: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise InvalidCheckoutPathError(
            "personal marketplace file must contain a JSON object"
        )
    return value


def _write_json_atomically(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(contents)
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _load_paths_best_effort(codex_home: Path) -> dict[str, Path]:
    try:
        return load_plugin_share_local_paths(codex_home)
    except ValueError:
        return {}


def _field(value: Any, name: str, default: Any) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _interface_category(interface: Any) -> str | None:
    category = _field(interface, "category", None)
    return category if isinstance(category, str) else None


__all__ = [
    "InvalidCheckoutPathError",
    "PERSONAL_MARKETPLACE_DISPLAY_NAME",
    "PERSONAL_MARKETPLACE_NAME",
    "PERSONAL_MARKETPLACE_RELATIVE_PATH",
    "PersonalMarketplaceUpdate",
    "RemotePluginShareCheckoutResult",
    "checkout_remote_plugin_share",
    "personal_marketplace_relative_plugin_path",
    "update_personal_marketplace",
]
