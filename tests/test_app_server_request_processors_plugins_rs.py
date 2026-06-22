from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.app_server.request_processors_plugins import (
    PluginRequestProcessor,
    PluginRequestProcessorError,
    convert_configured_marketplace_plugin_to_plugin_summary,
    local_plugin_interface_to_info,
    marketplace_plugin_source_to_info,
    plugin_share_principal_from_remote,
    plugin_skills_to_info,
    remote_installed_plugin_visible_scopes,
    remote_plugin_share_discoverability,
    remote_plugin_share_targets,
    remote_plugin_share_update_discoverability,
    share_context_for_source,
    validate_client_plugin_share_targets,
)
from pycodex.app_server.error_code import INVALID_REQUEST_ERROR_CODE
from pycodex.app_server_protocol import (
    PluginAuthPolicy,
    PluginInstallPolicy,
    PluginSharePrincipalRole,
    PluginSharePrincipalType,
    PluginShareTarget,
    PluginShareTargetRole,
)


def test_plugin_request_processor_new_stores_rust_constructor_dependencies() -> None:
    # Rust: codex-app-server/src/request_processors/plugins.rs PluginRequestProcessor::new.
    processor = PluginRequestProcessor.new("auth", "threads", "out", "analytics", "config", "workspace")

    assert processor.auth_manager == "auth"
    assert processor.thread_manager == "threads"
    assert processor.outgoing == "out"
    assert processor.analytics_events_client == "analytics"
    assert processor.config_manager == "config"
    assert processor.workspace_settings_cache == "workspace"


def test_plugin_skills_to_info_preserves_skill_fields_and_disabled_paths() -> None:
    # Rust: plugin_skills_to_info maps SkillMetadata and disables by path membership.
    enabled_skill = SimpleNamespace(
        name="ship",
        description="Ship code",
        short_description="Ship",
        interface=SimpleNamespace(
            display_name="Ship",
            short_description="Ship fast",
            icon_small="small",
            icon_large="large",
            brand_color="#123456",
            default_prompt="go",
        ),
        path_to_skills_md=Path("skills/ship/SKILL.md"),
    )
    disabled_skill = SimpleNamespace(
        name="blocked",
        description="Blocked skill",
        short_description=None,
        interface=None,
        path_to_skills_md=Path("skills/blocked/SKILL.md"),
    )

    summaries = plugin_skills_to_info(
        [enabled_skill, disabled_skill],
        {Path("skills/blocked/SKILL.md")},
    )

    assert [summary.name for summary in summaries] == ["ship", "blocked"]
    assert summaries[0].enabled is True
    assert summaries[0].interface.display_name == "Ship"
    assert summaries[0].path == Path("skills/ship/SKILL.md")
    assert summaries[1].enabled is False
    assert summaries[1].interface is None


def test_local_plugin_interface_to_info_adds_none_url_and_empty_remote_screenshot_fields() -> None:
    # Rust: local_plugin_interface_to_info copies local interface and fills URL fields as None/empty.
    interface = SimpleNamespace(
        display_name="Plugin",
        short_description="Short",
        long_description="Long",
        developer_name="OpenAI",
        category="dev",
        capabilities=("chat",),
        website_url="https://example.test",
        privacy_policy_url=None,
        terms_of_service_url=None,
        default_prompt="hello",
        brand_color="#abcdef",
        composer_icon="icon",
        logo="logo-bytes",
        screenshots=("screen-a",),
    )

    result = local_plugin_interface_to_info(interface)

    assert result.display_name == "Plugin"
    assert result.capabilities == ("chat",)
    assert result.composer_icon_url is None
    assert result.logo_url is None
    assert result.screenshots == ("screen-a",)
    assert result.screenshot_urls == ()


def test_marketplace_plugin_source_to_info_maps_local_and_git_variants() -> None:
    # Rust: marketplace_plugin_source_to_info mirrors Local and Git variants.
    local = marketplace_plugin_source_to_info({"type": "local", "path": "/tmp/plugin"})
    git = marketplace_plugin_source_to_info(
        {"type": "git", "url": "https://repo", "path": "plugins/a", "refName": "main", "sha": "abc"}
    )

    assert local.to_mapping() == {"type": "local", "path": "/tmp/plugin"}
    assert git.to_mapping() == {
        "type": "git",
        "url": "https://repo",
        "path": "plugins/a",
        "ref_name": "main",
        "sha": "abc",
    }


def test_share_context_for_source_only_uses_shared_local_path_mapping() -> None:
    # Rust: share_context_for_source returns Some only for local sources found in the local-path map.
    mapping = {Path("/tmp/plugin"): "remote-1"}

    context = share_context_for_source({"type": "local", "path": Path("/tmp/plugin")}, mapping)

    assert context.remote_plugin_id == "remote-1"
    assert context.remote_version is None
    assert context.discoverability is None
    assert share_context_for_source({"type": "local", "path": Path("/tmp/other")}, mapping) is None
    assert share_context_for_source({"type": "git", "url": "https://repo"}, mapping) is None


