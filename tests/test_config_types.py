import unittest
from pathlib import Path

from pycodex.config import (
    AltScreenMode,
    AppConfig,
    AppToolApproval,
    AppsConfigToml,
    AppsDefaultConfig,
    AuthCredentialsStoreMode,
    History,
    HistoryPersistence,
    MarketplaceConfig,
    MarketplaceSourceType,
    MemoriesConfig,
    MemoriesToml,
    ModelAvailabilityNuxConfig,
    Notice,
    NotificationCondition,
    NotificationMethod,
    Notifications,
    OAuthCredentialsStoreMode,
    OtelConfig,
    OtelConfigToml,
    OtelExporterKind,
    OtelHttpProtocol,
    PluginConfig,
    PluginMcpServerConfig,
    SandboxWorkspaceWrite,
    SessionPickerViewMode,
    ShellEnvironmentPolicyToml,
    SkillConfig,
    ToolSuggestDisabledTool,
    ToolSuggestDiscoverableType,
    Tui,
    TuiKeymap,
    TuiNotificationSettings,
    TuiPetAnchor,
    UriBasedFileOpener,
    WindowsSandboxModeToml,
    WindowsToml,
)


class ConfigTypesTests(unittest.TestCase):
    def test_memories_config_clamps_count_limits_to_nonzero_values(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/types.rs
        # Rust test: memories_config_clamps_count_limits_to_nonzero_values
        config = MemoriesConfig.from_toml(
            MemoriesToml(
                max_raw_memories_for_consolidation=0,
                max_rollouts_per_startup=0,
            )
        )

        self.assertEqual(
            config,
            MemoriesConfig(
                max_raw_memories_for_consolidation=1,
                max_rollouts_per_startup=1,
            ),
        )

    def test_memories_config_clamps_rate_limit_remaining_threshold(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/types.rs
        # Rust test: memories_config_clamps_rate_limit_remaining_threshold
        self.assertEqual(
            MemoriesConfig.from_toml(MemoriesToml(min_rate_limit_remaining_percent=101)),
            MemoriesConfig(min_rate_limit_remaining_percent=100),
        )
        self.assertEqual(
            MemoriesConfig.from_toml(MemoriesToml(min_rate_limit_remaining_percent=-1)),
            MemoriesConfig(min_rate_limit_remaining_percent=0),
        )

    def test_memories_toml_alias_and_defaults_match_rust_contract(self) -> None:
        # Rust source: src/types.rs MemoriesToml uses serde alias
        # `no_memories_if_mcp_or_web_search` for `disable_on_external_context`.
        config = MemoriesConfig.from_toml(
            {
                "no_memories_if_mcp_or_web_search": True,
                "generate_memories": False,
                "use_memories": False,
                "dedicated_tools": True,
                "extract_model": "gpt-5-mini",
                "consolidation_model": "gpt-5",
            }
        )

        self.assertEqual(
            config,
            MemoriesConfig(
                disable_on_external_context=True,
                generate_memories=False,
                use_memories=False,
                dedicated_tools=True,
                extract_model="gpt-5-mini",
                consolidation_model="gpt-5",
            ),
        )

    def test_memories_toml_rejects_non_rust_shapes(self) -> None:
        with self.assertRaisesRegex(TypeError, "memories toml"):
            MemoriesToml.from_mapping(1)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "generate_memories"):
            MemoriesToml.from_mapping({"generate_memories": "yes"})
        with self.assertRaisesRegex(TypeError, "max_rollouts_per_startup"):
            MemoriesToml.from_mapping({"max_rollouts_per_startup": True})
        with self.assertRaisesRegex(TypeError, "extract_model"):
            MemoriesToml.from_mapping({"extract_model": 123})

    def test_skill_config_with_name_selector_matches_rust_test(self) -> None:
        # Rust test: deserialize_skill_config_with_name_selector.
        cfg = SkillConfig.from_mapping({"name": "github:yeet", "enabled": False})

        self.assertEqual(cfg.name, "github:yeet")
        self.assertIsNone(cfg.path)
        self.assertFalse(cfg.enabled)

    def test_skill_config_with_path_selector_matches_rust_test(self) -> None:
        # Rust test: deserialize_skill_config_with_path_selector.
        cfg = SkillConfig.from_mapping({"path": "/tmp/skills/demo/SKILL.md", "enabled": False})

        self.assertEqual(cfg.path, Path("/tmp/skills/demo/SKILL.md"))
        self.assertIsNone(cfg.name)
        self.assertFalse(cfg.enabled)

    def test_basic_type_enums_and_defaults_match_rust_contract(self) -> None:
        self.assertEqual(str(SessionPickerViewMode.DENSE), "dense")
        self.assertEqual(str(SessionPickerViewMode.COMFORTABLE), "comfortable")
        self.assertEqual(AuthCredentialsStoreMode.FILE.value, "file")
        self.assertEqual(OAuthCredentialsStoreMode.AUTO.value, "auto")
        self.assertEqual(WindowsToml.from_mapping({"sandbox": "elevated"}).sandbox, WindowsSandboxModeToml.ELEVATED)
        self.assertEqual(UriBasedFileOpener.VSCODE.get_scheme(), "vscode")
        self.assertIsNone(UriBasedFileOpener.NONE.get_scheme())
        self.assertEqual(History.from_mapping({}), History())
        self.assertEqual(History.from_mapping({"persistence": "none"}).persistence, HistoryPersistence.NONE)

    def test_tool_suggest_and_notification_shapes(self) -> None:
        disabled = ToolSuggestDisabledTool.plugin(" github ")

        self.assertEqual(disabled.normalized(), ToolSuggestDisabledTool(ToolSuggestDiscoverableType.PLUGIN, "github"))
        self.assertIsNone(ToolSuggestDisabledTool.connector("  ").normalized())
        self.assertEqual(Notifications.from_value(True).enabled, True)
        self.assertEqual(Notifications.from_value(["notify-send", "done"]).custom, ("notify-send", "done"))
        settings = TuiNotificationSettings.from_mapping(
            {
                "notifications": False,
                "notification_method": "bel",
                "notification_condition": "always",
            }
        )
        self.assertEqual(settings.method, NotificationMethod.BEL)
        self.assertEqual(settings.condition, NotificationCondition.ALWAYS)

    def test_tui_defaults_and_overrides_match_rust_contract(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/types.rs
        # Behavior contract: Tui aggregate defaults and serde field shapes.
        defaults = Tui.from_mapping({})

        self.assertEqual(defaults.notification_settings, TuiNotificationSettings())
        self.assertTrue(defaults.animations)
        self.assertTrue(defaults.show_tooltips)
        self.assertFalse(defaults.vim_mode_default)
        self.assertFalse(defaults.raw_output_mode)
        self.assertEqual(defaults.alternate_screen, AltScreenMode.AUTO)
        self.assertIsNone(defaults.status_line)
        self.assertTrue(defaults.status_line_use_colors)
        self.assertIsNone(defaults.terminal_title)
        self.assertEqual(defaults.pet_anchor, TuiPetAnchor.COMPOSER)
        self.assertIsNone(defaults.session_picker_view)
        self.assertEqual(defaults.keymap, TuiKeymap())
        self.assertEqual(defaults.model_availability_nux, ModelAvailabilityNuxConfig({}))
        self.assertIsNone(defaults.terminal_resize_reflow_max_rows)

        tui = Tui.from_mapping(
            {
                "notifications": False,
                "notification_method": "bel",
                "notification_condition": "always",
                "animations": False,
                "show_tooltips": False,
                "vim_mode_default": True,
                "raw_output_mode": True,
                "alternate_screen": "never",
                "status_line": ["model-with-reasoning", "current-dir"],
                "status_line_use_colors": False,
                "terminal_title": ["activity"],
                "theme": "dark",
                "pet": "dewey",
                "pet_anchor": "screen-bottom",
                "session_picker_view": "comfortable",
                "keymap": {"global": {"open_transcript": "ctrl-o"}},
                "model_availability_nux": {"gpt-5": 2},
                "terminal_resize_reflow_max_rows": 0,
            }
        )

        self.assertEqual(tui.notification_settings.method, NotificationMethod.BEL)
        self.assertFalse(tui.animations)
        self.assertFalse(tui.show_tooltips)
        self.assertTrue(tui.vim_mode_default)
        self.assertTrue(tui.raw_output_mode)
        self.assertEqual(tui.alternate_screen, AltScreenMode.NEVER)
        self.assertEqual(tui.status_line, ("model-with-reasoning", "current-dir"))
        self.assertFalse(tui.status_line_use_colors)
        self.assertEqual(tui.terminal_title, ("activity",))
        self.assertEqual(tui.theme, "dark")
        self.assertEqual(tui.pet, "dewey")
        self.assertEqual(tui.pet_anchor, TuiPetAnchor.SCREEN_BOTTOM)
        self.assertEqual(tui.session_picker_view, SessionPickerViewMode.COMFORTABLE)
        self.assertEqual(tui.keymap.to_mapping(), {"global": {"open_transcript": "ctrl-o"}})
        self.assertEqual(tui.model_availability_nux, ModelAvailabilityNuxConfig({"gpt-5": 2}))
        self.assertEqual(tui.terminal_resize_reflow_max_rows, 0)

    def test_apps_otel_notice_plugin_marketplace_and_sandbox_shapes(self) -> None:
        apps = AppsConfigToml.from_mapping(
            {
                "_default": {"enabled": False},
                "github": {
                    "default_tools_approval_mode": "approve",
                    "tools": {"repos/list": {"enabled": True, "approval_mode": "prompt"}},
                },
            }
        )
        self.assertEqual(apps.default, AppsDefaultConfig(enabled=False))
        self.assertEqual(apps.apps["github"].default_tools_approval_mode, AppToolApproval.APPROVE)
        self.assertEqual(apps.apps["github"].tools.tools["repos/list"].approval_mode, AppToolApproval.PROMPT)
        self.assertEqual(AppConfig.from_mapping({}).enabled, True)

        otel = OtelConfig.from_toml(
            OtelConfigToml.from_mapping(
                {
                    "environment": "prod",
                    "exporter": {
                        "type": "otlp-http",
                        "endpoint": "https://otel.example",
                        "protocol": "json",
                    },
                }
            )
        )
        self.assertEqual(otel.environment, "prod")
        self.assertEqual(
            otel.exporter,
            OtelExporterKind.otlp_http("https://otel.example", protocol=OtelHttpProtocol.JSON),
        )
        self.assertEqual(OtelConfig().metrics_exporter, OtelExporterKind.statsig())

        notice = Notice.from_mapping(
            {
                "hide_gpt-5.1-codex-max_migration_prompt": True,
                "model_migrations": {"old": "new"},
                "external_config_migration_prompts": {"home": False, "projects": {"/repo": True}},
            }
        )
        self.assertTrue(notice.hide_gpt_5_1_codex_max_migration_prompt)
        self.assertEqual(notice.model_migrations, {"old": "new"})
        self.assertEqual(notice.external_config_migration_prompts.projects, {"/repo": True})

        plugin = PluginConfig.from_mapping(
            {
                "mcp_servers": {
                    "docs": {
                        "enabled": False,
                        "default_tools_approval_mode": "auto",
                        "enabled_tools": ["search"],
                    }
                }
            }
        )
        self.assertEqual(
            plugin.mcp_servers["docs"],
            PluginMcpServerConfig(
                enabled=False,
                default_tools_approval_mode=AppToolApproval.AUTO,
                enabled_tools=("search",),
                disabled_tools=None,
                tools={},
            ),
        )

        marketplace = MarketplaceConfig.from_mapping(
            {"source_type": "git", "source": "https://example/repo", "ref": "main", "sparse_paths": ["skills"]}
        )
        self.assertEqual(marketplace.source_type, MarketplaceSourceType.GIT)
        self.assertEqual(marketplace.ref_name, "main")
        self.assertEqual(marketplace.sparse_paths, ("skills",))

        sandbox = SandboxWorkspaceWrite.from_mapping(
            {"writable_roots": ["/tmp/work"], "network_access": True, "exclude_slash_tmp": True}
        )
        self.assertEqual(sandbox.writable_roots, (Path("/tmp/work"),))
        self.assertTrue(sandbox.to_sandbox_settings()["network_access"])

    def test_shell_environment_policy_toml_defaults_and_overrides(self) -> None:
        self.assertEqual(
            ShellEnvironmentPolicyToml.from_mapping({}).to_policy_mapping(),
            {
                "inherit": "all",
                "ignore_default_excludes": True,
                "exclude": (),
                "set": {},
                "include_only": (),
                "use_profile": False,
            },
        )
        self.assertEqual(
            ShellEnvironmentPolicyToml.from_mapping(
                {
                    "inherit": "none",
                    "ignore_default_excludes": False,
                    "exclude": ["SECRET_.*"],
                    "set": {"A": "B"},
                    "include_only": ["PATH"],
                    "experimental_use_profile": True,
                }
            ).to_policy_mapping(),
            {
                "inherit": "none",
                "ignore_default_excludes": False,
                "exclude": ("SECRET_.*",),
                "set": {"A": "B"},
                "include_only": ("PATH",),
                "use_profile": True,
            },
        )

    def test_new_type_shapes_reject_unknown_or_invalid_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown fields for WindowsToml"):
            WindowsToml.from_mapping({"extra": True})
        with self.assertRaisesRegex(TypeError, "notifications"):
            Notifications.from_value(1)
        with self.assertRaisesRegex(TypeError, "tools must be a table"):
            PluginMcpServerConfig.from_mapping({"tools": []})
        with self.assertRaisesRegex(ValueError, "unknown fields for Tui"):
            Tui.from_mapping({"unknown": True})
        with self.assertRaisesRegex(ValueError, "terminal_resize_reflow_max_rows"):
            Tui.from_mapping({"terminal_resize_reflow_max_rows": -1})
        with self.assertRaisesRegex(TypeError, "keymap must be a table"):
            Tui.from_mapping({"keymap": []})


if __name__ == "__main__":
    unittest.main()
