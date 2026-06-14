"""Behavior port for Rust ``codex-tui::updates``.

This module owns the release-update cache used by the TUI.  Python mirrors the
local cache/dismissal/version-selection semantics and keeps remote HTTP access
behind explicit injected callables rather than silently performing network I/O.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from ._porting import RustTuiModule
from .update_action import UpdateAction
from .update_versions import extract_version_from_latest_tag, is_newer, is_source_build_version
from .version import CODEX_CLI_VERSION

RUST_MODULE = RustTuiModule(crate="codex-tui", module="updates", source="codex/codex-rs/tui/src/updates.rs")

VERSION_FILENAME = "version.json"
HOMEBREW_CASK_API_URL = "https://formulae.brew.sh/api/cask/codex.json"
LATEST_RELEASE_URL = "https://api.github.com/repos/openai/codex/releases/latest"
NPM_PACKAGE_URL = "https://registry.npmjs.org/@openai/codex"
STALE_AFTER = timedelta(hours=20)


@dataclass(frozen=True)
class VersionInfo:
    latest_version: str
    last_checked_at: datetime
    dismissed_version: str | None = None

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> "VersionInfo":
        latest = mapping.get("latest_version")
        if not isinstance(latest, str):
            raise TypeError("latest_version must be a string")
        checked = _parse_datetime(mapping.get("last_checked_at"))
        dismissed = mapping.get("dismissed_version")
        if dismissed is not None and not isinstance(dismissed, str):
            raise TypeError("dismissed_version must be a string or null")
        return cls(latest_version=latest, last_checked_at=checked, dismissed_version=dismissed)

    def to_mapping(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "latest_version": self.latest_version,
            "last_checked_at": _format_datetime(self.last_checked_at),
        }
        if self.dismissed_version is not None:
            data["dismissed_version"] = self.dismissed_version
        return data


@dataclass(frozen=True)
class ReleaseInfo:
    tag_name: str


@dataclass(frozen=True)
class HomebrewCaskInfo:
    version: str


JsonGetter = Callable[[str], dict[str, Any] | Awaitable[dict[str, Any]]]
BackgroundScheduler = Callable[[Path, UpdateAction | None], Any]


def get_upgrade_version(
    config: Any,
    *,
    now: datetime | None = None,
    current_version: str = CODEX_CLI_VERSION,
    action: UpdateAction | None = None,
    background_scheduler: BackgroundScheduler | None = None,
) -> str | None:
    if not _check_for_update_on_startup(config) or is_source_build_version(current_version):
        return None

    now = _utc(now)
    version_file = version_filepath(config)
    try:
        info = read_version_info(version_file)
    except Exception:
        info = None

    if info is None or info.last_checked_at < now - STALE_AFTER:
        if background_scheduler is not None:
            background_scheduler(version_file, action)

    if info is not None and is_newer(info.latest_version, current_version) is True:
        return info.latest_version
    return None


def version_filepath(config: Any) -> Path:
    return _codex_home(config) / VERSION_FILENAME


def read_version_info(version_file: str | Path) -> VersionInfo:
    contents = Path(version_file).read_text(encoding="utf-8")
    return VersionInfo.from_mapping(json.loads(contents))


async def check_for_update(
    version_file: str | Path,
    action: UpdateAction | None,
    *,
    json_getter: JsonGetter | None = None,
    ensure_version_ready: Callable[[dict[str, Any], str], Any] | None = None,
    now: datetime | None = None,
) -> None:
    latest_version = await fetch_latest_version_for_action(
        action,
        json_getter=json_getter,
        ensure_version_ready=ensure_version_ready,
    )

    path = Path(version_file)
    try:
        prev_info = read_version_info(path)
        dismissed = prev_info.dismissed_version
    except Exception:
        dismissed = None

    info = VersionInfo(latest_version=latest_version, last_checked_at=_utc(now), dismissed_version=dismissed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info.to_mapping(), separators=(",", ":")) + "\n", encoding="utf-8")


async def fetch_latest_version_for_action(
    action: UpdateAction | None,
    *,
    json_getter: JsonGetter | None = None,
    ensure_version_ready: Callable[[dict[str, Any], str], Any] | None = None,
) -> str:
    if action is UpdateAction.BREW_UPGRADE:
        data = await _get_json(json_getter, HOMEBREW_CASK_API_URL)
        version = data.get("version")
        if not isinstance(version, str):
            raise ValueError("Homebrew cask response did not contain a string version")
        return version

    if action in {UpdateAction.NPM_GLOBAL_LATEST, UpdateAction.BUN_GLOBAL_LATEST}:
        latest_version = await fetch_latest_github_release_version(json_getter=json_getter)
        package_info = await _get_json(json_getter, NPM_PACKAGE_URL)
        if ensure_version_ready is None:
            raise NotImplementedError("npm_registry::ensure_version_ready is not wired for pycodex.tui.updates")
        result = ensure_version_ready(package_info, latest_version)
        if hasattr(result, "__await__"):
            await result
        return latest_version

    return await fetch_latest_github_release_version(json_getter=json_getter)


async def fetch_latest_github_release_version(*, json_getter: JsonGetter | None = None) -> str:
    data = await _get_json(json_getter, LATEST_RELEASE_URL)
    tag_name = data.get("tag_name")
    if not isinstance(tag_name, str):
        raise ValueError("GitHub release response did not contain a string tag_name")
    return extract_version_from_latest_tag(tag_name)


def get_upgrade_version_for_popup(
    config: Any,
    *,
    now: datetime | None = None,
    current_version: str = CODEX_CLI_VERSION,
    action: UpdateAction | None = None,
    background_scheduler: BackgroundScheduler | None = None,
) -> str | None:
    if not _check_for_update_on_startup(config) or is_source_build_version(current_version):
        return None

    version_file = version_filepath(config)
    latest = get_upgrade_version(
        config,
        now=now,
        current_version=current_version,
        action=action,
        background_scheduler=background_scheduler,
    )
    if latest is None:
        return None
    try:
        info = read_version_info(version_file)
    except Exception:
        return latest
    if info.dismissed_version == latest:
        return None
    return latest


async def dismiss_version(config: Any, version: str) -> None:
    version_file = version_filepath(config)
    try:
        info = read_version_info(version_file)
    except Exception:
        return

    updated = VersionInfo(
        latest_version=info.latest_version,
        last_checked_at=info.last_checked_at,
        dismissed_version=str(version),
    )
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text(json.dumps(updated.to_mapping(), separators=(",", ":")) + "\n", encoding="utf-8")


async def _get_json(json_getter: JsonGetter | None, url: str) -> dict[str, Any]:
    if json_getter is None:
        raise NotImplementedError("remote update HTTP client is not wired for pycodex.tui.updates")
    value = json_getter(url)
    if hasattr(value, "__await__"):
        value = await value
    if not isinstance(value, dict):
        raise TypeError("json_getter must return a JSON object mapping")
    return value


def _check_for_update_on_startup(config: Any) -> bool:
    if isinstance(config, dict):
        return bool(config.get("check_for_update_on_startup", False))
    return bool(getattr(config, "check_for_update_on_startup", False))


def _codex_home(config: Any) -> Path:
    if isinstance(config, dict):
        home = config.get("codex_home")
    else:
        home = getattr(config, "codex_home", None)
    if home is None:
        raise AttributeError("config must provide codex_home")
    return Path(home)


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _utc(value)
    if not isinstance(value, str):
        raise TypeError("last_checked_at must be an RFC3339 timestamp string")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    return _utc(datetime.fromisoformat(text))


def _format_datetime(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "HOMEBREW_CASK_API_URL",
    "HomebrewCaskInfo",
    "LATEST_RELEASE_URL",
    "NPM_PACKAGE_URL",
    "RUST_MODULE",
    "ReleaseInfo",
    "STALE_AFTER",
    "VERSION_FILENAME",
    "VersionInfo",
    "check_for_update",
    "dismiss_version",
    "fetch_latest_github_release_version",
    "fetch_latest_version_for_action",
    "get_upgrade_version",
    "get_upgrade_version_for_popup",
    "read_version_info",
    "version_filepath",
]