def test_convert_configured_marketplace_plugin_to_plugin_summary_maps_policy_and_context() -> None:
    # Rust: convert_configured_marketplace_plugin_to_plugin_summary builds the protocol summary.
    plugin = SimpleNamespace(
        id="local-plugin",
        source={"type": "local", "path": "/tmp/plugin"},
        local_version="1.2.3",
        installed=True,
        enabled=False,
        name="Local Plugin",
        policy=SimpleNamespace(
            installation=PluginInstallPolicy.INSTALLED_BY_DEFAULT,
            authentication=PluginAuthPolicy.ON_INSTALL,
        ),
        interface=None,
        keywords=("local", "tool"),
    )

    summary = convert_configured_marketplace_plugin_to_plugin_summary(plugin, {"/tmp/plugin": "remote-1"})

    assert summary.id == "local-plugin"
    assert summary.remote_plugin_id is None
    assert summary.local_version == "1.2.3"
    assert summary.installed is True
    assert summary.enabled is False
    assert summary.share_context.remote_plugin_id == "remote-1"
    assert summary.source.to_mapping() == {"type": "local", "path": "/tmp/plugin"}
    assert summary.install_policy == PluginInstallPolicy.INSTALLED_BY_DEFAULT
    assert summary.auth_policy == PluginAuthPolicy.ON_INSTALL
    assert summary.keywords == ("local", "tool")


def test_remote_installed_plugin_visible_scopes_tracks_feature_flags() -> None:
    # Rust: RemotePlugin adds Global and PluginSharing adds Workspace.
    features = SimpleNamespace(enabled=lambda name: name in {"RemotePlugin", "PluginSharing"})
    assert remote_installed_plugin_visible_scopes(SimpleNamespace(features=features)) == ("global", "workspace")

    assert remote_installed_plugin_visible_scopes({"features": {"RemotePlugin": True}}) == ("global",)


def test_validate_client_plugin_share_targets_rejects_workspace_principal() -> None:
    # Rust: validate_client_plugin_share_targets rejects workspace principals with invalid_request.
    target = PluginShareTarget(
        principal_type=PluginSharePrincipalType.WORKSPACE,
        principal_id="workspace-1",
        role=PluginShareTargetRole.READER,
    )

    with pytest.raises(PluginRequestProcessorError) as exc_info:
        validate_client_plugin_share_targets([target])

    assert exc_info.value.error.code == INVALID_REQUEST_ERROR_CODE
    assert "shareTargets cannot include workspace principals" in exc_info.value.error.message


def test_remote_plugin_share_converters_preserve_enum_values() -> None:
    # Rust: remote share helpers are one-for-one enum/value conversions.
    targets = remote_plugin_share_targets(
        [
            {"principalType": "user", "principalId": "u1", "role": "reader"},
            {"principalType": "group", "principalId": "g1", "role": "editor"},
        ]
    )

    assert remote_plugin_share_discoverability("LISTED") == "LISTED"
    assert remote_plugin_share_update_discoverability("PRIVATE") == "PRIVATE"
    assert [(target.principal_type, target.principal_id, target.role) for target in targets] == [
        (PluginSharePrincipalType.USER, "u1", PluginShareTargetRole.READER),
        (PluginSharePrincipalType.GROUP, "g1", PluginShareTargetRole.EDITOR),
    ]


def test_plugin_share_principal_from_remote_maps_type_role_id_and_name() -> None:
    # Rust: plugin_share_principal_from_remote copies principal fields and maps role.
    principal = plugin_share_principal_from_remote(
        {
            "principalType": "workspace",
            "principalId": "w1",
            "role": "owner",
            "name": "Workspace",
        }
    )

    assert principal.principal_type == PluginSharePrincipalType.WORKSPACE
    assert principal.principal_id == "w1"
    assert principal.role == PluginSharePrincipalRole.OWNER
    assert principal.name == "Workspace"


def test_public_facade_methods_delegate_to_injected_response_handlers() -> None:
    # Rust public async facade methods return their corresponding response payload.
    async def plugin_list_response(params):
        return {"params": params}

    processor = PluginRequestProcessor.new(
        None,
        None,
        None,
        None,
        None,
        None,
        response_handlers={"plugin_list_response": plugin_list_response},
    )

    assert asyncio.run(processor.plugin_list({"cwds": []})) == {"params": {"cwds": []}}


def test_effective_plugins_changed_clears_plugin_skill_caches_and_refreshes() -> None:
    # Rust: spawn_effective_plugins_changed_task clears plugin/skill caches and queues MCP refresh.
    calls = []

    class CacheManager:
        def __init__(self, name: str) -> None:
            self.name = name

        def clear_cache(self) -> None:
            calls.append(("clear", self.name))

    class ThreadManager:
        def plugins_manager(self):
            return CacheManager("plugins")

        def skills_manager(self):
            return CacheManager("skills")

    class ConfigManager:
        def queue_best_effort_refresh(self, thread_manager, config_manager) -> None:
            calls.append(("refresh", thread_manager is not None, config_manager is self))

    config_manager = ConfigManager()
    processor = PluginRequestProcessor.new(
        None,
        ThreadManager(),
        None,
        None,
        config_manager,
        None,
    )

    processor.effective_plugins_changed_callback()()

    assert calls == [
        ("clear", "plugins"),
        ("clear", "skills"),
        ("refresh", True, True),
    ]
