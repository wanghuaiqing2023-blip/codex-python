"""Managed feature constraints ported from Codex core config."""

from __future__ import annotations

import logging
from collections.abc import Mapping, MutableSequence
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from . import (
    Feature,
    FeatureConfigSource,
    FeatureOverrides,
    Features,
    FeaturesToml,
    canonical_feature_for_key,
    feature_for_key,
)


LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


def _ensure_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _ensure_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field} must be a bool")
    return value


def _ensure_feature(value: object, field: str) -> Feature:
    if not isinstance(value, Feature):
        raise TypeError(f"{field} must be a Feature")
    return value


@dataclass(frozen=True)
class RequirementSource:
    kind: str
    domain: str | None = None
    key: str | None = None
    file: str | None = None

    @classmethod
    def unknown(cls) -> "RequirementSource":
        return cls("unknown")

    def __post_init__(self) -> None:
        kind = _ensure_str(self.kind, "kind")
        if kind == "mdm_managed_preferences":
            object.__setattr__(self, "domain", _ensure_str(self.domain, "domain"))
            object.__setattr__(self, "key", _ensure_str(self.key, "key"))
        elif kind in {"system_requirements_toml", "legacy_managed_config_toml_from_file"}:
            object.__setattr__(self, "file", _ensure_str(self.file, "file"))
        elif kind in {"unknown", "cloud_requirements", "legacy_managed_config_toml_from_mdm"}:
            pass
        else:
            raise ValueError(f"unknown requirement source kind: {kind}")

    @classmethod
    def mdm_managed_preferences(cls, domain: str, key: str) -> "RequirementSource":
        return cls("mdm_managed_preferences", domain=_ensure_str(domain, "domain"), key=_ensure_str(key, "key"))

    @classmethod
    def cloud_requirements(cls) -> "RequirementSource":
        return cls("cloud_requirements")

    @classmethod
    def system_requirements_toml(cls, file: str) -> "RequirementSource":
        return cls("system_requirements_toml", file=_ensure_str(file, "file"))

    @classmethod
    def legacy_managed_config_toml_from_file(cls, file: str) -> "RequirementSource":
        return cls("legacy_managed_config_toml_from_file", file=_ensure_str(file, "file"))

    @classmethod
    def legacy_managed_config_toml_from_mdm(cls) -> "RequirementSource":
        return cls("legacy_managed_config_toml_from_mdm")

    def __str__(self) -> str:
        if self.kind == "unknown":
            return "<unspecified>"
        if self.kind == "mdm_managed_preferences":
            return f"MDM {self.domain}:{self.key}"
        if self.kind == "cloud_requirements":
            return "cloud requirements"
        if self.kind in ("system_requirements_toml", "legacy_managed_config_toml_from_file"):
            return self.file or ""
        if self.kind == "legacy_managed_config_toml_from_mdm":
            return "MDM managed_config.toml (legacy)"
        return self.kind


@dataclass(frozen=True)
class Sourced(Generic[T]):
    value: T
    source: RequirementSource


@dataclass(frozen=True)
class FeatureRequirementsToml:
    entries: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized: dict[str, bool] = {}
        for key, value in self.entries.items():
            normalized[_ensure_str(key, "feature requirement key")] = _ensure_bool(value, "feature requirement value")
        object.__setattr__(self, "entries", normalized)

    @classmethod
    def from_entries(cls, entries: Mapping[str, bool]) -> "FeatureRequirementsToml":
        return cls(entries)

    def is_empty(self) -> bool:
        return not self.entries


@dataclass
class ConstraintError(ValueError):
    field_name: str
    candidate: str
    allowed: str
    requirement_source: RequirementSource

    def __str__(self) -> str:
        return (
            f"invalid value for `{self.field_name}`: `{self.candidate}` is not in the allowed set "
            f"{self.allowed} (set by {self.requirement_source})"
        )


