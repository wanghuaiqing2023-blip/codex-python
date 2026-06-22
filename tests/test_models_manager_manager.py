import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from pycodex.models_manager import (
    CachedModelsManager,
    ModelsManagerConfig,
    OpenAiModelsManager,
    RefreshStrategy,
    StaticModelsManager,
    build_available_models,
    default_model_from_available,
    load_remote_models_from_file,
)
from pycodex.models_manager.model_info import model_info_from_slug
from pycodex.protocol import ModeKind, ModelVisibility, ModelsResponse


def visible_model(slug: str, *, priority: int = 1, supported_in_api: bool = True):
    return replace(
        model_info_from_slug(slug),
        visibility=ModelVisibility.LIST,
        priority=priority,
        supported_in_api=supported_in_api,
        used_fallback_model_metadata=False,
    )


def hidden_model(slug: str, *, priority: int = 1):
    return replace(
        visible_model(slug, priority=priority),
        visibility=ModelVisibility.HIDE,
    )


class FakeAuthManager:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def auth_mode(self) -> str:
        return self.mode

    def current_auth_uses_codex_backend(self) -> bool:
        return self.mode in {"chatgpt", "chatgpt_auth_tokens"}


class FakeEndpoint:
    def __init__(
        self,
        responses,
        *,
        has_command_auth: bool = False,
        uses_codex_backend: bool = True,
        etag: str | None = None,
    ) -> None:
        self.responses = list(responses)
        self.has_command_auth_value = has_command_auth
        self.uses_codex_backend_value = uses_codex_backend
        self.etag = etag
        self.client_versions: list[str] = []

    def has_command_auth(self) -> bool:
        return self.has_command_auth_value

    async def uses_codex_backend(self) -> bool:
        return self.uses_codex_backend_value

    async def list_models(self, client_version: str):
        self.client_versions.append(client_version)
        models = self.responses.pop(0) if self.responses else ()
        return list(models), self.etag


def test_refresh_strategy_values_match_rust_display() -> None:
    # Rust crate/module: codex-models-manager::manager
    assert str(RefreshStrategy.ONLINE) == "online"
    assert str(RefreshStrategy.OFFLINE) == "offline"
    assert str(RefreshStrategy.ONLINE_IF_UNCACHED) == "online_if_uncached"


def test_default_model_from_available_prefers_marked_default_then_first() -> None:
    presets = build_available_models((visible_model("second", priority=2), visible_model("first", priority=1)))

    assert default_model_from_available(presets) == "first"
    for preset in presets:
        preset.is_default = False
    assert default_model_from_available(presets) == "first"
    assert default_model_from_available([]) == ""


def test_build_available_models_filters_api_only_when_not_codex_backend() -> None:
    chatgpt_only = visible_model("chatgpt-only", priority=0, supported_in_api=False)
    api_model = visible_model("api-model", priority=1, supported_in_api=True)

    assert [preset.model for preset in build_available_models((chatgpt_only, api_model), uses_codex_backend=True)] == [
        "chatgpt-only",
        "api-model",
    ]
    assert [preset.model for preset in build_available_models((chatgpt_only, api_model), uses_codex_backend=False)] == [
        "api-model",
    ]
    assert [preset.model for preset in build_available_models((chatgpt_only, api_model))] == ["api-model"]


def test_static_models_manager_lists_and_gets_defaults() -> None:
    manager = StaticModelsManager(model_catalog=ModelsResponse((visible_model("visible"),)))

    assert [preset.model for preset in asyncio.run(manager.list_models())] == ["visible"]
    assert asyncio.run(manager.get_default_model()) == "visible"
    assert asyncio.run(manager.get_default_model("explicit")) == "explicit"
    assert [model.slug for model in manager.try_get_remote_models()] == ["visible"]


def test_static_models_manager_without_auth_filters_to_api_supported_models() -> None:
    # Rust source: auth_manager().is_some_and(...) is false when no auth manager exists.
    manager = StaticModelsManager(
        model_catalog=ModelsResponse(
            (
                visible_model("chatgpt-only", priority=0, supported_in_api=False),
                visible_model("api-model", priority=1),
            )
        )
    )

    assert [preset.model for preset in asyncio.run(manager.list_models(RefreshStrategy.ONLINE))] == ["api-model"]


