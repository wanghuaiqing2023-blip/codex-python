from __future__ import annotations


def test_remote_plugin_mutation_url_preserves_base_path_and_escapes_segments() -> None:
    from pycodex.core_plugins.remote import RemotePluginServiceConfig
    from pycodex.core_plugins.remote_legacy import remote_plugin_mutation_url

    config = RemotePluginServiceConfig("https://example.com/backend-api/")
    assert remote_plugin_mutation_url(config, "plugin id", "enable") == (
        "https://example.com/backend-api/plugins/plugin%20id/enable"
    )


def test_remote_plugin_status_defaults_marketplace_name() -> None:
    from pycodex.core_plugins.remote_legacy import RemotePluginStatusSummary

    summary = RemotePluginStatusSummary.from_mapping(
        {"name": "linear", "enabled": True}
    )
    assert summary.marketplace_name == "openai-curated"
    assert summary.enabled is True