class ManagedFeatures:
    """Feature set wrapper that normalizes to managed requirements."""

    def __init__(
        self,
        value: Features | None = None,
        pinned_features: Mapping[Feature, bool] | None = None,
        source: RequirementSource | None = None,
    ) -> None:
        if value is not None and not isinstance(value, Features):
            raise TypeError("value must be a Features instance")
        self._value = _clone_features(value or Features())
        self._pinned_features = {
            _ensure_feature(feature, "pinned feature"): _ensure_bool(enabled, "pinned feature value")
            for feature, enabled in (pinned_features or {}).items()
        }
        if source is not None and not isinstance(source, RequirementSource):
            raise TypeError("source must be a RequirementSource")
        self._source = source

    @classmethod
    def default(cls) -> "ManagedFeatures":
        return cls(Features())

    @classmethod
    def from_features(cls, features: Features) -> "ManagedFeatures":
        return cls(features)

    @classmethod
    def from_configured(
        cls,
        configured_features: Features,
        feature_requirements: Sourced[FeatureRequirementsToml] | None = None,
    ) -> "ManagedFeatures":
        return cls.from_configured_with_warnings(configured_features, feature_requirements, None)

    @classmethod
    def from_configured_with_warnings(
        cls,
        configured_features: Features,
        feature_requirements: Sourced[FeatureRequirementsToml] | None,
        startup_warnings: MutableSequence[str] | None,
    ) -> "ManagedFeatures":
        pinned_features: dict[Feature, bool]
        source: RequirementSource | None
        if feature_requirements is None:
            pinned_features = {}
            source = None
        else:
            source = feature_requirements.source
            pinned_features = parse_feature_requirements(
                feature_requirements.value,
                source,
                startup_warnings,
            )

        normalized_features = normalize_candidate(configured_features, pinned_features)
        validate_pinned_features(normalized_features, pinned_features, source)
        return cls(normalized_features, pinned_features, source)

    def get(self) -> Features:
        return self._value

    def enabled(self, feature: Feature) -> bool:
        return self._value.enabled(feature)

    def can_set(self, candidate: Features) -> None:
        self._normalize_and_validate(candidate)

    def set(self, candidate: Features) -> None:
        self._value = self._normalize_and_validate(candidate)

    def set_enabled(self, feature: Feature, enabled: bool) -> None:
        next_features = _clone_features(self._value)
        next_features.set_enabled(_ensure_feature(feature, "feature"), _ensure_bool(enabled, "enabled"))
        self.set(next_features)

    def enable(self, feature: Feature) -> None:
        self.set_enabled(feature, True)

    def disable(self, feature: Feature) -> None:
        self.set_enabled(feature, False)

    def _normalize_and_validate(self, candidate: Features) -> Features:
        normalized = normalize_candidate(candidate, self._pinned_features)
        validate_pinned_features(normalized, self._pinned_features, self._source)
        return normalized


def normalize_candidate(candidate: Features, pinned_features: Mapping[Feature, bool]) -> Features:
    normalized = _clone_features(candidate)
    for feature in _ordered_features(pinned_features):
        normalized.set_enabled(feature, pinned_features[feature])
    normalized.normalize_dependencies()
    return normalized


def validate_pinned_features(
    normalized_features: Features,
    pinned_features: Mapping[Feature, bool],
    source: RequirementSource | None,
) -> None:
    if source is None:
        return

    allowed = feature_requirements_display(pinned_features)
    for feature in _ordered_features(pinned_features):
        enabled = pinned_features[feature]
        if normalized_features.enabled(feature) != enabled:
            raise ConstraintError(
                field_name="features",
                candidate=f"{feature.key()}={_bool_string(normalized_features.enabled(feature))}",
                allowed=allowed,
                requirement_source=source,
            )


def feature_requirements_display(feature_requirements: Mapping[Feature, bool]) -> str:
    values = [
        f"{feature.key()}={_bool_string(feature_requirements[feature])}"
        for feature in _ordered_features(feature_requirements)
    ]
    return f"[{', '.join(values)}]"


def parse_feature_requirements(
    feature_requirements: FeatureRequirementsToml,
    source: RequirementSource,
    startup_warnings: MutableSequence[str] | None = None,
) -> dict[Feature, bool]:
    pinned_features: dict[Feature, bool] = {}
    for key in sorted(feature_requirements.entries):
        enabled = _ensure_bool(feature_requirements.entries[key], "feature requirement value")
        if key == "auto_review":
            pinned_features[Feature.GUARDIAN_APPROVAL] = enabled
            continue

        feature = canonical_feature_for_key(key)
        if feature is not None:
            pinned_features[feature] = enabled
            continue

        feature = feature_for_key(key)
        if feature is not None:
            _push_feature_requirement_warning(
                startup_warnings,
                (
                    f"Using legacy `features` requirement `{key}` from {source}; "
                    f"prefer canonical feature key `{feature.key()}`"
                ),
            )
            pinned_features[feature] = enabled
            continue

        _push_feature_requirement_warning(
            startup_warnings,
            f"Ignoring unknown `features` requirement `{key}` from {source}",
        )
    return pinned_features


