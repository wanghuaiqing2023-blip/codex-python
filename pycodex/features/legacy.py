"""Legacy feature aliases owned by ``codex-features::legacy``."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import Feature, Features


LOGGER = logging.getLogger(__name__)

_ALIAS_NAMES = (
    "connectors",
    "enable_experimental_windows_sandbox",
    "experimental_use_unified_exec_tool",
    "request_permissions",
    "web_search",
    "collab",
    "memory_tool",
    "telepathy",
    "codex_hooks",
)


def _aliases() -> dict[str, Feature]:
    from . import Feature

    return {
        "connectors": Feature.APPS,
        "enable_experimental_windows_sandbox": Feature.WINDOWS_SANDBOX,
        "experimental_use_unified_exec_tool": Feature.UNIFIED_EXEC,
        "request_permissions": Feature.EXEC_PERMISSION_APPROVALS,
        "web_search": Feature.WEB_SEARCH_REQUEST,
        "collab": Feature.COLLAB,
        "memory_tool": Feature.MEMORY_TOOL,
        "telepathy": Feature.CHRONICLE,
        "codex_hooks": Feature.CODEX_HOOKS,
    }


def legacy_feature_keys() -> tuple[str, ...]:
    return _ALIAS_NAMES


def feature_for_key(key: str) -> Feature | None:
    feature = _aliases().get(key)
    if feature is not None:
        _log_alias(key, feature)
    return feature


@dataclass
class LegacyFeatureToggles:
    experimental_use_unified_exec_tool: bool | None = None

    def apply(self, features: Features) -> None:
        from . import Feature

        _set_if_some(
            features,
            Feature.UNIFIED_EXEC,
            self.experimental_use_unified_exec_tool,
            "experimental_use_unified_exec_tool",
        )


def _set_if_some(
    features: Features,
    feature: Feature,
    maybe_value: bool | None,
    alias_key: str,
) -> None:
    if maybe_value is None:
        return
    features.set_enabled(feature, maybe_value)
    _log_alias(alias_key, feature)
    features.record_legacy_usage(alias_key, feature)


def _log_alias(alias: str, feature: Feature) -> None:
    canonical = feature.key()
    if alias == canonical:
        return
    LOGGER.info(
        "legacy feature toggle detected; prefer `[features].%s`",
        canonical,
        extra={"alias": alias, "canonical": canonical},
    )


__all__ = ["LegacyFeatureToggles", "feature_for_key", "legacy_feature_keys"]
