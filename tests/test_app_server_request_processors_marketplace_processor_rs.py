"""Rust parity tests for ``request_processors/marketplace_processor.rs``."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.app_server.request_processors_marketplace_processor import (
    MarketplaceOperationError,
    MarketplaceRequestProcessor,
    MarketplaceRequestProcessorError,
)
from pycodex.app_server_protocol import (
    MarketplaceAddParams,
    MarketplaceAddResponse,
    MarketplaceRemoveParams,
    MarketplaceRemoveResponse,
    MarketplaceUpgradeErrorInfo,
    MarketplaceUpgradeParams,
    MarketplaceUpgradeResponse,
)


class ConfigManager:
    def __init__(self, config=None, error: Exception | None = None) -> None:
        self.config = config
        self.error = error
        self.calls = []

    def load_latest_config(self):
        self.calls.append(None)
        if self.error is not None:
            raise self.error
        return self.config


class UpgradeConfig:
    def __init__(self) -> None:
        self.plugins_input = {"marketplaces": ["stable"]}

    def plugins_config_input(self):
        return self.plugins_input


class ThreadManager:
    def __init__(self, plugins_manager) -> None:
        self._plugins_manager = plugins_manager

    def plugins_manager(self):
        return self._plugins_manager


class PluginsManager:
    def __init__(self, outcome=None, error: Exception | None = None) -> None:
        self.outcome = outcome
        self.error = error
        self.calls = []

    def upgrade_configured_marketplaces_for_config(self, plugins_input, marketplace_name):
        self.calls.append((plugins_input, marketplace_name))
        if self.error is not None:
            raise self.error
        return self.outcome


def _processor(**kwargs):
    config = kwargs.pop("config", SimpleNamespace(codex_home=Path("C:/codex-home")))
    config_manager = kwargs.pop("config_manager", ConfigManager(UpgradeConfig()))
    thread_manager = kwargs.pop("thread_manager", ThreadManager(SimpleNamespace()))
    return MarketplaceRequestProcessor.new(config, config_manager, thread_manager, **kwargs)


def test_marketplace_request_processor_new_stores_runtime_dependencies() -> None:
    # Rust source: MarketplaceRequestProcessor::new stores config, config_manager, thread_manager.
    config = SimpleNamespace(codex_home=Path("C:/home"))
    config_manager = ConfigManager(UpgradeConfig())
    thread_manager = ThreadManager(object())

    processor = MarketplaceRequestProcessor.new(config, config_manager, thread_manager)

    assert processor.config is config
    assert processor.config_manager is config_manager
    assert processor.thread_manager is thread_manager


def test_marketplace_add_maps_request_defaults_and_response() -> None:
    # Rust source: marketplace_add_inner unwrap_or_default sparse_paths and maps add outcome.
    calls = []

    def add_marketplace(codex_home, request):
        calls.append((codex_home, request))
        return {
            "marketplace_name": "acme",
            "installed_root": Path("C:/codex-home/marketplaces/acme"),
            "already_added": False,
        }

    processor = _processor(add_marketplace=add_marketplace)

    response = asyncio.run(processor.marketplace_add({"source": "https://example.com/acme"}))

    assert calls == [
        (
            Path("C:/codex-home"),
            {"source": "https://example.com/acme", "ref_name": None, "sparse_paths": ()},
        )
    ]
    assert response == MarketplaceAddResponse(
        marketplace_name="acme",
        installed_root=Path("C:/codex-home/marketplaces/acme"),
        already_added=False,
    )


def test_marketplace_add_maps_invalid_request_error_like_rust() -> None:
    # Rust source: MarketplaceAddError::InvalidRequest maps to invalid_request.
    def add_marketplace(_codex_home, _request):
        raise MarketplaceOperationError("InvalidRequest", "bad source")

    processor = _processor(add_marketplace=add_marketplace)

    with pytest.raises(MarketplaceRequestProcessorError) as caught:
        asyncio.run(processor.marketplace_add(MarketplaceAddParams(source="bad")))

    assert caught.value.error.code == -32600
    assert caught.value.error.message == "bad source"


def test_marketplace_remove_maps_removed_root_to_installed_root() -> None:
    # Rust source: marketplace_remove_inner maps removed_installed_root to installed_root.
    calls = []

    def remove_marketplace(codex_home, request):
        calls.append((codex_home, request))
        return {"marketplace_name": "acme", "removed_installed_root": Path("C:/old/acme")}

    processor = _processor(remove_marketplace=remove_marketplace)

    response = asyncio.run(processor.marketplace_remove(MarketplaceRemoveParams(marketplace_name="acme")))

    assert calls == [(Path("C:/codex-home"), {"marketplace_name": "acme"})]
    assert response == MarketplaceRemoveResponse(marketplace_name="acme", installed_root=Path("C:/old/acme"))


def test_marketplace_remove_maps_internal_error_like_rust() -> None:
    # Rust source: MarketplaceRemoveError::Internal maps to internal_error.
    def remove_marketplace(_codex_home, _request):
        raise MarketplaceOperationError("Internal", "disk failed")

    processor = _processor(remove_marketplace=remove_marketplace)

    with pytest.raises(MarketplaceRequestProcessorError) as caught:
        asyncio.run(processor.marketplace_remove({"marketplaceName": "acme"}))

    assert caught.value.error.code == -32603
    assert caught.value.error.message == "disk failed"


def test_marketplace_upgrade_loads_latest_config_and_maps_outcome() -> None:
    # Rust source: marketplace_upgrade_response_inner loads config, calls plugins manager, maps errors.
    config_manager = ConfigManager(UpgradeConfig())
    plugin_manager = SimpleNamespace(name="pm")
    calls = []

    def upgrade_marketplaces(plugins_manager, plugins_input, marketplace_name):
        calls.append((plugins_manager, plugins_input, marketplace_name))
        return {
            "selected_marketplaces": ("stable",),
            "upgraded_roots": (Path("C:/marketplaces/stable"),),
            "errors": ({"marketplace_name": "beta", "message": "offline"},),
        }

    processor = _processor(
        config_manager=config_manager,
        thread_manager=ThreadManager(plugin_manager),
        upgrade_marketplaces=upgrade_marketplaces,
    )

    response = asyncio.run(processor.marketplace_upgrade(MarketplaceUpgradeParams(marketplace_name="stable")))

    assert config_manager.calls == [None]
    assert calls == [(plugin_manager, {"marketplaces": ["stable"]}, "stable")]
    assert response == MarketplaceUpgradeResponse(
        selected_marketplaces=("stable",),
        upgraded_roots=(Path("C:/marketplaces/stable"),),
        errors=(MarketplaceUpgradeErrorInfo(marketplace_name="beta", message="offline"),),
    )


def test_marketplace_upgrade_default_plugins_manager_path_matches_rust_call_order() -> None:
    # Rust source: uses thread_manager.plugins_manager(), config.plugins_config_input(),
    # and upgrade_configured_marketplaces_for_config(&plugins_input, marketplace_name.as_deref()).
    config_manager = ConfigManager(UpgradeConfig())
    plugins_manager = PluginsManager(
        outcome={
            "selected_marketplaces": ("stable", "beta"),
            "upgraded_roots": (),
            "errors": (),
        }
    )
    processor = _processor(
        config_manager=config_manager,
        thread_manager=ThreadManager(plugins_manager),
    )

    response = asyncio.run(processor.marketplace_upgrade({"marketplaceName": None}))

    assert config_manager.calls == [None]
    assert plugins_manager.calls == [({"marketplaces": ["stable"]}, None)]
    assert response == MarketplaceUpgradeResponse(
        selected_marketplaces=("stable", "beta"),
        upgraded_roots=(),
        errors=(),
    )


def test_marketplace_upgrade_maps_plugin_failure_to_invalid_request() -> None:
    # Rust source: upgrade_configured_marketplaces_for_config errors map through invalid_request.
    processor = _processor(
        thread_manager=ThreadManager(PluginsManager(error=RuntimeError("unknown marketplace"))),
    )

    with pytest.raises(MarketplaceRequestProcessorError) as caught:
        asyncio.run(processor.marketplace_upgrade(MarketplaceUpgradeParams(marketplace_name="missing")))

    assert caught.value.error.code == -32600
    assert caught.value.error.message == "unknown marketplace"


def test_marketplace_upgrade_maps_load_latest_config_failure_to_internal_error() -> None:
    # Rust source: load_latest_config maps reload failure to internal_error.
    processor = _processor(config_manager=ConfigManager(error=RuntimeError("bad config")))

    with pytest.raises(MarketplaceRequestProcessorError) as caught:
        asyncio.run(processor.marketplace_upgrade({}))

    assert caught.value.error.code == -32603
    assert caught.value.error.message == "failed to reload config: bad config"
