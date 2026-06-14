from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pycodex.tui.update_action import UpdateAction
from pycodex.tui.updates import (
    HOMEBREW_CASK_API_URL,
    LATEST_RELEASE_URL,
    NPM_PACKAGE_URL,
    VersionInfo,
    check_for_update,
    dismiss_version,
    fetch_latest_github_release_version,
    fetch_latest_version_for_action,
    get_upgrade_version,
    get_upgrade_version_for_popup,
    read_version_info,
    version_filepath,
)


@dataclass
class Config:
    codex_home: Path
    check_for_update_on_startup: bool = True


def _write_info(path: Path, latest: str, checked: datetime, dismissed: str | None = None) -> None:
    data = {"latest_version": latest, "last_checked_at": checked.isoformat().replace("+00:00", "Z")}
    if dismissed is not None:
        data["dismissed_version"] = dismissed
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")


def test_version_filepath_and_read_version_info(tmp_path: Path) -> None:
    config = Config(tmp_path)
    path = version_filepath(config)
    checked = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _write_info(path, "1.2.3", checked, "1.2.0")

    info = read_version_info(path)

    assert path == tmp_path / "version.json"
    assert info == VersionInfo("1.2.3", checked, "1.2.0")


def test_get_upgrade_version_respects_disabled_source_build_and_cached_newer(tmp_path: Path) -> None:
    config = Config(tmp_path)
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    _write_info(version_filepath(config), "1.2.4", now)

    assert get_upgrade_version(config, now=now, current_version="1.2.3") == "1.2.4"
    assert get_upgrade_version(Config(tmp_path, False), now=now, current_version="1.2.3") is None
    assert get_upgrade_version(config, now=now, current_version="0.0.0") is None


def test_get_upgrade_version_schedules_refresh_for_missing_or_stale_cache(tmp_path: Path) -> None:
    config = Config(tmp_path)
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    scheduled: list[tuple[Path, object]] = []

    assert get_upgrade_version(config, now=now, current_version="1.0.0", background_scheduler=lambda p, a: scheduled.append((p, a))) is None
    assert scheduled == [(version_filepath(config), None)]

    scheduled.clear()
    _write_info(version_filepath(config), "1.0.1", now - timedelta(hours=21))
    assert get_upgrade_version(config, now=now, current_version="1.0.0", background_scheduler=lambda p, a: scheduled.append((p, a))) == "1.0.1"
    assert scheduled == [(version_filepath(config), None)]


def test_get_upgrade_version_for_popup_honors_dismissed_version(tmp_path: Path) -> None:
    config = Config(tmp_path)
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    _write_info(version_filepath(config), "1.2.4", now, dismissed="1.2.4")

    assert get_upgrade_version_for_popup(config, now=now, current_version="1.2.3") is None

    _write_info(version_filepath(config), "1.2.5", now, dismissed="1.2.4")
    assert get_upgrade_version_for_popup(config, now=now, current_version="1.2.3") == "1.2.5"


def test_dismiss_version_updates_existing_cache_and_missing_cache_is_noop(tmp_path: Path) -> None:
    config = Config(tmp_path)
    checked = datetime(2026, 1, 1, tzinfo=timezone.utc)

    asyncio.run(dismiss_version(config, "1.2.4"))
    assert not version_filepath(config).exists()

    _write_info(version_filepath(config), "1.2.4", checked)
    asyncio.run(dismiss_version(config, "1.2.4"))

    assert read_version_info(version_filepath(config)) == VersionInfo("1.2.4", checked, "1.2.4")


def test_fetch_latest_github_release_version_extracts_rust_tag() -> None:
    async def getter(url: str) -> dict[str, str]:
        assert url == LATEST_RELEASE_URL
        return {"tag_name": "rust-v1.2.3"}

    assert asyncio.run(fetch_latest_github_release_version(json_getter=getter)) == "1.2.3"


def test_fetch_latest_version_for_action_uses_expected_remote_source() -> None:
    calls: list[str] = []

    async def getter(url: str) -> dict[str, object]:
        calls.append(url)
        if url == HOMEBREW_CASK_API_URL:
            return {"version": "2.0.0"}
        if url == LATEST_RELEASE_URL:
            return {"tag_name": "rust-v3.0.0"}
        if url == NPM_PACKAGE_URL:
            return {"versions": {"3.0.0": {}}}
        raise AssertionError(url)

    assert asyncio.run(fetch_latest_version_for_action(UpdateAction.BREW_UPGRADE, json_getter=getter)) == "2.0.0"
    assert calls == [HOMEBREW_CASK_API_URL]

    calls.clear()
    ensured: list[str] = []
    assert (
        asyncio.run(
            fetch_latest_version_for_action(
                UpdateAction.NPM_GLOBAL_LATEST,
                json_getter=getter,
                ensure_version_ready=lambda _package, version: ensured.append(version),
            )
        )
        == "3.0.0"
    )
    assert calls == [LATEST_RELEASE_URL, NPM_PACKAGE_URL]
    assert ensured == ["3.0.0"]


def test_check_for_update_writes_cache_and_preserves_dismissal(tmp_path: Path) -> None:
    checked = datetime(2026, 1, 1, tzinfo=timezone.utc)
    path = tmp_path / "version.json"
    _write_info(path, "1.0.0", checked, dismissed="1.0.0")

    async def getter(url: str) -> dict[str, str]:
        assert url == LATEST_RELEASE_URL
        return {"tag_name": "rust-v1.2.0"}

    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    asyncio.run(check_for_update(path, None, json_getter=getter, now=now))

    assert read_version_info(path) == VersionInfo("1.2.0", now, "1.0.0")
