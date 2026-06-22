from dataclasses import dataclass

from pycodex.app_server.analytics_utils import (
    AnalyticsEventsClientConfigProjection,
    analytics_events_client_from_config_projection,
)


@dataclass(frozen=True)
class _Config:
    chatgpt_base_url: str
    analytics_enabled: bool


def test_analytics_events_client_from_config_trims_base_url_and_passes_enabled_flag() -> None:
    # Rust: analytics_utils.rs::analytics_events_client_from_config.
    auth_manager = object()
    projection = analytics_events_client_from_config_projection(
        auth_manager,
        _Config(chatgpt_base_url="https://chatgpt.example.com///", analytics_enabled=True),
    )

    assert projection == AnalyticsEventsClientConfigProjection(
        auth_manager=auth_manager,
        chatgpt_base_url="https://chatgpt.example.com",
        analytics_enabled=True,
    )


def test_analytics_events_client_from_config_accepts_mapping_config() -> None:
    auth_manager = object()
    projection = analytics_events_client_from_config_projection(
        auth_manager,
        {"chatgpt_base_url": "https://chatgpt.example.com/", "analytics_enabled": False},
    )

    assert projection.auth_manager is auth_manager
    assert projection.chatgpt_base_url == "https://chatgpt.example.com"
    assert projection.analytics_enabled is False
