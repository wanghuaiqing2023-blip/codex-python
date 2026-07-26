"""Analytics client construction owned by ``codex-app-server::analytics_utils``."""

from __future__ import annotations

from typing import Any

from pycodex.analytics import AnalyticsEventsClient


def analytics_events_client_from_config(
    auth_manager: Any,
    config: Any,
) -> AnalyticsEventsClient:
    """Construct the production analytics client from the App-server config."""

    return AnalyticsEventsClient(
        auth_manager=auth_manager,
        base_url=str(_field(config, "chatgpt_base_url", "")).rstrip("/"),
        analytics_enabled=_field(config, "analytics_enabled"),
    )


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = ["analytics_events_client_from_config"]
