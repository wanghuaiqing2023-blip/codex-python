"""Behavior port for Rust ``codex-tui::service_tier_resolution``.

Upstream source: ``codex/codex-rs/tui/src/service_tier_resolution.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Tuple, Union

from ._porting import RustTuiModule
from .config_update import SERVICE_TIER_DEFAULT_REQUEST_VALUE

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="service_tier_resolution",
    source="codex/codex-rs/tui/src/service_tier_resolution.rs",
)

FAST_MODE_FEATURE = "fast_mode"


@dataclass(frozen=True)
class FeatureSet:
    enabled_features: frozenset[str] = frozenset()

    def enabled(self, feature: str) -> bool:
        return feature in self.enabled_features


@dataclass(frozen=True)
class Notices:
    fast_default_opt_out: Optional[bool] = None


@dataclass(frozen=True)
class Config:
    service_tier: Optional[str] = None
    features: FeatureSet = field(default_factory=FeatureSet)
    notices: Notices = field(default_factory=Notices)


@dataclass(frozen=True)
class ServiceTierPreset:
    id: str


@dataclass(frozen=True)
class ModelPreset:
    model: str
    service_tiers: Tuple[ServiceTierPreset, ...] = ()
    default_service_tier: Optional[str] = None


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _feature_enabled(features: Any, feature: str) -> bool:
    enabled = getattr(features, "enabled", None)
    if callable(enabled):
        return bool(enabled(feature))
    if isinstance(features, dict):
        return bool(features.get(feature) or features.get("FastMode") or features.get("fastMode"))
    if isinstance(features, (set, frozenset, list, tuple)):
        return feature in features or "FastMode" in features or "fastMode" in features
    return False


def _fast_mode_enabled(config: Any) -> bool:
    return _feature_enabled(_get(config, "features", FeatureSet()), FAST_MODE_FEATURE)


def _fast_default_opt_out(config: Any) -> Optional[bool]:
    notices = _get(config, "notices", Notices())
    return _get(notices, "fast_default_opt_out")


def _tier_id(tier: Any) -> str:
    return str(_get(tier, "id", tier))


def _preset_model(preset: Any) -> str:
    return str(_get(preset, "model", ""))


def _preset_default_service_tier(preset: Any) -> Optional[str]:
    default = _get(preset, "default_service_tier")
    return None if default is None else str(default)


def _preset_service_tiers(preset: Any) -> Iterable[Any]:
    return _get(preset, "service_tiers", ()) or ()


def configured_service_tier(config: Any) -> Optional[str]:
    configured = _get(config, "service_tier")
    if configured is not None:
        return str(configured)
    if _fast_default_opt_out(config) is True:
        return SERVICE_TIER_DEFAULT_REQUEST_VALUE
    return None


def _find_model_preset(model: str, models: Iterable[Any]) -> Optional[Any]:
    for preset in models:
        if _preset_model(preset) == model:
            return preset
    return None


def effective_service_tier(config: Any, model: str, models: Iterable[Any]) -> Optional[str]:
    if not _fast_mode_enabled(config):
        return None

    configured = configured_service_tier(config)
    preset = _find_model_preset(model, models)
    if preset is None:
        return configured

    if configured == SERVICE_TIER_DEFAULT_REQUEST_VALUE:
        return configured
    if configured is not None:
        return configured if model_supports_service_tier(preset, configured) else None

    default_tier = _preset_default_service_tier(preset)
    if default_tier is not None and model_supports_service_tier(preset, default_tier):
        return default_tier
    return None


def service_tier_update_for_core(config: Any, model: str, models: Iterable[Any]) -> Optional[str]:
    """Return the service tier value that Rust wraps as ``Some(Some(value))``.

    Rust's outer ``None`` means "send no update"; this Python boundary has no
    ``Some(None)`` branch in the upstream implementation, so ``None`` is the
    no-update result and a string is the update payload.
    """

    models_tuple = tuple(models)
    if not _fast_mode_enabled(config):
        return None

    effective = effective_service_tier(config, model, models_tuple)
    if effective is not None:
        return effective

    if not any(_preset_model(preset) == model for preset in models_tuple):
        return None

    return SERVICE_TIER_DEFAULT_REQUEST_VALUE


def model_supports_service_tier(model: Any, service_tier: str) -> bool:
    return any(_tier_id(tier) == service_tier for tier in _preset_service_tiers(model))


__all__ = [
    "Config",
    "FAST_MODE_FEATURE",
    "FeatureSet",
    "ModelPreset",
    "Notices",
    "RUST_MODULE",
    "ServiceTierPreset",
    "configured_service_tier",
    "effective_service_tier",
    "model_supports_service_tier",
    "service_tier_update_for_core",
]
