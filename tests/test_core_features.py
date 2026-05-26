import sys
import unittest

from pycodex.core import (
    AppsMcpPathOverrideConfigToml,
    Feature,
    FeatureConfigSource,
    FeatureOverrides,
    FEATURES,
    FeatureToml,
    Features,
    FeaturesToml,
    MultiAgentV2ConfigToml,
    NetworkProxyConfigToml,
    StageKind,
    canonical_feature_for_key,
    feature_for_key,
    is_known_feature_key,
    legacy_feature_keys,
    unstable_features_warning_event,
)
from pycodex.protocol import EventMsg, WarningEvent


class CoreFeaturesTests(unittest.TestCase):
    def test_under_development_features_are_disabled_by_default(self) -> None:
        for spec in FEATURES:
            if spec.stage.kind is StageKind.UNDER_DEVELOPMENT:
                self.assertFalse(spec.default_enabled, spec.key)

    def test_default_enabled_features_are_stable_removed_or_terminal_reflow(self) -> None:
        for spec in FEATURES:
            if spec.default_enabled:
                self.assertTrue(
                    spec.stage.kind in (StageKind.STABLE, StageKind.REMOVED)
                    or spec.id is Feature.TERMINAL_RESIZE_REFLOW,
                    spec.key,
                )

    def test_known_feature_metadata_matches_upstream_registry(self) -> None:
        self.assertEqual(Feature.USE_LEGACY_LANDLOCK.stage().kind, StageKind.DEPRECATED)
        self.assertFalse(Feature.USE_LEGACY_LANDLOCK.default_enabled())
        self.assertEqual(Feature.USE_LINUX_SANDBOX_BWRAP.stage().kind, StageKind.REMOVED)
        self.assertEqual(Feature.GUARDIAN_APPROVAL.stage().kind, StageKind.STABLE)
        self.assertTrue(Feature.GUARDIAN_APPROVAL.default_enabled())
        self.assertEqual(Feature.NETWORK_PROXY.stage().kind, StageKind.EXPERIMENTAL)
        self.assertFalse(Feature.NETWORK_PROXY.default_enabled())
        self.assertEqual(Feature.UNIFIED_EXEC.default_enabled(), sys.platform != "win32")

    def test_feature_lookup_accepts_canonical_and_legacy_keys(self) -> None:
        self.assertEqual(feature_for_key("apply_patch_freeform"), Feature.APPLY_PATCH_FREEFORM)
        self.assertEqual(feature_for_key("plugin_hooks"), Feature.PLUGIN_HOOKS)
        self.assertEqual(feature_for_key("remote_compaction_v2"), Feature.REMOTE_COMPACTION_V2)
        self.assertEqual(feature_for_key("responses_websocket_response_processed"), Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED)
        self.assertEqual(feature_for_key("terminal_resize_reflow"), Feature.TERMINAL_RESIZE_REFLOW)
        self.assertEqual(feature_for_key("in_app_browser"), Feature.IN_APP_BROWSER)
        self.assertEqual(feature_for_key("browser_use"), Feature.BROWSER_USE)
        self.assertEqual(feature_for_key("browser_use_external"), Feature.BROWSER_USE_EXTERNAL)
        self.assertEqual(feature_for_key("computer_use"), Feature.COMPUTER_USE)
        self.assertEqual(feature_for_key("use_linux_sandbox_bwrap"), Feature.USE_LINUX_SANDBOX_BWRAP)
        self.assertEqual(feature_for_key("image_detail_original"), Feature.IMAGE_DETAIL_ORIGINAL)
        self.assertEqual(feature_for_key("auth_elicitation"), Feature.AUTH_ELICITATION)
        self.assertEqual(feature_for_key("workspace_dependencies"), Feature.WORKSPACE_DEPENDENCIES)
        self.assertEqual(feature_for_key("telepathy"), Feature.CHRONICLE)
        self.assertEqual(feature_for_key("collab"), Feature.COLLAB)
        self.assertEqual(feature_for_key("codex_hooks"), Feature.CODEX_HOOKS)
        self.assertIsNone(feature_for_key("made_up_feature"))
        self.assertEqual(canonical_feature_for_key("collab"), None)
        self.assertTrue(is_known_feature_key("connectors"))
        self.assertIn("experimental_use_unified_exec_tool", legacy_feature_keys())

    def test_dependency_normalization_is_one_way(self) -> None:
        code_mode_features = Features.with_defaults()
        code_mode_features.enable(Feature.CODE_MODE_ONLY)
        code_mode_features.normalize_dependencies()
        self.assertTrue(code_mode_features.enabled(Feature.CODE_MODE_ONLY))
        self.assertTrue(code_mode_features.enabled(Feature.CODE_MODE))

        fanout_features = Features.with_defaults()
        fanout_features.enable(Feature.SPAWN_CSV)
        fanout_features.normalize_dependencies()
        self.assertTrue(fanout_features.enabled(Feature.SPAWN_CSV))
        self.assertTrue(fanout_features.enabled(Feature.COLLAB))

        collab_features = Features.with_defaults()
        collab_features.enable(Feature.COLLAB)
        collab_features.normalize_dependencies()
        self.assertTrue(collab_features.enabled(Feature.COLLAB))
        self.assertFalse(collab_features.enabled(Feature.SPAWN_CSV))

    def test_apps_require_feature_flag_and_chatgpt_auth(self) -> None:
        features = Features.with_defaults()
        features.disable(Feature.APPS)
        self.assertFalse(features.apps_enabled_for_auth(False))
        self.assertFalse(features.apps_enabled_for_auth(True))

        features.enable(Feature.APPS)
        self.assertFalse(features.apps_enabled_for_auth(False))
        self.assertTrue(features.apps_enabled_for_auth(True))

    def test_apply_map_records_deprecated_use_legacy_landlock_notice(self) -> None:
        features = Features.with_defaults()
        features.apply_map({"use_legacy_landlock": True})

        usages = features.legacy_feature_usages()
        self.assertEqual(len(usages), 1)
        self.assertEqual(usages[0].alias, "features.use_legacy_landlock")
        self.assertEqual(usages[0].feature, Feature.USE_LEGACY_LANDLOCK)
        self.assertEqual(
            usages[0].summary,
            "`[features].use_legacy_landlock` is deprecated and will be removed soon.",
        )
        self.assertEqual(
            usages[0].details,
            "Remove this setting to stop opting into the legacy Linux sandbox behavior.",
        )
        self.assertTrue(features.use_legacy_landlock())

    def test_removed_feature_keys_are_ignored_by_config_application(self) -> None:
        for key in (
            "image_detail_original",
            "undo",
            "js_repl",
            "js_repl_tools_only",
            "apply_patch_freeform",
            "plugin_hooks",
            "remote_control",
            "tool_search",
        ):
            features = Features.from_sources(
                FeatureConfigSource(features=FeaturesToml.from_entries({key: True})),
                FeatureConfigSource(),
                FeatureOverrides(),
            )
            self.assertEqual(features, Features.with_defaults(), key)

    def test_from_sources_applies_base_profile_and_overrides(self) -> None:
        base = FeaturesToml.from_entries({"plugins": True})
        profile = FeaturesToml.from_entries({"code_mode_only": True})

        features = Features.from_sources(
            FeatureConfigSource(features=base),
            FeatureConfigSource(features=profile),
            FeatureOverrides(web_search_request=False),
        )

        self.assertTrue(features.enabled(Feature.PLUGINS))
        self.assertTrue(features.enabled(Feature.CODE_MODE_ONLY))
        self.assertTrue(features.enabled(Feature.CODE_MODE))
        self.assertFalse(features.enabled(Feature.APPLY_PATCH_FREEFORM))
        self.assertFalse(features.enabled(Feature.WEB_SEARCH_REQUEST))

    def test_legacy_toggle_source_maps_to_unified_exec(self) -> None:
        features = Features.from_sources(
            FeatureConfigSource(experimental_use_unified_exec_tool=True),
            FeatureConfigSource(),
            FeatureOverrides(),
        )

        self.assertTrue(features.enabled(Feature.UNIFIED_EXEC))
        self.assertEqual(
            features.legacy_feature_usages()[0].alias,
            "experimental_use_unified_exec_tool",
        )

    def test_feature_toml_special_configs_report_enabled_entries(self) -> None:
        features_toml = FeaturesToml(
            multi_agent_v2=FeatureToml.config(
                MultiAgentV2ConfigToml(
                    enabled=True,
                    max_concurrent_threads_per_session=4,
                    min_wait_timeout_ms=2500,
                    max_wait_timeout_ms=120000,
                    default_wait_timeout_ms=30000,
                    usage_hint_enabled=False,
                    usage_hint_text="Custom delegation guidance.",
                    root_agent_usage_hint_text="Root guidance.",
                    subagent_usage_hint_text="Subagent guidance.",
                    tool_namespace="agents",
                    hide_spawn_agent_metadata=True,
                    non_code_mode_only=True,
                )
            ),
            apps_mcp_path_override=FeatureToml.config(AppsMcpPathOverrideConfigToml(path="apps-mcp")),
            network_proxy=FeatureToml.enabled_toggle(False),
        )

        self.assertEqual(
            features_toml.entries(),
            {
                "multi_agent_v2": True,
                "apps_mcp_path_override": True,
                "network_proxy": False,
            },
        )

    def test_config_without_enabled_does_not_enable_feature(self) -> None:
        features_toml = FeaturesToml(
            multi_agent_v2=FeatureToml.config(MultiAgentV2ConfigToml(usage_hint_enabled=False))
        )

        features = Features.from_sources(
            FeatureConfigSource(features=features_toml),
            FeatureConfigSource(),
            FeatureOverrides(),
        )

        self.assertFalse(features.enabled(Feature.MULTI_AGENT_V2))
        self.assertEqual(features_toml.entries(), {})

    def test_materialize_resolved_enabled_writes_all_features_and_preserves_config(self) -> None:
        features = Features.with_defaults()
        features.enable(Feature.CODE_MODE)
        features.enable(Feature.MULTI_AGENT_V2)
        features.enable(Feature.NETWORK_PROXY)

        features_toml = FeaturesToml(
            multi_agent_v2=FeatureToml.config(
                MultiAgentV2ConfigToml(enabled=False, min_wait_timeout_ms=2500)
            ),
            network_proxy=FeatureToml.config(
                NetworkProxyConfigToml(enabled=False, proxy_url="http://127.0.0.1:43128")
            ),
        )

        features_toml.materialize_resolved_enabled(features)

        entries = features_toml.entries()
        for spec in FEATURES:
            self.assertEqual(entries.get(spec.key), features.enabled(spec.id), spec.key)
        self.assertEqual(features_toml.multi_agent_v2.value.enabled, True)
        self.assertEqual(features_toml.multi_agent_v2.value.min_wait_timeout_ms, 2500)
        self.assertEqual(features_toml.network_proxy.value.enabled, True)
        self.assertEqual(features_toml.network_proxy.value.proxy_url, "http://127.0.0.1:43128")

    def test_unstable_warning_event_only_mentions_enabled_under_development_features(self) -> None:
        configured_features = {
            "child_agents_md": True,
            "personality": True,
            "unknown": True,
        }
        features = Features.with_defaults()
        features.enable(Feature.CHILD_AGENTS_MD)

        warning = unstable_features_warning_event(
            configured_features,
            suppress_unstable_features_warning=False,
            features=features,
            config_path="/tmp/config.toml",
        )

        self.assertIsNotNone(warning)
        self.assertEqual(warning.msg, EventMsg.with_payload("warning", WarningEvent(warning.msg.payload.message)))
        self.assertIn("child_agents_md", warning.msg.payload.message)
        self.assertNotIn("personality", warning.msg.payload.message)
        self.assertIn("/tmp/config.toml", warning.msg.payload.message)
        self.assertIsNone(
            unstable_features_warning_event(
                configured_features,
                suppress_unstable_features_warning=True,
                features=features,
                config_path="/tmp/config.toml",
            )
        )


if __name__ == "__main__":
    unittest.main()
