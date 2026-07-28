"""Rust-derived ownership checks for codex-features submodules."""

from pycodex import features


def test_feature_configs_rs_owns_configuration_types() -> None:
    from pycodex.features import feature_configs

    expected = {
        "AppsMcpPathOverrideConfigToml",
        "MultiAgentV2ConfigToml",
        "NetworkProxyConfigToml",
        "NetworkProxyDomainPermissionToml",
        "NetworkProxyModeToml",
        "NetworkProxyUnixSocketPermissionToml",
    }

    assert expected <= set(feature_configs.__all__)
    for name in expected:
        assert getattr(feature_configs, name).__module__ == "pycodex.features.feature_configs"
        assert getattr(features, name) is getattr(feature_configs, name)


def test_legacy_rs_owns_alias_resolution_and_toggle_application() -> None:
    from pycodex.features import legacy

    assert legacy.legacy_feature_keys() == (
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
    assert legacy.feature_for_key("telepathy") is features.Feature.CHRONICLE
    assert legacy.feature_for_key("missing") is None

    configured = features.Features.with_defaults()
    legacy.LegacyFeatureToggles(
        experimental_use_unified_exec_tool=True
    ).apply(configured)

    assert configured.enabled(features.Feature.UNIFIED_EXEC)
    usages = tuple(configured.legacy_feature_usages())
    assert any(
        usage.alias == "experimental_use_unified_exec_tool"
        and usage.feature is features.Feature.UNIFIED_EXEC
        for usage in usages
    )


def test_lib_rs_public_feature_lookup_delegates_to_legacy_module() -> None:
    from pycodex.features import legacy

    assert features.feature_for_key("apps") is features.Feature.APPS
    assert features.feature_for_key("connectors") is legacy.feature_for_key("connectors")
    assert features.legacy_feature_keys is legacy.legacy_feature_keys