def test_managers_list_builtin_collaboration_modes(tmp_path) -> None:
    # Rust crate/module: codex-models-manager::manager::list_collaboration_modes
    static = StaticModelsManager(model_catalog=ModelsResponse((visible_model("visible"),)))
    cached = CachedModelsManager(tmp_path, lambda: ModelsResponse(()))

    assert [mask.mode for mask in static.list_collaboration_modes()] == [ModeKind.PLAN, ModeKind.DEFAULT]
    assert [mask.mode for mask in cached.list_collaboration_modes()] == [ModeKind.PLAN, ModeKind.DEFAULT]


def test_static_models_manager_reads_latest_auth_mode() -> None:
    # Rust crate/module: codex-models-manager::manager::static_manager_reads_latest_auth_mode
    auth_manager = FakeAuthManager("chatgpt")
    manager = StaticModelsManager(
        auth_manager=auth_manager,
        model_catalog=ModelsResponse(
            (
                visible_model("chatgpt-only", priority=0, supported_in_api=False),
                visible_model("api-model", priority=1),
            )
        ),
    )

    assert [preset.model for preset in asyncio.run(manager.list_models(RefreshStrategy.ONLINE))] == [
        "chatgpt-only",
        "api-model",
    ]

    auth_manager.mode = "api_key"
    assert [preset.model for preset in asyncio.run(manager.list_models(RefreshStrategy.ONLINE))] == ["api-model"]


def test_cached_models_manager_online_offline_and_cache_hit(tmp_path) -> None:
    now = datetime(2026, 6, 14, 18, tzinfo=timezone.utc)
    calls = {"count": 0}

    def fetch():
        calls["count"] += 1
        return ModelsResponse((visible_model(f"remote-{calls['count']}"),)), f"etag-{calls['count']}"

    manager = CachedModelsManager(tmp_path, fetch, client_version="1.2.3-dev", ttl=timedelta(hours=24), clock=lambda: now)

    assert [preset.model for preset in asyncio.run(manager.list_models(RefreshStrategy.ONLINE_IF_UNCACHED))] == ["remote-1"]
    assert [preset.model for preset in asyncio.run(manager.list_models(RefreshStrategy.ONLINE_IF_UNCACHED))] == ["remote-1"]
    assert calls["count"] == 1

    assert [preset.model for preset in asyncio.run(manager.list_models(RefreshStrategy.ONLINE))] == ["remote-2"]
    assert [preset.model for preset in asyncio.run(manager.list_models(RefreshStrategy.OFFLINE))] == ["remote-2"]
    assert calls["count"] == 2


def test_cached_models_manager_uses_remote_only_catalog_for_chatgpt_auth(tmp_path) -> None:
    # Rust crate/module: codex-models-manager::manager
    remote = (visible_model("chatgpt-visible-source-of-truth", priority=0),)

    manager = CachedModelsManager(
        tmp_path,
        lambda: ModelsResponse(remote),
        auth_manager=FakeAuthManager("chatgpt"),
        uses_codex_backend=True,
    )

    asyncio.run(manager.list_models(RefreshStrategy.ONLINE_IF_UNCACHED))

    assert manager.get_remote_models() == remote


def test_cached_models_manager_uses_cached_remote_only_catalog_for_chatgpt_auth(tmp_path) -> None:
    # Rust crate/module: codex-models-manager::manager
    remote = (visible_model("chatgpt-cached-source-of-truth", priority=0),)
    calls = {"count": 0}

    def fetch():
        calls["count"] += 1
        return ModelsResponse(remote), None

    manager = CachedModelsManager(
        tmp_path,
        fetch,
        auth_manager=FakeAuthManager("chatgpt"),
        uses_codex_backend=True,
    )
    asyncio.run(manager.list_models(RefreshStrategy.ONLINE_IF_UNCACHED))

    cached_manager = CachedModelsManager(
        tmp_path,
        fetch,
        auth_manager=FakeAuthManager("chatgpt"),
        uses_codex_backend=True,
    )
    asyncio.run(cached_manager.list_models(RefreshStrategy.ONLINE_IF_UNCACHED))

    assert cached_manager.get_remote_models() == remote
    assert calls["count"] == 1


