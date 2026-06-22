import asyncio
import json

from pycodex.app_server_protocol.apps import AppBranding, AppInfo
from pycodex.connectors import (
    ConnectorDirectoryCacheContext,
    ConnectorDirectoryCacheKey,
    DirectoryApp,
    DirectoryListResponse,
    cached_directory_connectors,
    list_all_connectors_with_options,
    list_directory_connectors,
)
from pycodex.connectors import _clear_directory_memory_cache_for_tests
from pycodex.connectors.filter import (
    filter_disallowed_connectors,
    filter_tool_suggest_discoverable_connectors,
)
from pycodex.connectors.merge import merge_connectors, plugin_connector_to_app_info
from pycodex.connectors.metadata import connector_install_url, connector_mention_slug


def app(connector_id: str, name: str | None = None, **updates) -> AppInfo:
    return AppInfo(
        id=connector_id,
        name=name or connector_id,
        description=updates.pop("description", None),
        logo_url=updates.pop("logo_url", None),
        logo_url_dark=updates.pop("logo_url_dark", None),
        distribution_channel=updates.pop("distribution_channel", None),
        install_url=updates.pop("install_url", None),
        branding=updates.pop("branding", None),
        app_metadata=updates.pop("app_metadata", None),
        labels=updates.pop("labels", None),
        is_accessible=updates.pop("is_accessible", False),
        is_enabled=updates.pop("is_enabled", True),
        plugin_display_names=tuple(updates.pop("plugin_display_names", ())),
    )


def directory_app(connector_id: str, name: str, **updates) -> DirectoryApp:
    return DirectoryApp(id=connector_id, name=name, **updates)


def cache_context(codex_home, suffix: str) -> ConnectorDirectoryCacheContext:
    return ConnectorDirectoryCacheContext(
        codex_home,
        ConnectorDirectoryCacheKey(
            "https://chatgpt.example",
            f"account-{suffix}",
            f"user-{suffix}",
            True,
        ),
    )


def test_filter_disallowed_connectors_allows_non_disallowed_connectors() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-connectors
    # Rust module: src/filter.rs
    # Rust test: filter_disallowed_connectors_allows_non_disallowed_connectors
    # Contract: ordinary connector ids are preserved.
    filtered = filter_disallowed_connectors(
        [app("asdk_app_hidden"), app("alpha")],
        "codex_cli",
    )
    assert filtered == [app("asdk_app_hidden"), app("alpha")]


def test_filter_disallowed_connectors_filters_disallowed_connector_ids() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-connectors
    # Rust module: src/filter.rs
    # Rust test: filter_disallowed_connectors_filters_disallowed_connector_ids
    # Contract: global disallowed ids are removed for normal originators.
    filtered = filter_disallowed_connectors(
        [
            app("asdk_app_6938a94a61d881918ef32cb999ff937c"),
            app("connector_3f8d1a79f27c4c7ba1a897ab13bf37dc"),
            app("delta"),
        ],
        "codex_cli",
    )
    assert filtered == [app("delta")]


def test_first_party_chat_originator_filters_target_connector_ids() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-connectors
    # Rust module: src/filter.rs
    # Rust test: first_party_chat_originator_filters_target_connector_ids
    # Contract: first-party chat originators use their narrower disallow list.
    filtered = filter_disallowed_connectors(
        [
            app("connector_openai_foo"),
            app("asdk_app_6938a94a61d881918ef32cb999ff937c"),
            app("connector_0f9c9d4592e54d0a9a12b3f44a1e2010"),
        ],
        "codex_atlas",
    )
    assert filtered == [
        app("connector_openai_foo"),
        app("asdk_app_6938a94a61d881918ef32cb999ff937c"),
    ]


