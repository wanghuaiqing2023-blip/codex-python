from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    ("module_name", "symbol"),
    [
        ("pycodex.app_server_client.remote", "RemoteAppServerClient"),
        ("pycodex.app_server_client.legacy_core", "McpManager"),
        ("pycodex.app_server_client.legacy_core.config", "__all__"),
        ("pycodex.app_server_client.legacy_core.config.edit", "__all__"),
        ("pycodex.app_server_client.legacy_core.connectors", "__all__"),
        ("pycodex.app_server_client.legacy_core.otel_init", "__all__"),
        ("pycodex.app_server_client.legacy_core.personality_migration", "__all__"),
        ("pycodex.app_server_client.legacy_core.review_format", "__all__"),
        ("pycodex.app_server_client.legacy_core.review_prompts", "__all__"),
        ("pycodex.app_server_client.legacy_core.test_support", "__all__"),
        ("pycodex.app_server_client.legacy_core.util", "__all__"),
        ("pycodex.app_server_client.legacy_core.windows_sandbox", "__all__"),
    ],
)
def test_rust_app_server_client_module_has_one_python_owner(
    module_name: str,
    symbol: str,
) -> None:
    module = importlib.import_module(module_name)
    assert hasattr(module, symbol)


def test_remote_public_type_is_defined_by_remote_module() -> None:
    from pycodex.app_server_client.remote import RemoteAppServerClient

    assert RemoteAppServerClient.__module__ == "pycodex.app_server_client.remote"