def test_cached_models_manager_merges_cached_models_for_api_auth(tmp_path) -> None:
    # Rust source: try_load_cache applies cache models through apply_remote_models,
    # so API auth keeps bundled models and merges cached remote entries.
    remote = (visible_model("cached-api-visible", priority=0),)
    calls = {"count": 0}

    def fetch():
        calls["count"] += 1
        return ModelsResponse(remote), None

    manager = CachedModelsManager(
        tmp_path,
        fetch,
        auth_manager=FakeAuthManager("api_key"),
        has_command_auth=True,
        uses_codex_backend=False,
    )
    asyncio.run(manager.list_models(RefreshStrategy.ONLINE_IF_UNCACHED))

    cached_manager = CachedModelsManager(
        tmp_path,
        fetch,
        auth_manager=FakeAuthManager("api_key"),
        has_command_auth=True,
        uses_codex_backend=False,
    )
    asyncio.run(cached_manager.list_models(RefreshStrategy.ONLINE_IF_UNCACHED))

    assert cached_manager.get_remote_models() == (*load_remote_models_from_file(), *remote)
    assert calls["count"] == 1


def test_cached_models_manager_get_model_info_falls_back_when_chatgpt_remote_is_authoritative(tmp_path) -> None:
    # Rust crate/module: codex-models-manager::manager
    remote = (visible_model("chatgpt-authoritative-model-info", priority=0),)
    manager = CachedModelsManager(
        tmp_path,
        lambda: ModelsResponse(remote),
        auth_manager=FakeAuthManager("chatgpt"),
        uses_codex_backend=True,
    )
    bundled_slug = load_remote_models_from_file()[0].slug

    asyncio.run(manager.list_models(RefreshStrategy.ONLINE_IF_UNCACHED))
    info = asyncio.run(manager.get_model_info(bundled_slug, ModelsManagerConfig()))

    assert info.slug == bundled_slug
    assert info.used_fallback_model_metadata is True


def test_cached_models_manager_preserves_bundled_catalog_for_empty_chatgpt_remote(tmp_path) -> None:
    # Rust crate/module: codex-models-manager::manager
    manager = CachedModelsManager(
        tmp_path,
        lambda: ModelsResponse(()),
        auth_manager=FakeAuthManager("chatgpt"),
        uses_codex_backend=True,
    )
    expected = load_remote_models_from_file()

    asyncio.run(manager.list_models(RefreshStrategy.ONLINE_IF_UNCACHED))

    assert manager.get_remote_models() == expected


def test_cached_models_manager_merges_hidden_only_chatgpt_remote_with_bundled_catalog(tmp_path) -> None:
    # Rust crate/module: codex-models-manager::manager
    hidden = hidden_model("chatgpt-hidden-only", priority=0)
    manager = CachedModelsManager(
        tmp_path,
        lambda: ModelsResponse((hidden,)),
        auth_manager=FakeAuthManager("chatgpt"),
        uses_codex_backend=True,
    )
    expected = (*load_remote_models_from_file(), hidden)

    asyncio.run(manager.list_models(RefreshStrategy.ONLINE_IF_UNCACHED))

    assert manager.get_remote_models() == expected


def test_cached_models_manager_keeps_merging_for_api_auth(tmp_path) -> None:
    # Rust crate/module: codex-models-manager::manager
    remote = visible_model("api-auth-visible-remote", priority=0)
    calls = {"count": 0}

    def fetch():
        calls["count"] += 1
        return ModelsResponse((remote,)), None

    manager = CachedModelsManager(
        tmp_path,
        fetch,
        auth_manager=FakeAuthManager("api_key"),
        has_command_auth=True,
        uses_codex_backend=False,
    )
    expected = (*load_remote_models_from_file(), remote)

    asyncio.run(manager.list_models(RefreshStrategy.ONLINE_IF_UNCACHED))

    assert manager.get_remote_models() == expected
    assert calls["count"] == 1