def test_filter_tool_suggest_discoverable_connectors_keeps_uninstalled_plugin_backed_apps() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-connectors
    # Rust module: src/filter.rs
    # Rust test: filter_tool_suggest_discoverable_connectors_keeps_only_plugin_backed_uninstalled_apps
    # Contract: suggestions exclude accessible apps and ids outside the discoverable set.
    filtered = filter_tool_suggest_discoverable_connectors(
        [
            app(
                "connector_2128aebfecb84f64a069897515042a44",
                "Google Calendar",
                install_url=connector_install_url("Google Calendar", "connector_2128aebfecb84f64a069897515042a44"),
            ),
            app(
                "connector_68df038e0ba48191908c8434991bbac2",
                "Gmail",
                install_url=connector_install_url("Gmail", "connector_68df038e0ba48191908c8434991bbac2"),
            ),
            app("connector_other", "Other"),
        ],
        [
            app(
                "connector_2128aebfecb84f64a069897515042a44",
                "Google Calendar",
                is_accessible=True,
            )
        ],
        {
            "connector_2128aebfecb84f64a069897515042a44",
            "connector_68df038e0ba48191908c8434991bbac2",
        },
        "codex_cli",
    )
    assert [connector.id for connector in filtered] == ["connector_68df038e0ba48191908c8434991bbac2"]


def test_merge_connectors_replaces_plugin_placeholder_name_with_accessible_name() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-connectors
    # Rust module: src/merge.rs
    # Rust test: merge_connectors_replaces_plugin_placeholder_name_with_accessible_name
    # Contract: accessible metadata replaces placeholder name/metadata.
    merged = merge_connectors(
        [plugin_connector_to_app_info("calendar")],
        [
            app(
                "calendar",
                "Google Calendar",
                description="Plan events",
                logo_url="https://example.com/logo.png",
                logo_url_dark="https://example.com/logo-dark.png",
                distribution_channel="workspace",
                is_accessible=True,
            )
        ],
    )
    assert merged == [
        app(
            "calendar",
            "Google Calendar",
            description="Plan events",
            logo_url="https://example.com/logo.png",
            logo_url_dark="https://example.com/logo-dark.png",
            distribution_channel="workspace",
            install_url=connector_install_url("calendar", "calendar"),
            is_accessible=True,
        )
    ]
    assert connector_mention_slug(merged[0]) == "google-calendar"


