from __future__ import annotations

import json
from pathlib import Path

import pytest

from pycodex.app_server_protocol import (
    PluginAuthPolicy,
    PluginAvailability,
    PluginInstallPolicy,
)


def test_remote_plugin_id_validation_matches_rust_character_set() -> None:
    from pycodex.core_plugins.remote import (
        InvalidRemotePluginIdError,
        is_valid_remote_plugin_id,
        validate_remote_plugin_id,
    )

    for value in ("plugin", "a-b_c~1", "A0"):
        assert is_valid_remote_plugin_id(value)
        validate_remote_plugin_id(value)

    for value in ("", "a.b", "a/b", "空"):
        assert not is_valid_remote_plugin_id(value)
        with pytest.raises(InvalidRemotePluginIdError):
            validate_remote_plugin_id(value)


def test_group_remote_installed_plugins_filters_scopes_and_orders_marketplaces() -> None:
    from pycodex.core_plugins.remote import (
        REMOTE_GLOBAL_MARKETPLACE_NAME,
        REMOTE_WORKSPACE_MARKETPLACE_NAME,
        RemoteInstalledPlugin,
        RemotePluginScope,
        group_remote_installed_plugins_by_marketplaces,
    )

    plugins = [
        RemoteInstalledPlugin(
            marketplace_name=REMOTE_WORKSPACE_MARKETPLACE_NAME,
            id="remote-z",
            name="zulu",
            enabled=True,
            install_policy=PluginInstallPolicy.AVAILABLE,
            auth_policy=PluginAuthPolicy.ON_USE,
            availability=PluginAvailability.AVAILABLE,
        ),
        RemoteInstalledPlugin(
            marketplace_name=REMOTE_GLOBAL_MARKETPLACE_NAME,
            id="remote-b",
            name="bravo",
            enabled=False,
            install_policy=PluginInstallPolicy.INSTALLED_BY_DEFAULT,
            auth_policy=PluginAuthPolicy.ON_INSTALL,
            availability=PluginAvailability.AVAILABLE,
        ),
    ]

    marketplaces = group_remote_installed_plugins_by_marketplaces(
        plugins,
        [RemotePluginScope.GLOBAL],
    )
    assert [marketplace.name for marketplace in marketplaces] == [
        REMOTE_GLOBAL_MARKETPLACE_NAME
    ]
    assert marketplaces[0].plugins[0].id == "bravo@openai-curated-remote"
    assert marketplaces[0].plugins[0].remote_plugin_id == "remote-b"


def test_local_share_path_mapping_round_trips_and_removes_empty_file(
    tmp_path: Path,
) -> None:
    from pycodex.core_plugins.remote.share.local_paths import (
        load_plugin_share_local_paths,
        record_plugin_share_local_path,
        remove_plugin_share_local_path,
    )

    plugin_path = (tmp_path / "plugins" / "demo").resolve()
    record_plugin_share_local_path(tmp_path, "remote-1", plugin_path)
    assert load_plugin_share_local_paths(tmp_path) == {"remote-1": plugin_path}

    mapping_file = tmp_path / ".tmp" / "plugin-share-local-paths-v1.json"
    payload = json.loads(mapping_file.read_text(encoding="utf-8"))
    assert payload["localPluginPathsByRemotePluginId"]["remote-1"] == str(plugin_path)

    remove_plugin_share_local_path(tmp_path, "remote-1")
    assert not mapping_file.exists()


def test_malformed_local_share_mapping_is_reset_on_update(tmp_path: Path) -> None:
    from pycodex.core_plugins.remote.share.local_paths import (
        load_plugin_share_local_paths,
        record_plugin_share_local_path,
    )

    mapping_file = tmp_path / ".tmp" / "plugin-share-local-paths-v1.json"
    mapping_file.parent.mkdir(parents=True)
    mapping_file.write_text("{bad", encoding="utf-8")

    with pytest.raises(ValueError):
        load_plugin_share_local_paths(tmp_path)

    plugin_path = (tmp_path / "plugins" / "demo").resolve()
    record_plugin_share_local_path(tmp_path, "remote-1", plugin_path)
    assert load_plugin_share_local_paths(tmp_path) == {"remote-1": plugin_path}


@pytest.mark.asyncio
async def test_fetch_remote_installed_plugins_pages_both_scopes_and_sorts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust: core-plugins/src/remote.rs::fetch_remote_installed_plugins.
    from pycodex.core_plugins import remote

    calls: list[dict[str, object]] = []

    async def request_json(config, auth, path, query):
        calls.append(dict(query))
        scope = str(query["scope"])
        page = query.get("pageToken")
        if scope == "GLOBAL":
            return {
                "plugins": [
                    {
                        "id": "remote-z",
                        "name": "zulu",
                        "scope": "GLOBAL",
                        "installation_policy": "AVAILABLE",
                        "authentication_policy": "ON_USE",
                        "status": "AVAILABLE",
                        "enabled": True,
                        "release": {
                            "display_name": "Zulu",
                            "description": "z",
                            "keywords": ["z"],
                            "interface": {},
                        },
                    }
                ],
                "pagination": {"next_page_token": "next" if page is None else None},
            } if page is None else {
                "plugins": [],
                "pagination": {"next_page_token": None},
            }
        return {
            "plugins": [
                {
                    "id": "remote-a",
                    "name": "alpha",
                    "scope": "WORKSPACE",
                    "discoverability": "LISTED",
                    "installation_policy": "INSTALLED_BY_DEFAULT",
                    "authentication_policy": "ON_INSTALL",
                    "status": "ENABLED",
                    "enabled": False,
                    "release": {
                        "display_name": "Alpha",
                        "description": "a",
                        "keywords": [],
                        "interface": {},
                    },
                }
            ],
            "pagination": {"next_page_token": None},
        }

    monkeypatch.setattr(remote, "_request_json", request_json)
    plugins = await remote.fetch_remote_installed_plugins(
        remote.RemotePluginServiceConfig("https://chatgpt.example/backend-api"),
        {"uses_codex_backend": True, "access_token": "token"},
    )

    assert [plugin.name for plugin in plugins] == ["zulu", "alpha"]
    assert [plugin.marketplace_name for plugin in plugins] == [
        remote.REMOTE_GLOBAL_MARKETPLACE_NAME,
        remote.REMOTE_WORKSPACE_MARKETPLACE_NAME,
    ]
    assert plugins[1].availability is PluginAvailability.AVAILABLE
    assert calls == [
        {"scope": "GLOBAL"},
        {"scope": "GLOBAL", "pageToken": "next"},
        {"scope": "WORKSPACE"},
    ]
