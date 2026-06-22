"""Parity tests for ``app-server/src/request_processors/config_processor.rs``.

Rust source anchors:
- ``requirements_api_includes_allow_managed_hooks_only``
- ``requirements_api_includes_allow_appshots``
- ``requirements_api_includes_computer_use_requirements``
- source contracts for feature read/write and runtime enablement handling.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.app_server.config_manager_service import ConfigManagerError
from pycodex.app_server.request_processors_config_processor import (
    SUPPORTED_EXPERIMENTAL_FEATURE_ENABLEMENT,
    ConfigRequestProcessor,
    ConfigRequestProcessorError,
    collect_plugin_enabled_candidates,
    map_requirements_toml_to_api,
)
from pycodex.app_server_protocol import (
    Config,
    ConfigBatchWriteParams,
    ConfigEdit,
    ConfigLayerMetadata,
    ConfigLayerSource,
    ConfigReadParams,
    ConfigReadResponse,
    ConfigValueWriteParams,
    ConfigWriteErrorCode,
    ConfigWriteResponse,
    MergeStrategy,
    WriteStatus,
)
from pycodex.app_server_protocol.shared import SandboxMode
from pycodex.protocol import WebSearchMode


class Features:
    def __init__(self, enabled):
        self.enabled_values = dict(enabled)

    def enabled(self, key):
        return self.enabled_values.get(key, False)

    def apps_enabled_for_auth(self, uses_backend):
        return uses_backend and self.enabled("apps")


class ConfigManager:
    def __init__(self):
        self.latest = SimpleNamespace(features=Features({"apps": True, "plugins": True}))
        self.read_response = ConfigReadResponse(
            config=Config(additional={"features": "stale"}),
            origins={"model": ConfigLayerMetadata(ConfigLayerSource.session_flags(), "v0")},
        )
        self.extended = []
        self.writes = []
        self.batches = []

    async def read(self, params):
        self.read_params = params
        return self.read_response

    async def read_requirements(self):
        return None

    async def load_latest_config(self, fallback_cwd):
        self.fallback_cwd = fallback_cwd
        return self.latest

    async def write_value(self, params):
        self.writes.append(params)
        return ConfigWriteResponse(status=WriteStatus.OK, version="v1", file_path=Path.cwd())

    async def batch_write(self, params):
        self.batches.append(params)
        return ConfigWriteResponse(status=WriteStatus.OK, version="v2", file_path=Path.cwd())

    def extend_runtime_feature_enablement(self, enablement):
        self.extended.append(dict(enablement))


class CacheManager:
    def __init__(self):
        self.cleared = 0

    def clear_cache(self):
        self.cleared += 1


class Thread:
    def __init__(self):
        self.refreshed = []

    async def refresh_runtime_config(self, config):
        self.refreshed.append(config)


class ThreadManager:
    def __init__(self):
        self.plugins = CacheManager()
        self.skills = CacheManager()
        self.thread = Thread()

    def plugins_manager(self):
        return self.plugins

    def skills_manager(self):
        return self.skills

    async def list_thread_ids(self):
        return ["thread-1", "missing"]

    async def get_thread(self, thread_id):
        if thread_id == "missing":
            raise RuntimeError("missing")
        return self.thread


class Outgoing:
    def __init__(self):
        self.responses = []
        self.notifications = []

    async def send_response_as(self, request_id, payload):
        self.responses.append((request_id, payload))

    async def send_server_notification(self, notification):
        self.notifications.append(notification)


class AuthManager:
    async def auth(self):
        return SimpleNamespace(uses_codex_backend=lambda: True)


class Analytics:
    def __init__(self):
        self.enabled = []
        self.disabled = []

    def track_plugin_enabled(self, metadata):
        self.enabled.append(metadata)

    def track_plugin_disabled(self, metadata):
        self.disabled.append(metadata)


def processor():
    config_manager = ConfigManager()
    outgoing = Outgoing()
    thread_manager = ThreadManager()
    analytics = Analytics()
    return (
        ConfigRequestProcessor(outgoing, config_manager, AuthManager(), thread_manager, analytics),
        config_manager,
        outgoing,
        thread_manager,
        analytics,
    )


def test_read_replaces_non_object_features_and_injects_supported_enablement():
    proc, config_manager, _, _, _ = processor()

    response = asyncio.run(proc.read(ConfigReadParams(cwd="C:/work")))

    features = response.config.additional["features"]
    assert config_manager.fallback_cwd == "C:/work"
    assert tuple(features) == SUPPORTED_EXPERIMENTAL_FEATURE_ENABLEMENT
    assert features["apps"] is True
    assert features["plugins"] is True
    assert features["memories"] is False


def test_requirements_api_includes_allow_managed_hooks_only():
    mapped = map_requirements_toml_to_api(
        {
            "allowed_permissions": ["managed-standard", "managed-build"],
            "allow_managed_hooks_only": True,
        }
    )

    assert mapped.allowed_permissions == ("managed-standard", "managed-build")
    assert mapped.allow_managed_hooks_only is True
    assert mapped.hooks is None


def test_requirements_api_includes_allow_appshots():
    mapped = map_requirements_toml_to_api({"allow_appshots": False})

    assert mapped.allow_appshots is False
    assert mapped.hooks is None


def test_requirements_api_includes_computer_use_requirements():
    mapped = map_requirements_toml_to_api(
        {"computer_use": {"allow_locked_computer_use": False}}
    )

    assert mapped.computer_use is not None
    assert mapped.computer_use.allow_locked_computer_use is False


def test_requirements_mapping_filters_external_sandbox_and_appends_disabled_web_search():
    mapped = map_requirements_toml_to_api(
        {
            "allowed_sandbox_modes": ["read-only", "external-sandbox", "danger-full-access"],
            "allowed_web_search_modes": ["live"],
        }
    )

    assert mapped.allowed_sandbox_modes == (SandboxMode.READ_ONLY, SandboxMode.DANGER_FULL_ACCESS)
    assert mapped.allowed_web_search_modes == (WebSearchMode.LIVE, WebSearchMode.DISABLED)


def test_batch_write_reloads_user_config_and_clears_caches_after_success():
    proc, _, _, thread_manager, _ = processor()
    params = ConfigBatchWriteParams(
        edits=(ConfigEdit("model", "gpt-test", MergeStrategy.REPLACE),),
        reload_user_config=True,
    )

    response = asyncio.run(proc.batch_write(params))

    assert response.version == "v2"
    assert thread_manager.thread.refreshed
    assert thread_manager.plugins.cleared == 1
    assert thread_manager.skills.cleared == 1


def test_value_write_maps_config_manager_write_errors_and_skips_cache_clear():
    proc, config_manager, _, thread_manager, _ = processor()

    async def fail(_params):
        raise ConfigManagerError.write(ConfigWriteErrorCode.CONFIG_VERSION_CONFLICT, "stale")

    config_manager.write_value = fail

    with pytest.raises(ConfigRequestProcessorError) as exc:
        asyncio.run(
            proc.value_write(
                ConfigValueWriteParams("model", "gpt-test", MergeStrategy.REPLACE)
            )
        )

    assert exc.value.error.message == "stale"
    assert exc.value.error.data == {"config_write_error_code": "configVersionConflict"}
    assert thread_manager.plugins.cleared == 0


def test_experimental_feature_enablement_set_validates_keys_and_sends_response():
    proc, config_manager, outgoing, thread_manager, _ = processor()

    result = asyncio.run(
        proc.experimental_feature_enablement_set("req-1", {"enablement": {"apps": True}})
    )

    assert result is None
    assert config_manager.extended == [{"apps": True}]
    assert outgoing.responses[0][0] == "req-1"
    assert outgoing.responses[0][1].enablement == {"apps": True}
    assert outgoing.notifications == [{"method": "appListUpdated"}]
    assert thread_manager.plugins.cleared == 1


def test_experimental_feature_enablement_set_rejects_unsupported_alias_and_unknown():
    proc, _, _, _, _ = processor()

    with pytest.raises(ConfigRequestProcessorError) as unsupported:
        asyncio.run(proc.set_experimental_feature_enablement({"enablement": {"browser_use": True}}))
    assert "unsupported feature enablement `browser_use`" in unsupported.value.error.message

    with pytest.raises(ConfigRequestProcessorError) as alias:
        asyncio.run(proc.set_experimental_feature_enablement({"enablement": {"connectors": True}}))
    assert "use canonical feature key `apps`" in alias.value.error.message

    with pytest.raises(ConfigRequestProcessorError) as unknown:
        asyncio.run(proc.set_experimental_feature_enablement({"enablement": {"not_a_feature": True}}))
    assert "invalid feature enablement `not_a_feature`" == unknown.value.error.message


def test_plugin_enabled_candidates_feed_analytics_after_successful_write():
    proc, _, _, _, analytics = processor()

    asyncio.run(
        proc.value_write(
            ConfigValueWriteParams("plugins.my_plugin.enabled", True, MergeStrategy.REPLACE)
        )
    )

    assert collect_plugin_enabled_candidates((("plugins.my_plugin.enabled", True),)) == {
        "my_plugin": True
    }
    assert analytics.enabled == [{"plugin_id": "my_plugin"}]