def test_cached_models_manager_skips_network_without_refresh_auth(tmp_path) -> None:
    # Rust crate/module: codex-models-manager::manager::refresh_available_models_skips_network_without_chatgpt_auth
    calls = {"count": 0}

    def fetch():
        calls["count"] += 1
        return ModelsResponse((visible_model("dynamic-no-auth"),)), None

    manager = CachedModelsManager(
        tmp_path,
        fetch,
        auth_manager=None,
        has_command_auth=False,
        uses_codex_backend=False,
    )

    asyncio.run(manager.list_models(RefreshStrategy.ONLINE))

    assert all(model.slug != "dynamic-no-auth" for model in manager.get_remote_models())
    assert calls["count"] == 0


def test_openai_models_manager_fetches_through_endpoint_client(tmp_path) -> None:
    # Rust crate/module: codex-models-manager::manager::ModelsEndpointClient
    endpoint = FakeEndpoint(
        [(visible_model("endpoint-visible", priority=0),)],
        has_command_auth=False,
        uses_codex_backend=True,
        etag="endpoint-etag",
    )
    manager = OpenAiModelsManager(
        tmp_path,
        endpoint,
        FakeAuthManager("chatgpt"),
        client_version="1.2.3-dev",
    )

    assert [preset.model for preset in asyncio.run(manager.list_models(RefreshStrategy.ONLINE))] == [
        "endpoint-visible"
    ]
    assert endpoint.client_versions == ["1.2.3"]
    assert manager.etag == "endpoint-etag"


def test_openai_models_manager_skips_endpoint_without_refresh_auth(tmp_path) -> None:
    # Rust crate/module: codex-models-manager::manager::should_refresh_models
    endpoint = FakeEndpoint(
        [(visible_model("endpoint-should-not-fetch", priority=0),)],
        has_command_auth=False,
        uses_codex_backend=False,
    )
    manager = OpenAiModelsManager(tmp_path, endpoint, None)

    asyncio.run(manager.list_models(RefreshStrategy.ONLINE))

    assert endpoint.client_versions == []
    assert all(model.slug != "endpoint-should-not-fetch" for model in manager.get_remote_models())


def test_openai_models_manager_fetches_with_command_auth_for_api_mode(tmp_path) -> None:
    # Rust crate/module: codex-models-manager::manager::refresh_available_models_keeps_merging_for_api_auth
    remote = visible_model("endpoint-api-visible", priority=0)
    endpoint = FakeEndpoint(
        [(remote,)],
        has_command_auth=True,
        uses_codex_backend=False,
    )
    manager = OpenAiModelsManager(tmp_path, endpoint, FakeAuthManager("api_key"))

    asyncio.run(manager.list_models(RefreshStrategy.ONLINE))

    assert endpoint.client_versions == ["0.0.0"]
    assert manager.get_remote_models() == (*load_remote_models_from_file(), remote)


def test_cached_models_manager_refreshes_etag_only_on_change(tmp_path) -> None:
    now = {"value": datetime(2026, 6, 14, 18, tzinfo=timezone.utc)}
    calls = {"count": 0}

    def fetch():
        calls["count"] += 1
        return ModelsResponse((visible_model(f"remote-{calls['count']}"),)), "etag"

    manager = CachedModelsManager(
        tmp_path,
        fetch,
        client_version="1.2.3-dev",
        ttl=timedelta(hours=24),
        clock=lambda: now["value"],
    )

    asyncio.run(manager.list_models(RefreshStrategy.ONLINE))
    now["value"] = datetime(2026, 6, 14, 19, tzinfo=timezone.utc)
    asyncio.run(manager.refresh_models_etag("etag"))

    assert calls["count"] == 1
    cache = manager.read_cache()
    assert cache is not None
    assert cache.fetched_at == now["value"]

    asyncio.run(manager.refresh_models_etag("new-etag"))
    assert calls["count"] == 2


def test_cached_models_manager_same_etag_missing_cache_does_not_raise(tmp_path) -> None:
    # Rust source: refresh_if_new_etag logs renew_cache_ttl errors and returns.
    manager = CachedModelsManager(
        tmp_path,
        lambda: ModelsResponse((visible_model("remote"),)),
        client_version="1.2.3",
    )
    manager.etag = "etag"

    asyncio.run(manager.refresh_models_etag("etag"))
