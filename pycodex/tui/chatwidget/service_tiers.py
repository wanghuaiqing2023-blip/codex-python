"""Service-tier selection helpers for chat widgets.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/service_tiers.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .._porting import RustTuiModule
from ..bottom_pane.slash_commands import ServiceTierCommand
from ..config_update import SERVICE_TIER_DEFAULT_REQUEST_VALUE
from ..service_tier_resolution import (
    Config,
    FeatureSet,
    ModelPreset,
    ServiceTierPreset,
    effective_service_tier,
    model_supports_service_tier as preset_supports_service_tier,
    service_tier_update_for_core as resolve_service_tier_update_for_core,
)

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::service_tiers",
    source="codex/codex-rs/tui/src/chatwidget/service_tiers.rs",
)

SPEED_TIER_FAST = "fast"
FAST_MODE_FEATURE = "fast_mode"


@dataclass(frozen=True)
class ServiceTierSelectionEvent:
    """Semantic event emitted by Rust ``set_service_tier_selection``."""

    kind: str
    service_tier: str | None

    @classmethod
    def override_turn_context(cls, service_tier: str | None) -> "ServiceTierSelectionEvent":
        return cls("override_turn_context", service_tier)

    @classmethod
    def persist_selection(cls, service_tier: str | None) -> "ServiceTierSelectionEvent":
        return cls("persist_selection", service_tier)


@dataclass
class ChatWidgetServiceTierState:
    """Small semantic stand-in for the service-tier fields on Rust ``ChatWidget``."""

    config: Config = field(default_factory=Config)
    model: str = ""
    models: tuple[Any, ...] = ()
    has_chatgpt_account: bool = False
    user_turn_pending_or_running: bool = False
    modal_or_popup_active: bool = False
    effective_service_tier: str | None = None
    events: list[ServiceTierSelectionEvent] = field(default_factory=list)
    model_dependent_surface_refreshes: int = 0

    def __post_init__(self) -> None:
        self.refresh_effective_service_tier()

    def set_service_tier(self, service_tier: str | None) -> None:
        self.config = Config(
            service_tier=service_tier,
            features=self.config.features,
            notices=self.config.notices,
        )
        self.refresh_effective_service_tier()
        self.refresh_model_dependent_surfaces()

    def current_service_tier(self) -> str | None:
        return self.effective_service_tier

    def configured_service_tier(self) -> str | None:
        return self.config.service_tier

    def service_tier_update_for_core(self) -> str | None:
        return resolve_service_tier_update_for_core(self.config, self.current_model(), self._models_or_default())

    def should_show_fast_status(self, model: str, service_tier: str | None) -> bool:
        return (
            service_tier == ServiceTierPresetFast.request_value()
            and self.model_supports_service_tier(model, service_tier)
            and self.has_chatgpt_account
        )

    def fast_mode_enabled(self) -> bool:
        return self.config.features.enabled(FAST_MODE_FEATURE)

    def can_toggle_fast_mode_from_keybinding(self) -> bool:
        return (
            self.fast_mode_enabled()
            and self.current_model_fast_service_tier() is not None
            and not self.user_turn_pending_or_running
            and not self.modal_or_popup_active
        )

    def toggle_fast_mode_from_ui(self) -> None:
        fast_tier = self.current_model_fast_service_tier()
        if fast_tier is None:
            return
        next_tier = (
            SERVICE_TIER_DEFAULT_REQUEST_VALUE
            if self.current_service_tier() == fast_tier.id
            else fast_tier.id
        )
        self.set_service_tier_selection(next_tier)

    def toggle_service_tier_from_ui(self, command: ServiceTierCommand) -> None:
        next_tier = (
            SERVICE_TIER_DEFAULT_REQUEST_VALUE
            if self.current_service_tier() == command.id
            else command.id
        )
        self.set_service_tier_selection(next_tier)

    def current_model_service_tier_commands(self) -> list[ServiceTierCommand]:
        model = self.current_model()
        for preset in self._models_or_default():
            if _preset_model(preset) != model:
                continue
            return [
                ServiceTierCommand(
                    id=str(_get(tier, "id", "")),
                    name=str(_get(tier, "name", "")).lower(),
                    description=str(_get(tier, "description", "")),
                )
                for tier in (_get(preset, "service_tiers", ()) or ())
            ]
        return []

    def set_service_tier_selection(self, service_tier: str | None) -> None:
        self.set_service_tier(service_tier)
        self.events.append(ServiceTierSelectionEvent.override_turn_context(service_tier))
        self.events.append(ServiceTierSelectionEvent.persist_selection(service_tier))

    def model_supports_service_tier(self, model: str, service_tier: str) -> bool:
        for preset in self._models_or_default():
            if _preset_model(preset) == model:
                return preset_supports_service_tier(preset, service_tier)
        return False

    def current_model_fast_service_tier(self) -> ServiceTierCommand | None:
        for tier in self.current_model_service_tier_commands():
            if tier.name.lower() == SPEED_TIER_FAST:
                return tier
        return None

    def refresh_effective_service_tier(self) -> None:
        self.effective_service_tier = effective_service_tier(
            self.config,
            self.current_model(),
            self._models_or_default(),
        )

    def refresh_model_dependent_surfaces(self) -> None:
        self.model_dependent_surface_refreshes += 1

    def current_model(self) -> str:
        return self.model

    def _models_or_default(self) -> tuple[Any, ...]:
        return tuple(_list_models(self.models))


@dataclass(frozen=True)
class ServiceTierPresetFast:
    """Tiny equivalent of Rust ``ServiceTier::Fast.request_value()``."""

    @staticmethod
    def request_value() -> str:
        return SPEED_TIER_FAST


def _list_models(models: Any) -> Iterable[Any]:
    try_list_models = getattr(models, "try_list_models", None)
    if callable(try_list_models):
        try:
            return tuple(try_list_models())
        except Exception:
            return ()
    list_models = getattr(models, "list_models", None)
    if callable(list_models):
        try:
            return tuple(list_models())
        except Exception:
            return ()
    return models or ()


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _preset_model(preset: Any) -> str:
    return str(_get(preset, "model", ""))


def fast_mode_config(enabled: bool, service_tier: str | None = None) -> Config:
    return Config(
        service_tier=service_tier,
        features=FeatureSet(frozenset({FAST_MODE_FEATURE}) if enabled else frozenset()),
    )


__all__ = [
    "FAST_MODE_FEATURE",
    "SPEED_TIER_FAST",
    "ChatWidgetServiceTierState",
    "ModelPreset",
    "RUST_MODULE",
    "SERVICE_TIER_DEFAULT_REQUEST_VALUE",
    "ServiceTierCommand",
    "ServiceTierPreset",
    "ServiceTierPresetFast",
    "ServiceTierSelectionEvent",
    "fast_mode_config",
]
