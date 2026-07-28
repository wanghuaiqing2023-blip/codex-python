"""Extension registration from Rust ``web-search/src/extension.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pycodex.codex_api import (
    AllowedCaller,
    ApproximateLocation,
    LocationType,
    SearchContextSize,
    SearchFilters,
    SearchSettings,
)
from pycodex.extension_api import ExtensionRegistryBuilder
from pycodex.features import Feature
from pycodex.model_provider import create_model_provider
from pycodex.protocol import WebSearchMode

from .tool import WebSearchTool


@dataclass(frozen=True)
class WebSearchExtensionConfig:
    enabled: bool
    provider: Any
    settings: SearchSettings

    @classmethod
    def from_config(cls, config: Any) -> "WebSearchExtensionConfig":
        mode = _web_search_mode(config)
        provider = _field(config, "model_provider")
        features = _field(config, "features")
        feature_enabled = bool(
            features is not None
            and callable(getattr(features, "enabled", None))
            and features.enabled(Feature.STANDALONE_WEB_SEARCH)
        )
        provider_is_openai = bool(
            provider is not None
            and callable(getattr(provider, "is_openai", None))
            and provider.is_openai()
        )
        return cls(
            enabled=feature_enabled
            and provider_is_openai
            and mode is not WebSearchMode.DISABLED,
            provider=provider,
            settings=search_settings(config, mode),
        )


def search_settings(config: Any, web_search_mode: WebSearchMode) -> SearchSettings:
    web_config = _field(config, "web_search_config")
    location = _field(web_config, "user_location") if web_config is not None else None
    context_size = (
        _field(web_config, "search_context_size")
        if web_config is not None
        else None
    )
    filters = _field(web_config, "filters") if web_config is not None else None
    return SearchSettings(
        user_location=(
            None
            if location is None
            else ApproximateLocation(
                type=LocationType.APPROXIMATE,
                country=_field(location, "country"),
                region=_field(location, "region"),
                city=_field(location, "city"),
                timezone=_field(location, "timezone"),
            )
        ),
        search_context_size=(
            None
            if context_size is None
            else SearchContextSize(_enum_value(context_size))
        ),
        filters=(
            None
            if filters is None
            else SearchFilters(
                allowed_domains=_field(filters, "allowed_domains"),
                blocked_domains=None,
            )
        ),
        allowed_callers=(AllowedCaller.DIRECT,),
        external_web_access=web_search_mode is WebSearchMode.LIVE,
    )


class WebSearchExtension:
    def __init__(self, auth_manager: Any) -> None:
        self.auth_manager = auth_manager

    async def on_thread_start(self, input: Any) -> None:
        input.thread_store.insert(WebSearchExtensionConfig.from_config(input.config))

    def on_config_changed(
        self,
        session_store: Any,
        thread_store: Any,
        previous_config: Any,
        new_config: Any,
    ) -> None:
        del session_store, previous_config
        thread_store.insert(WebSearchExtensionConfig.from_config(new_config))

    def tools(self, session_store: Any, thread_store: Any) -> list[Any]:
        config = thread_store.get(WebSearchExtensionConfig)
        if config is None or not config.enabled:
            return []
        return [
            WebSearchTool(
                session_id=session_store.level_id(),
                provider=create_model_provider(config.provider, self.auth_manager),
                settings=config.settings,
            )
        ]


def install(
    registry: ExtensionRegistryBuilder,
    auth_manager: Any,
) -> WebSearchExtension:
    extension = WebSearchExtension(auth_manager)
    registry.thread_lifecycle_contributor(extension)
    registry.config_contributor(extension)
    registry.tool_contributor(extension)
    return extension


def _web_search_mode(config: Any) -> WebSearchMode:
    mode = _field(config, "web_search_mode", WebSearchMode.DISABLED)
    value_method = getattr(mode, "value", None)
    if callable(value_method):
        mode = value_method()
    else:
        mode = _enum_value(mode)
    return WebSearchMode(mode)


def _enum_value(value: Any) -> Any:
    raw = getattr(value, "value", value)
    return raw() if callable(raw) else raw


def _field(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = [
    "WebSearchExtension",
    "WebSearchExtensionConfig",
    "install",
    "search_settings",
]
