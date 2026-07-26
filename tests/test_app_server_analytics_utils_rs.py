from dataclasses import dataclass

from pycodex.analytics import AnalyticsEventsClient
from pycodex.app_server.analytics_utils import analytics_events_client_from_config


@dataclass(frozen=True)
class _Config:
    chatgpt_base_url: str
    analytics_enabled: bool | None


def test_analytics_events_client_from_config_constructs_real_client() -> None:
    # Rust: analytics_utils.rs::analytics_events_client_from_config.
    auth_manager = object()
    client = analytics_events_client_from_config(
        auth_manager,
        _Config(chatgpt_base_url="https://chatgpt.example.com///", analytics_enabled=True),
    )

    assert isinstance(client, AnalyticsEventsClient)
    assert client.auth_manager is auth_manager
    assert client.base_url == "https://chatgpt.example.com"
    assert client.enabled is True


def test_analytics_events_client_from_config_preserves_rust_optional_enablement() -> None:
    auth_manager = object()
    client = analytics_events_client_from_config(
        auth_manager,
        {"chatgpt_base_url": "https://chatgpt.example.com/", "analytics_enabled": False},
    )

    assert isinstance(client, AnalyticsEventsClient)
    assert client.auth_manager is auth_manager
    assert client.base_url == "https://chatgpt.example.com"
    assert client.enabled is False