def test_list_all_connectors_uses_shared_directory_cache(tmp_path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-connectors
    # Rust module: src/lib.rs
    # Rust test: list_all_connectors_uses_shared_directory_cache
    # Contract: unexpired matching in-memory directory cache bypasses fetch.
    _clear_directory_memory_cache_for_tests()
    calls = 0
    context = cache_context(tmp_path, "shared")

    async def first_fetch(_path: str) -> DirectoryListResponse:
        nonlocal calls
        calls += 1
        return DirectoryListResponse((directory_app("alpha", "Alpha"),))

    first = asyncio.run(list_all_connectors_with_options(context, False, False, first_fetch))

    async def second_fetch(_path: str) -> DirectoryListResponse:
        raise AssertionError("cache should have been used")

    second = asyncio.run(list_all_connectors_with_options(context, False, False, second_fetch))

    assert calls == 1
    assert first == second


def test_list_all_connectors_merges_and_normalizes_directory_apps(tmp_path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-connectors
    # Rust module: src/lib.rs
    # Rust test: list_all_connectors_merges_and_normalizes_directory_apps
    # Contract: directory/workspace pages merge duplicate apps and normalize display fields.
    _clear_directory_memory_cache_for_tests()
    context = cache_context(tmp_path, "merged")
    calls = 0

    async def fetch(path: str) -> DirectoryListResponse:
        nonlocal calls
        calls += 1
        if path.startswith("/connectors/directory/list_workspace"):
            return DirectoryListResponse(
                (
                    directory_app(
                        "alpha",
                        "",
                        description="Merged description",
                        branding=AppBranding(category="calendar", is_discoverable_app=True),
                    ),
                    directory_app("hidden", "Hidden", visibility="HIDDEN"),
                )
            )
        return DirectoryListResponse((directory_app("alpha", " Alpha "), directory_app("beta", "Beta")))

    connectors = asyncio.run(list_all_connectors_with_options(context, True, True, fetch))

    assert calls == 2
    assert len(connectors) == 2
    assert connectors[0].id == "alpha"
    assert connectors[0].name == "Alpha"
    assert connectors[0].description == "Merged description"
    assert connectors[0].install_url == "https://chatgpt.com/apps/alpha/alpha"
    assert connectors[0].branding is not None
    assert connectors[0].branding.category == "calendar"
    assert connectors[1].id == "beta"


def test_cached_directory_connectors_reads_directory_disk_cache(tmp_path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-connectors
    # Rust module: src/lib.rs + src/directory_cache.rs
    # Rust test: cached_directory_connectors_reads_directory_disk_cache
    # Contract: disk cache can repopulate memory after memory cache is cleared.
    _clear_directory_memory_cache_for_tests()
    context = cache_context(tmp_path, "disk")
    calls = 0

    async def fetch(_path: str) -> DirectoryListResponse:
        nonlocal calls
        calls += 1
        return DirectoryListResponse((directory_app("alpha", "Alpha"),))

    first = asyncio.run(list_all_connectors_with_options(context, False, False, fetch))
    _clear_directory_memory_cache_for_tests()

    second = cached_directory_connectors(context)

    assert calls == 1
    assert second == first


def test_list_all_connectors_refreshes_when_only_directory_disk_cache_exists(tmp_path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-connectors
    # Rust module: src/lib.rs + src/directory_cache.rs
    # Rust test: list_all_connectors_refreshes_when_only_directory_disk_cache_exists
    # Contract: disk-only cached connector is visible via cached read, but list_all refreshes.
    _clear_directory_memory_cache_for_tests()
    context = cache_context(tmp_path, "disk-refresh")
    calls = 0

    async def first_fetch(_path: str) -> DirectoryListResponse:
        nonlocal calls
        calls += 1
        return DirectoryListResponse((directory_app("alpha", "Alpha"),))

    asyncio.run(list_all_connectors_with_options(context, False, False, first_fetch))
    _clear_directory_memory_cache_for_tests()
    assert [connector.id for connector in cached_directory_connectors(context) or []] == ["alpha"]

    async def refreshed_fetch(_path: str) -> DirectoryListResponse:
        nonlocal calls
        calls += 1
        return DirectoryListResponse((directory_app("beta", "Beta"),))

    refreshed = asyncio.run(list_all_connectors_with_options(context, False, False, refreshed_fetch))

    assert calls == 2
    assert [connector.id for connector in refreshed] == ["beta"]


def test_cached_directory_connectors_drops_stale_disk_schema(tmp_path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-connectors
    # Rust module: src/lib.rs + src/directory_cache.rs
    # Rust test: cached_directory_connectors_drops_stale_disk_schema
    # Contract: stale schema returns no cache and removes the invalid file.
    _clear_directory_memory_cache_for_tests()
    context = cache_context(tmp_path, "stale-schema")
    cache_path = context.cache_path()
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(json.dumps({"schema_version": 0, "connectors": []}), encoding="utf-8")

    assert cached_directory_connectors(context) is None
    assert not cache_path.exists()


def test_list_directory_connectors_omits_tier_for_all_pages() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-connectors
    # Rust module: src/lib.rs
    # Rust test: list_directory_connectors_omits_tier_for_all_pages
    # Contract: page requests use external_logos and token only, never tier.
    requested_paths: list[str] = []

    async def fetch(path: str) -> DirectoryListResponse:
        requested_paths.append(path)
        if path == "/connectors/directory/list?external_logos=true":
            return DirectoryListResponse((directory_app("alpha", "Alpha"),), next_token="page 2")
        assert path == "/connectors/directory/list?token=page%202&external_logos=true"
        return DirectoryListResponse((directory_app("beta", "Beta"),))

    apps = asyncio.run(list_directory_connectors(fetch))

    assert [app.id for app in apps] == ["alpha", "beta"]
    assert requested_paths == [
        "/connectors/directory/list?external_logos=true",
        "/connectors/directory/list?token=page%202&external_logos=true",
    ]
