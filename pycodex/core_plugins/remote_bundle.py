"""Remote plugin bundle validation, download, extraction, and installation.

Rust owner: ``codex-core-plugins::remote_bundle``.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pycodex.plugin import PluginId, PluginIdError
from pycodex.utils.plugins import find_plugin_manifest_path

from .manifest import load_plugin_manifest
from .plugin_bundle_archive import (
    ExtractedBundleTooLargeError,
    InvalidPluginBundleError,
    PluginBundleUnpackError,
    unpack_plugin_bundle_tar_gz,
)
from .remote import REMOTE_GLOBAL_MARKETPLACE_NAME
from .store import (
    PluginInstallResult,
    PluginStore,
    PluginStoreError,
    validate_plugin_version_segment,
)

REMOTE_PLUGIN_BUNDLE_DOWNLOAD_TIMEOUT = 60
REMOTE_PLUGIN_BUNDLE_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
REMOTE_PLUGIN_BUNDLE_ERROR_BODY_MAX_BYTES = 8 * 1024
REMOTE_PLUGIN_BUNDLE_MAX_EXTRACTED_BYTES = 250 * 1024 * 1024
REMOTE_PLUGIN_INSTALL_STAGING_DIR = "plugins/.remote-plugin-install-staging"
TEST_ALLOW_LOOPBACK_HTTP_REMOTE_PLUGIN_BUNDLES_ENV = (
    "CODEX_TEST_ALLOW_HTTP_REMOTE_PLUGIN_BUNDLE_DOWNLOADS"
)


class RemotePluginBundleInstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class ValidatedRemotePluginBundle:
    plugin_id: PluginId
    plugin_version: str
    app_manifest: Any | None
    bundle_download_url: str


def validate_remote_plugin_bundle(
    remote_plugin_id: str,
    remote_marketplace_name: str,
    plugin_name: str,
    release_version: str | None,
    bundle_download_url: str | None,
    app_manifest: Any | None,
) -> ValidatedRemotePluginBundle:
    try:
        plugin_id = PluginId.parse(f"{plugin_name}@{remote_marketplace_name}")
    except PluginIdError as exc:
        raise RemotePluginBundleInstallError(
            f"backend returned an invalid local plugin id for remote plugin "
            f"`{remote_plugin_id}`: {exc}"
        ) from exc

    plugin_version = (release_version or "").strip()
    if not plugin_version:
        raise RemotePluginBundleInstallError(
            f"backend did not return a release version for remote plugin "
            f"`{remote_plugin_id}`"
        )
    try:
        validate_plugin_version_segment(plugin_version)
    except PluginStoreError as exc:
        raise RemotePluginBundleInstallError(
            f"backend returned an invalid release version for remote plugin "
            f"`{remote_plugin_id}`: {exc}"
        ) from exc

    download_url = (bundle_download_url or "").strip()
    if not download_url:
        raise RemotePluginBundleInstallError(
            f"backend did not return a download URL for remote plugin "
            f"`{remote_plugin_id}`"
        )
    parsed = urlsplit(download_url)
    if not parsed.scheme or (
        parsed.scheme in {"http", "https"} and not parsed.netloc
    ):
        raise RemotePluginBundleInstallError(
            f"backend returned an invalid download URL for remote plugin "
            f"`{remote_plugin_id}`: {download_url}"
        )
    if not _is_allowed_bundle_download_url(parsed):
        raise RemotePluginBundleInstallError(
            f"backend returned an unsupported download URL scheme for remote "
            f"plugin `{remote_plugin_id}`: {parsed.scheme}"
        )

    return ValidatedRemotePluginBundle(
        plugin_id=plugin_id,
        plugin_version=plugin_version,
        app_manifest=app_manifest,
        bundle_download_url=download_url,
    )


def _is_allowed_bundle_download_url(parsed: Any) -> bool:
    if parsed.scheme == "https":
        return True
    return (
        parsed.scheme == "http"
        and os.environ.get(
            TEST_ALLOW_LOOPBACK_HTTP_REMOTE_PLUGIN_BUNDLES_ENV
        )
        == "1"
        and _is_loopback_host(parsed.hostname)
    )


def _is_loopback_host(hostname: str | None) -> bool:
    if hostname is None:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


async def download_and_install_remote_plugin_bundle(
    codex_home: Path,
    bundle: ValidatedRemotePluginBundle,
) -> PluginInstallResult:
    contents = await _download_remote_plugin_bundle_with_limit(
        bundle.bundle_download_url,
        REMOTE_PLUGIN_BUNDLE_MAX_DOWNLOAD_BYTES,
    )
    return await asyncio.to_thread(
        _install_remote_plugin_bundle,
        Path(codex_home),
        bundle,
        contents,
    )


async def download_and_extract_remote_plugin_bundle_to_path(
    bundle: ValidatedRemotePluginBundle,
    destination: Path,
) -> Path:
    contents = await _download_remote_plugin_bundle_with_limit(
        bundle.bundle_download_url,
        REMOTE_PLUGIN_BUNDLE_MAX_DOWNLOAD_BYTES,
    )
    return await asyncio.to_thread(
        _extract_remote_plugin_bundle_to_path,
        bundle,
        contents,
        Path(destination),
    )


async def _download_remote_plugin_bundle_with_limit(
    url: str,
    max_bytes: int,
) -> bytes:
    return await asyncio.to_thread(_download_sync, url, max_bytes)


def _download_sync(url: str, max_bytes: int) -> bytes:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(
            request,
            timeout=REMOTE_PLUGIN_BUNDLE_DOWNLOAD_TIMEOUT,
        ) as response:
            length = response.headers.get("Content-Length")
            if length is not None and int(length) > max_bytes:
                raise RemotePluginBundleInstallError(
                    f"remote plugin bundle download would be {int(length)} bytes, "
                    f"exceeding maximum size of {max_bytes} bytes"
                )
            result = bytearray()
            while chunk := response.read(min(64 * 1024, max_bytes + 1)):
                result.extend(chunk)
                if len(result) > max_bytes:
                    raise RemotePluginBundleInstallError(
                        f"remote plugin bundle download would be {len(result)} bytes, "
                        f"exceeding maximum size of {max_bytes} bytes"
                    )
            return bytes(result)
    except RemotePluginBundleInstallError:
        raise
    except urllib.error.HTTPError as exc:
        body = exc.read(REMOTE_PLUGIN_BUNDLE_ERROR_BODY_MAX_BYTES).decode(
            "utf-8",
            errors="replace",
        )
        raise RemotePluginBundleInstallError(
            f"remote plugin bundle request failed with status {exc.code}: {body}"
        ) from exc
    except OSError as exc:
        raise RemotePluginBundleInstallError(
            f"failed to download remote plugin bundle from {url}: {exc}"
        ) from exc


def _install_remote_plugin_bundle(
    codex_home: Path,
    bundle: ValidatedRemotePluginBundle,
    contents: bytes,
) -> PluginInstallResult:
    staging_parent = codex_home / REMOTE_PLUGIN_INSTALL_STAGING_DIR
    staging_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=staging_parent) as temp_dir:
        plugin_root = Path(temp_dir)
        _extract_plugin_bundle_tar_gz(contents, plugin_root)
        _prepare_extracted_remote_plugin_root(plugin_root, bundle)
        return PluginStore.try_new(codex_home.resolve()).install_with_version(
            plugin_root,
            bundle.plugin_id,
            bundle.plugin_version,
        )


def _extract_remote_plugin_bundle_to_path(
    bundle: ValidatedRemotePluginBundle,
    contents: bytes,
    destination: Path,
) -> Path:
    if destination.exists():
        raise RemotePluginBundleInstallError(
            f"remote plugin destination already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix=".remote-plugin-checkout-", dir=destination.parent)
    )
    try:
        _extract_plugin_bundle_tar_gz(contents, temp_dir)
        _prepare_extracted_remote_plugin_root(temp_dir, bundle)
        manifest = load_plugin_manifest(temp_dir)
        if manifest is None:
            raise RemotePluginBundleInstallError(
                "remote plugin bundle did not contain a valid plugin.json"
            )
        if manifest.name != bundle.plugin_id.plugin_name:
            raise RemotePluginBundleInstallError(
                f"plugin.json name `{manifest.name}` does not match remote plugin "
                f"name `{bundle.plugin_id.plugin_name}`"
            )
        temp_dir.replace(destination)
        return destination
    except BaseException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _prepare_extracted_remote_plugin_root(
    plugin_root: Path,
    bundle: ValidatedRemotePluginBundle,
) -> None:
    if bundle.plugin_id.marketplace_name != REMOTE_GLOBAL_MARKETPLACE_NAME:
        return
    _overwrite_plugin_manifest_version(plugin_root, bundle.plugin_version)
    if bundle.app_manifest is not None:
        manifest = load_plugin_manifest(plugin_root)
        app_path = (
            manifest.paths.apps
            if manifest is not None and manifest.paths.apps is not None
            else plugin_root / ".app.json"
        )
        _write_json_file(app_path, bundle.app_manifest)


def _overwrite_plugin_manifest_version(
    plugin_root: Path,
    plugin_version: str,
) -> None:
    manifest_path = find_plugin_manifest_path(plugin_root)
    if manifest_path is None:
        raise RemotePluginBundleInstallError(
            "remote plugin bundle did not contain a valid plugin.json"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RemotePluginBundleInstallError(
            f"failed to parse remote plugin manifest: {exc}"
        ) from exc
    if not isinstance(manifest, dict):
        raise RemotePluginBundleInstallError(
            "remote plugin manifest must be a JSON object"
        )
    manifest["version"] = plugin_version
    _write_json_file(manifest_path, manifest)


def _write_json_file(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _extract_plugin_bundle_tar_gz(contents: bytes, destination: Path) -> None:
    try:
        unpack_plugin_bundle_tar_gz(
            contents,
            destination,
            REMOTE_PLUGIN_BUNDLE_MAX_EXTRACTED_BYTES,
        )
    except (
        ExtractedBundleTooLargeError,
        InvalidPluginBundleError,
        PluginBundleUnpackError,
    ) as exc:
        raise RemotePluginBundleInstallError(str(exc)) from exc
    if find_plugin_manifest_path(destination) is None:
        raise RemotePluginBundleInstallError(
            "remote plugin bundle did not contain a standard plugin root "
            "with plugin.json"
        )


__all__ = [
    "REMOTE_PLUGIN_BUNDLE_MAX_DOWNLOAD_BYTES",
    "REMOTE_PLUGIN_BUNDLE_MAX_EXTRACTED_BYTES",
    "RemotePluginBundleInstallError",
    "ValidatedRemotePluginBundle",
    "download_and_extract_remote_plugin_bundle_to_path",
    "download_and_install_remote_plugin_bundle",
    "validate_remote_plugin_bundle",
]