def explicit_feature_settings_in_config(cfg: Any) -> list[tuple[str, Feature, bool]]:
    explicit_settings: list[tuple[str, Feature, bool]] = []

    features = _features_toml_or_none(_get_value(cfg, "features"))
    if features is not None:
        for key, enabled in features.entries().items():
            feature = feature_for_key(key)
            if feature is not None:
                explicit_settings.append((f"features.{key}", feature, enabled))

    enabled = _get_value(cfg, "experimental_use_unified_exec_tool")
    if enabled is not None:
        explicit_settings.append(("experimental_use_unified_exec_tool", Feature.UNIFIED_EXEC, _ensure_bool(enabled, "experimental_use_unified_exec_tool")))

    return explicit_settings


def validate_explicit_feature_settings_in_config_toml(
    cfg: Any,
    feature_requirements: Sourced[FeatureRequirementsToml] | None,
) -> None:
    if feature_requirements is None:
        return

    pinned_features = parse_feature_requirements(feature_requirements.value, feature_requirements.source)
    if not pinned_features:
        return

    allowed = feature_requirements_display(pinned_features)
    for path, feature, enabled in explicit_feature_settings_in_config(cfg):
        required = pinned_features.get(feature)
        if required is not None and required != enabled:
            raise ConstraintError(
                field_name="features",
                candidate=f"{path}={_bool_string(enabled)}",
                allowed=allowed,
                requirement_source=feature_requirements.source,
            )


def validate_feature_requirements_in_config_toml(
    cfg: Any,
    feature_requirements: Sourced[FeatureRequirementsToml] | None,
) -> None:
    configured_features = Features.from_sources(
        FeatureConfigSource(
            features=_features_toml_or_none(_get_value(cfg, "features")),
            experimental_use_unified_exec_tool=_get_value(cfg, "experimental_use_unified_exec_tool"),
        ),
        FeatureConfigSource(),
        FeatureOverrides(),
    )
    ManagedFeatures.from_configured(configured_features, feature_requirements)


def validate_feature_requirements_for_config_toml(
    cfg: Any,
    feature_requirements: Sourced[FeatureRequirementsToml] | None,
) -> None:
    validate_explicit_feature_settings_in_config_toml(cfg, feature_requirements)
    validate_feature_requirements_in_config_toml(cfg, feature_requirements)


def _validate_profile(
    cfg: Any,
    profile_name: str | None,
    profile: Any,
    feature_requirements: Sourced[FeatureRequirementsToml] | None,
) -> None:
    configured_features = Features.from_sources(
        FeatureConfigSource(
            features=_features_toml_or_none(_get_value(cfg, "features")),
            experimental_use_unified_exec_tool=_get_value(cfg, "experimental_use_unified_exec_tool"),
        ),
        FeatureConfigSource(
            features=_features_toml_or_none(_get_value(profile, "features")),
            experimental_use_unified_exec_tool=_get_value(profile, "experimental_use_unified_exec_tool"),
        ),
        FeatureOverrides(),
    )
    try:
        ManagedFeatures.from_configured(configured_features, feature_requirements)
    except ConstraintError as exc:
        if profile_name is None:
            raise
        raise ValueError(f"invalid feature configuration for profile `{profile_name}`: {exc}") from exc


def _push_feature_requirement_warning(
    startup_warnings: MutableSequence[str] | None,
    message: str,
) -> None:
    LOGGER.warning(message)
    if startup_warnings is not None:
        startup_warnings.append(message)


def _features_toml_or_none(value: Any) -> FeaturesToml | None:
    if value is None:
        return None
    if isinstance(value, FeaturesToml):
        return value
    if isinstance(value, Mapping):
        return FeaturesToml.from_mapping(value)
    raise TypeError("features must be a FeaturesToml or mapping")


def _get_value(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _clone_features(features: Features) -> Features:
    return Features(features.enabled_features(), features.legacy_feature_usages())


def _ordered_features(features: Mapping[Feature, bool]) -> list[Feature]:
    return [feature for feature in Feature if feature in features]


def _bool_string(value: bool) -> str:
    return "true" if value else "false"


__all__ = [
    "ConstraintError",
    "FeatureRequirementsToml",
    "ManagedFeatures",
    "RequirementSource",
    "Sourced",
    "explicit_feature_settings_in_config",
    "feature_requirements_display",
    "normalize_candidate",
    "parse_feature_requirements",
    "validate_explicit_feature_settings_in_config_toml",
    "validate_feature_requirements_for_config_toml",
    "validate_feature_requirements_in_config_toml",
    "validate_pinned_features",
]
