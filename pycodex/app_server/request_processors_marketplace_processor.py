"""Marketplace request processor projection.

Ported from ``codex-app-server/src/request_processors/marketplace_processor.rs``.
The Rust module owns the JSON-RPC facade for adding, removing, and upgrading
configured marketplaces. Concrete marketplace installation/removal and plugin
upgrade execution stay injected at this module boundary.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.app_server.error_code import internal_error, invalid_request
from pycodex.app_server_protocol import (
    JSONRPCErrorError,
    MarketplaceAddParams,
    MarketplaceAddResponse,
    MarketplaceRemoveParams,
    MarketplaceRemoveResponse,
    MarketplaceUpgradeErrorInfo,
    MarketplaceUpgradeParams,
    MarketplaceUpgradeResponse,
)

JsonValue = Any


class MarketplaceRequestProcessorError(Exception):
    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


@dataclass(frozen=True)
class MarketplaceOperationError(Exception):
    """Small test-double friendly error shape for Rust InvalidRequest/Internal."""

    kind: str
    message: str

    def __str__(self) -> str:
        return self.message


class MarketplaceRequestProcessor:
    def __init__(
        self,
        config: Any,
        config_manager: Any,
        thread_manager: Any,
        *,
        add_marketplace: Any | None = None,
        remove_marketplace: Any | None = None,
        upgrade_marketplaces: Any | None = None,
    ) -> None:
        self.config = config
        self.config_manager = config_manager
        self.thread_manager = thread_manager
        self.add_marketplace = add_marketplace
        self.remove_marketplace = remove_marketplace
        self.upgrade_marketplaces = upgrade_marketplaces

    @classmethod
    def new(
        cls,
        config: Any,
        config_manager: Any,
        thread_manager: Any,
        **kwargs: Any,
    ) -> "MarketplaceRequestProcessor":
        return cls(config, config_manager, thread_manager, **kwargs)

    async def marketplace_add(
        self,
        params: MarketplaceAddParams | Mapping[str, JsonValue],
    ) -> MarketplaceAddResponse:
        return await self.marketplace_add_inner(_params(MarketplaceAddParams, params))

    async def marketplace_remove(
        self,
        params: MarketplaceRemoveParams | Mapping[str, JsonValue],
    ) -> MarketplaceRemoveResponse:
        return await self.marketplace_remove_inner(_params(MarketplaceRemoveParams, params))

    async def marketplace_upgrade(
        self,
        params: MarketplaceUpgradeParams | Mapping[str, JsonValue],
    ) -> MarketplaceUpgradeResponse:
        return await self.marketplace_upgrade_response_inner(_params(MarketplaceUpgradeParams, params))

    async def marketplace_add_inner(self, params: MarketplaceAddParams) -> MarketplaceAddResponse:
        if self.add_marketplace is None:
            raise MarketplaceRequestProcessorError(internal_error("marketplace add runtime is not configured"))
        request = {
            "source": params.source,
            "ref_name": getattr(params, "ref_name", None),
            "sparse_paths": tuple(getattr(params, "sparse_paths", None) or ()),
        }
        try:
            outcome = await _maybe_await(self.add_marketplace(_codex_home(self.config), request))
        except Exception as exc:
            raise MarketplaceRequestProcessorError(_map_marketplace_error(exc)) from exc
        return MarketplaceAddResponse(
            marketplace_name=_field(outcome, "marketplace_name"),
            installed_root=_field(outcome, "installed_root"),
            already_added=bool(_field(outcome, "already_added", False)),
        )

    async def marketplace_remove_inner(self, params: MarketplaceRemoveParams) -> MarketplaceRemoveResponse:
        if self.remove_marketplace is None:
            raise MarketplaceRequestProcessorError(internal_error("marketplace remove runtime is not configured"))
        request = {"marketplace_name": params.marketplace_name}
        try:
            outcome = await _maybe_await(self.remove_marketplace(_codex_home(self.config), request))
        except Exception as exc:
            raise MarketplaceRequestProcessorError(_map_marketplace_error(exc)) from exc
        return MarketplaceRemoveResponse(
            marketplace_name=_field(outcome, "marketplace_name"),
            installed_root=_field(outcome, "removed_installed_root"),
        )

    async def marketplace_upgrade_response_inner(
        self,
        params: MarketplaceUpgradeParams,
    ) -> MarketplaceUpgradeResponse:
        config = await self.load_latest_config(None)
        plugins_manager = _call(self.thread_manager, "plugins_manager")
        marketplace_name = getattr(params, "marketplace_name", None)
        plugins_input = _call(config, "plugins_config_input")

        try:
            if self.upgrade_marketplaces is not None:
                outcome = await _maybe_await(
                    self.upgrade_marketplaces(plugins_manager, plugins_input, marketplace_name)
                )
            else:
                outcome = await _maybe_await(
                    _call(
                        plugins_manager,
                        "upgrade_configured_marketplaces_for_config",
                        plugins_input,
                        marketplace_name,
                    )
                )
        except Exception as exc:
            raise MarketplaceRequestProcessorError(invalid_request(str(exc))) from exc

        errors = tuple(
            MarketplaceUpgradeErrorInfo(
                marketplace_name=_field(error, "marketplace_name"),
                message=_field(error, "message"),
            )
            for error in (_field(outcome, "errors", ()) or ())
        )
        return MarketplaceUpgradeResponse(
            selected_marketplaces=tuple(_field(outcome, "selected_marketplaces", ()) or ()),
            upgraded_roots=tuple(_field(outcome, "upgraded_roots", ()) or ()),
            errors=errors,
        )

    async def load_latest_config(self, fallback_cwd: str | Path | None = None) -> Any:
        try:
            if fallback_cwd is None:
                return await _maybe_await(_call(self.config_manager, "load_latest_config"))
            return await _maybe_await(_call(self.config_manager, "load_latest_config", fallback_cwd))
        except Exception as exc:
            raise MarketplaceRequestProcessorError(internal_error(f"failed to reload config: {exc}")) from exc


def _map_marketplace_error(exc: BaseException) -> JSONRPCErrorError:
    kind = _field(exc, "kind", None)
    message = str(_field(exc, "message", str(exc)))
    if kind in {"InvalidRequest", "invalid_request", "invalidRequest"}:
        return invalid_request(message)
    if exc.__class__.__name__ in {"InvalidRequest", "MarketplaceInvalidRequest"}:
        return invalid_request(message)
    return internal_error(message)


def _codex_home(config: Any) -> Path:
    value = _field(config, "codex_home")
    return value if isinstance(value, Path) else Path(value)


def _params(cls: type, value: Any) -> Any:
    if isinstance(value, cls):
        return value
    if isinstance(value, Mapping):
        return cls.from_mapping(value)
    return cls(**dict(value))


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _call(obj: Any, name: str, *args: Any) -> Any:
    target = _field(obj, name, None)
    if target is None or not callable(target):
        raise AttributeError(name)
    return target(*args)


def _field(value: Any, name: str, default: Any = ...):
    if isinstance(value, Mapping):
        if default is ...:
            return value[name]
        return value.get(name, default)
    if default is ...:
        return getattr(value, name)
    return getattr(value, name, default)


__all__ = [
    "MarketplaceOperationError",
    "MarketplaceRequestProcessor",
    "MarketplaceRequestProcessorError",
]
