"""Analytics client setup helper ported from ``codex-app-server/src/analytics_utils.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnalyticsEventsClientConfigProjection:
    auth_manager: Any
    chatgpt_base_url: str
    analytics_enabled: bool


def analytics_events_client_from_config_projection(
    auth_manager: Any,
    config: Any,
) -> AnalyticsEventsClientConfigProjection:
    """Mirror the app-server-owned constructor arguments for AnalyticsEventsClient."""

    return AnalyticsEventsClientConfigProjection(
        auth_manager=auth_manager,
        chatgpt_base_url=str(_field(config, "chatgpt_base_url", "")).rstrip("/"),
        analytics_enabled=bool(_field(config, "analytics_enabled", False)),
    )


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = [
    "AnalyticsEventsClientConfigProjection",
    "analytics_events_client_from_config_projection",
]
