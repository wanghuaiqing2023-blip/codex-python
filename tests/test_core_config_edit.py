import asyncio
import tempfile
import unittest
from pathlib import Path

from pycodex.core import (
    ConfigEdit,
    ConfigEditError,
    ConfigEditKind,
    ConfigEditsBuilder,
    McpServerConfig,
    McpServerTransportConfig,
    SessionPickerViewMode,
    SkillConfigSelector,
    ToolSuggestDiscoverableType,
    ToolSuggestDisabledTool,
    add_tool_suggest_disabled_tool_edit,
    apply_blocking,
    apply_config_edit,
    apply_config_edits,
    clear_legacy_windows_sandbox_key_edits,
    dumps_toml_mapping,
    keymap_binding_clear_edit,
    keymap_binding_edit,
    keymap_bindings_edit,
    model_availability_nux_count_edits,
    model_selection_edits,
    normalize_skill_config_path,
    notice_external_config_migration_prompt_home_last_prompted_at_edit,
    notice_external_config_migration_prompt_project_last_prompted_at_edit,
    notice_hide_external_config_migration_prompt_home_edit,
    notice_hide_external_config_migration_prompt_project_edit,
    notice_hide_full_access_warning_edit,
    notice_hide_model_migration_prompt_edit,
    notice_hide_rate_limit_model_nudge_edit,
    notice_hide_world_writable_warning_edit,
    personality_edit,
    project_trust_key,
    project_trust_level_edit,
    read_toml_mapping,
    realtime_microphone_edit,
    realtime_speaker_edit,
    realtime_voice_edit,
    record_model_migration_seen_edit,
    replace_mcp_servers_edit,
    session_picker_view_edit,
    service_tier_edit,
    set_feature_enabled_edit,
    set_skill_config_by_name_edit,
    set_skill_config_edit,
    status_line_items_edit,
    status_line_use_colors_edit,
    syntax_theme_edit,
    terminal_title_items_edit,
    tui_pet_edit,
    windows_sandbox_mode_edit,
)


class CoreConfigEditTests(unittest.TestCase):
    def test_set_feature_enabled_sets_enabled_or_default_true_feature(self) -> None:
        enable = set_feature_enabled_edit("network_proxy", True)
        disable_default_true = set_feature_enabled_edit("shell_tool", False)

        self.assertEqual(enable.kind, ConfigEditKind.SET_PATH)
        self.assertEqual(enable.segments, ("features", "network_proxy"))
        self.assertIs(enable.value, True)
        self.assertEqual(disable_default_true.kind, ConfigEditKind.SET_PATH)
        self.assertEqual(disable_default_true.segments, ("features", "shell_tool"))
        self.assertIs(disable_default_true.value, False)

    def test_set_feature_enabled_clears_disabled_default_false_feature(self) -> None:
        edit = set_feature_enabled_edit("network_proxy", False)

        self.assertEqual(edit.kind, ConfigEditKind.CLEAR_PATH)
        self.assertEqual(edit.segments, ("features", "network_proxy"))

    def test_apply_config_edit_creates_nested_tables_and_tracks_mutation(self) -> None:
        config = {"features": False}

        self.assertTrue(apply_config_edit(config, ConfigEdit.set_path(("features", "network_proxy"), True)))
        self.assertEqual(config, {"features": {"network_proxy": True}})
        self.assertFalse(apply_config_edit(config, ConfigEdit.set_path(("features", "network_proxy"), True)))

    def test_apply_config_edit_clear_path_keeps_parent_table(self) -> None:
        config = {"features": {"network_proxy": True}}

        self.assertTrue(apply_config_edit(config, ConfigEdit.clear_path(("features", "network_proxy"))))
        self.assertEqual(config, {"features": {}})
        self.assertFalse(apply_config_edit(config, ConfigEdit.clear_path(("features", "network_proxy"))))

    def test_apply_config_edits_applies_in_order(self) -> None:
        config = {}

        mutated = apply_config_edits(
            config,
            [
                ConfigEdit.set_path(("features", "network_proxy"), True),
                ConfigEdit.clear_path(("features", "network_proxy")),
                ConfigEdit.set_path(("features", "shell_tool"), False),
            ],
        )

        self.assertTrue(mutated)
        self.assertEqual(config, {"features": {"shell_tool": False}})

    def test_model_service_tier_and_personality_edits_match_upstream_root_keys(self) -> None:
        config = {
            "model": "old-model",
            "model_reasoning_effort": "low",
            "service_tier": "flex",
            "personality": "friendly",
        }

        self.assertTrue(apply_config_edits(config, model_selection_edits("gpt-5.4", "high")))
        self.assertTrue(apply_config_edit(config, service_tier_edit("priority")))
        self.assertTrue(apply_config_edit(config, personality_edit("pragmatic")))
        self.assertEqual(
            config,
            {
                "model": "gpt-5.4",
                "model_reasoning_effort": "high",
                "service_tier": "fast",
                "personality": "pragmatic",
            },
        )

    def test_optional_model_service_tier_and_personality_clear_existing_values(self) -> None:
        config = {
            "model": "old-model",
            "model_reasoning_effort": "low",
            "service_tier": "flex",
            "personality": "friendly",
        }

        mutated = apply_config_edits(
            config,
            [
                *model_selection_edits(None, None),
                service_tier_edit(None),
                personality_edit(None),
            ],
        )

        self.assertTrue(mutated)
        self.assertEqual(config, {})

    def test_service_tier_preserves_default_and_unknown_values(self) -> None:
        self.assertEqual(service_tier_edit("default").value, "default")
        self.assertEqual(service_tier_edit("priority").value, "fast")
        self.assertEqual(service_tier_edit("fast").value, "fast")
        self.assertEqual(service_tier_edit("flex").value, "flex")
        self.assertEqual(service_tier_edit("experimental-tier-id").value, "experimental-tier-id")

    def test_notice_edit_helpers_match_upstream_notice_paths(self) -> None:
        config = {"notice": {"existing": "value"}}

        mutated = apply_config_edits(
            config,
            [
                notice_hide_full_access_warning_edit(True),
                notice_hide_world_writable_warning_edit(True),
                notice_hide_rate_limit_model_nudge_edit(True),
                notice_hide_model_migration_prompt_edit("hide_gpt5_1_migration_prompt", True),
                record_model_migration_seen_edit("gpt-5.2", "gpt-5.4"),
                notice_hide_external_config_migration_prompt_home_edit(True),
                notice_external_config_migration_prompt_home_last_prompted_at_edit(1_760_000_000),
                notice_hide_external_config_migration_prompt_project_edit("/tmp/project", True),
                notice_external_config_migration_prompt_project_last_prompted_at_edit(
                    "/tmp/project",
                    1_760_000_001,
                ),
            ],
        )

        self.assertTrue(mutated)
        self.assertEqual(
            config,
            {
                "notice": {
                    "existing": "value",
                    "hide_full_access_warning": True,
                    "hide_world_writable_warning": True,
                    "hide_rate_limit_model_nudge": True,
                    "hide_gpt5_1_migration_prompt": True,
                    "model_migrations": {"gpt-5.2": "gpt-5.4"},
                    "external_config_migration_prompts": {
                        "home": True,
                        "home_last_prompted_at": 1_760_000_000,
                        "projects": {"/tmp/project": True},
                        "project_last_prompted_at": {"/tmp/project": 1_760_000_001},
                    },
                }
            },
        )

    def test_tool_suggest_disabled_tool_normalizes_type_and_id(self) -> None:
        self.assertEqual(
            ToolSuggestDisabledTool.connector(" connector_calendar ").normalized(),
            ToolSuggestDisabledTool(ToolSuggestDiscoverableType.CONNECTOR, "connector_calendar"),
        )
        self.assertEqual(
            ToolSuggestDisabledTool.from_mapping({"type": "plugin", "id": "slack@openai-curated"}),
            ToolSuggestDisabledTool.plugin("slack@openai-curated"),
        )
        self.assertIsNone(ToolSuggestDisabledTool.plugin("   ").normalized())
        self.assertIsNone(ToolSuggestDisabledTool.from_mapping({"type": "unknown", "id": "x"}))
        self.assertIsNone(ToolSuggestDisabledTool.from_mapping({"type": "plugin"}))

    def test_add_tool_suggest_disabled_tool_creates_config_entry(self) -> None:
        config = {}

        mutated = apply_config_edit(config, add_tool_suggest_disabled_tool_edit(ToolSuggestDisabledTool.connector("calendar")))

        self.assertTrue(mutated)
        self.assertEqual(
            config,
            {"tool_suggest": {"disabled_tools": [{"type": "connector", "id": "calendar"}]}},
        )

    def test_add_tool_suggest_disabled_tool_dedupes_existing_inline_or_table_entries(self) -> None:
        config = {
            "tool_suggest": {
                "discoverables": [{"type": "plugin", "id": "sample@openai-curated"}],
                "disabled_tools": [
                    {"type": "connector", "id": " connector_calendar "},
                    {"type": "connector", "id": "connector_calendar"},
                    {"type": "connector", "id": "   "},
                    {"type": "unknown", "id": "ignored"},
                    {"type": "plugin", "id": "slack@openai-curated"},
                ],
            }
        }

        mutated = apply_config_edit(config, add_tool_suggest_disabled_tool_edit({"type": "connector", "id": "calendar"}))

        self.assertTrue(mutated)
        self.assertEqual(
            config["tool_suggest"]["disabled_tools"],
            [
                {"type": "connector", "id": "connector_calendar"},
                {"type": "plugin", "id": "slack@openai-curated"},
                {"type": "connector", "id": "calendar"},
            ],
        )
        self.assertEqual(config["tool_suggest"]["discoverables"], [{"type": "plugin", "id": "sample@openai-curated"}])

    def test_add_tool_suggest_disabled_tool_is_noop_for_existing_normalized_entry(self) -> None:
        config = {"tool_suggest": {"disabled_tools": [{"type": "plugin", "id": "slack@openai-curated"}]}}

        mutated = apply_config_edit(
            config,
            add_tool_suggest_disabled_tool_edit(ToolSuggestDisabledTool.plugin(" slack@openai-curated ")),
        )

        self.assertFalse(mutated)
        self.assertEqual(config, {"tool_suggest": {"disabled_tools": [{"type": "plugin", "id": "slack@openai-curated"}]}})

    def test_project_trust_level_edit_sets_explicit_project_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "Work Tree"
            key = project_trust_key(project)
            config = {"projects": {key: {"old": "value"}}}

            mutated = apply_config_edit(config, project_trust_level_edit(project, "trusted"))

            self.assertTrue(mutated)
            self.assertEqual(config, {"projects": {key: {"old": "value", "trust_level": "trusted"}}})

    def test_project_trust_level_edit_replaces_scalar_project_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            key = project_trust_key(project)
            config = {"projects": {key: "legacy"}}

            mutated = apply_config_edit(config, project_trust_level_edit(project, "untrusted"))

            self.assertTrue(mutated)
            self.assertEqual(config, {"projects": {key: {"trust_level": "untrusted"}}})

    def test_project_trust_level_rejects_unknown_values(self) -> None:
        with self.assertRaises(ConfigEditError):
            project_trust_level_edit("project", "maybe")

    def test_set_skill_config_writes_disabled_path_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = Path(tmpdir) / "skills" / "demo" / "SKILL.md"
            skill_path.parent.mkdir(parents=True)
            skill_path.write_text("name: demo\n", encoding="utf-8")
            config = {}

            mutated = apply_config_edit(config, set_skill_config_edit(skill_path, False))

            self.assertTrue(mutated)
            self.assertEqual(
                config,
                {"skills": {"config": [{"path": normalize_skill_config_path(skill_path), "enabled": False}]}},
            )

    def test_set_skill_config_enabled_removes_entry_and_empty_skills_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = Path(tmpdir) / "skills" / "demo" / "SKILL.md"
            normalized = normalize_skill_config_path(skill_path)
            config = {"skills": {"config": [{"path": normalized, "enabled": False}]}}

            mutated = apply_config_edit(config, set_skill_config_edit(skill_path, True))

            self.assertTrue(mutated)
            self.assertEqual(config, {})

    def test_set_skill_config_by_name_trims_and_preserves_other_rules(self) -> None:
        config = {
            "skills": {
                "config": [
                    {"name": "github:yeet", "enabled": False},
                    {"name": "other", "enabled": False},
                ]
            }
        }

        self.assertTrue(apply_config_edit(config, set_skill_config_by_name_edit(" github:yeet ", True)))
        self.assertEqual(config, {"skills": {"config": [{"name": "other", "enabled": False}]}})

        self.assertTrue(apply_config_edit(config, set_skill_config_by_name_edit(" github:yeet ", False)))
        self.assertEqual(
            config,
            {
                "skills": {
                    "config": [
                        {"name": "other", "enabled": False},
                        {"name": "github:yeet", "enabled": False},
                    ]
                }
            },
        )

    def test_set_skill_config_empty_name_is_noop(self) -> None:
        config = {}

        self.assertFalse(apply_config_edit(config, set_skill_config_by_name_edit("   ", False)))
        self.assertEqual(config, {})

    def test_skill_config_selector_ignores_entries_with_both_path_and_name(self) -> None:
        config = {"skills": {"config": [{"name": "demo", "path": "/tmp/demo/SKILL.md", "enabled": False}]}}

        mutated = apply_config_edit(config, set_skill_config_by_name_edit("demo", False))

        self.assertTrue(mutated)
        self.assertEqual(
            config,
            {
                "skills": {
                    "config": [
                        {"name": "demo", "path": "/tmp/demo/SKILL.md", "enabled": False},
                        {"name": "demo", "enabled": False},
                    ]
                }
            },
        )

    def test_tui_path_edit_helpers_match_upstream_paths(self) -> None:
        config = {}

        mutated = apply_config_edits(
            config,
            [
                syntax_theme_edit("solarized-dark"),
                tui_pet_edit("cat"),
                session_picker_view_edit(SessionPickerViewMode.DENSE),
                status_line_items_edit(["model", "tokens"]),
                status_line_use_colors_edit(False),
                terminal_title_items_edit([]),
            ],
        )

        self.assertTrue(mutated)
        self.assertEqual(
            config,
            {
                "tui": {
                    "theme": "solarized-dark",
                    "pet": "cat",
                    "session_picker_view": "dense",
                    "status_line": ["model", "tokens"],
                    "status_line_use_colors": False,
                    "terminal_title": [],
                }
            },
        )

    def test_status_line_empty_list_persists_as_explicit_empty_array(self) -> None:
        # Rust source: codex-rs/core/src/config/edit.rs::status_line_items_edit.
        # Rust contract: an empty array means "hide the status line", not "unset".
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)

            changed = ConfigEditsBuilder.new(home).with_edits([status_line_items_edit([])]).apply_blocking()

            self.assertTrue(changed)
            self.assertEqual(read_toml_mapping(home / "config.toml"), {"tui": {"status_line": []}})
            self.assertEqual((home / "config.toml").read_text(encoding="utf-8"), "[tui]\nstatus_line = []\n")

    def test_keymap_binding_helpers_use_root_tui_keymap_paths(self) -> None:
        config = {"profiles": {"team": {"tui": {"keymap": {"composer": {"submit": "shift-enter"}}}}}}

        self.assertTrue(apply_config_edit(config, keymap_binding_edit("composer", "submit", "ctrl-enter")))
        self.assertEqual(config["tui"]["keymap"]["composer"]["submit"], "ctrl-enter")
        self.assertEqual(config["profiles"]["team"]["tui"]["keymap"]["composer"]["submit"], "shift-enter")

        self.assertTrue(apply_config_edit(config, keymap_binding_clear_edit("composer", "submit")))
        self.assertNotIn("submit", config["tui"]["keymap"]["composer"])
        self.assertEqual(config["profiles"]["team"]["tui"]["keymap"]["composer"]["submit"], "shift-enter")

    def test_keymap_bindings_edit_serializes_single_key_as_string_and_many_as_array(self) -> None:
        single = keymap_bindings_edit("composer", "submit", ["ctrl-enter"])
        many = keymap_bindings_edit("composer", "submit", ["enter", "ctrl-enter"])

        self.assertEqual(single.value, "ctrl-enter")
        self.assertEqual(many.value, ["enter", "ctrl-enter"])

    def test_model_availability_nux_count_edits_clear_then_write_sorted_counts(self) -> None:
        config = {"tui": {"model_availability_nux": {"old": 99}}}

        mutated = apply_config_edits(config, model_availability_nux_count_edits({"gpt-foo": 4, "gpt-bar": 1}))

        self.assertTrue(mutated)
        self.assertEqual(config, {"tui": {"model_availability_nux": {"gpt-bar": 1, "gpt-foo": 4}}})

    def test_platform_and_realtime_edit_helpers_match_upstream_paths(self) -> None:
        config = {
            "features": {
                "experimental_windows_sandbox": True,
                "elevated_windows_sandbox": True,
                "enable_experimental_windows_sandbox": True,
                "other": True,
            },
            "audio": {"speaker": "old-speaker"},
        }

        mutated = apply_config_edits(
            config,
            [
                windows_sandbox_mode_edit("restricted-token"),
                realtime_microphone_edit("desk-mic"),
                realtime_speaker_edit(None),
                realtime_voice_edit("sage"),
                *clear_legacy_windows_sandbox_key_edits(),
            ],
        )

        self.assertTrue(mutated)
        self.assertEqual(
            config,
            {
                "features": {"other": True},
                "audio": {"microphone": "desk-mic"},
                "windows": {"sandbox": "restricted-token"},
                "realtime": {"voice": "sage"},
            },
        )

    def test_dumps_toml_mapping_writes_scalars_before_tables(self) -> None:
        self.assertEqual(
            dumps_toml_mapping(
                {
                    "model": "gpt-5",
                    "features": {"network_proxy": True, "shell_tool": False},
                    "profiles": {"work": {"model": "gpt-5.1"}},
                }
            ),
            (
                'model = "gpt-5"\n'
                "\n"
                "[features]\n"
                "network_proxy = true\n"
                "shell_tool = false\n"
                "\n"
                "[profiles.work]\n"
                'model = "gpt-5.1"\n'
            ),
        )

    def test_dumps_toml_mapping_quotes_dotted_or_space_keys(self) -> None:
        self.assertEqual(
            dumps_toml_mapping({"projects": {"C:/Users/me/work tree": {"trust_level": "trusted"}}}),
            '[projects."C:/Users/me/work tree"]\ntrust_level = "trusted"\n',
        )

    def test_apply_blocking_writes_config_file_for_feature_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)

            changed = apply_blocking(home, [set_feature_enabled_edit("network_proxy", True)])

            self.assertTrue(changed)
            self.assertEqual(read_toml_mapping(home / "config.toml"), {"features": {"network_proxy": True}})
            self.assertEqual((home / "config.toml").read_text(encoding="utf-8"), "[features]\nnetwork_proxy = true\n")

    def test_apply_blocking_does_not_write_for_noop_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)

            changed = apply_blocking(home, [set_feature_enabled_edit("network_proxy", False)])

            self.assertFalse(changed)
            self.assertFalse((home / "config.toml").exists())

    def test_builder_applies_feature_edits_to_explicit_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "custom.toml"
            path.write_text("[features]\nnetwork_proxy = true\n", encoding="utf-8")

            changed = ConfigEditsBuilder.for_config_path(path).set_feature_enabled("network_proxy", False).apply_blocking()

            self.assertTrue(changed)
            self.assertEqual(read_toml_mapping(path), {"features": {}})
            self.assertEqual(path.read_text(encoding="utf-8"), "[features]\n")

    def test_builder_applies_config_edit_helper_methods(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)

            changed = (
                ConfigEditsBuilder.new(home)
                .set_model("gpt-5.4", "high")
                .set_service_tier("priority")
                .set_personality("pragmatic")
                .set_hide_full_access_warning(True)
                .record_model_migration_seen("gpt-5.2", "gpt-5.4")
                .set_session_picker_view("comfortable")
                .set_model_availability_nux_count({"gpt-foo": 4})
                .set_project_trust_level(home / "project", "trusted")
                .set_windows_sandbox_mode("restricted-token")
                .set_realtime_voice(None)
                .apply_blocking()
            )
            project_key = project_trust_key(home / "project")

            self.assertTrue(changed)
            self.assertEqual(
                read_toml_mapping(home / "config.toml"),
                {
                    "tui": {
                        "session_picker_view": "comfortable",
                        "model_availability_nux": {"gpt-foo": 4},
                    },
                    "model": "gpt-5.4",
                    "model_reasoning_effort": "high",
                    "service_tier": "fast",
                    "personality": "pragmatic",
                    "notice": {
                        "hide_full_access_warning": True,
                        "model_migrations": {"gpt-5.2": "gpt-5.4"},
                    },
                    "projects": {project_key: {"trust_level": "trusted"}},
                    "windows": {"sandbox": "restricted-token"},
                },
            )

    def test_builder_can_persist_disabled_tool_suggestion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)

            changed = ConfigEditsBuilder.new(home).add_tool_suggest_disabled_tool(
                ToolSuggestDisabledTool.plugin("slack@openai-curated")
            ).apply_blocking()

            self.assertTrue(changed)
            self.assertEqual(
                read_toml_mapping(home / "config.toml"),
                {"tool_suggest": {"disabled_tools": [{"type": "plugin", "id": "slack@openai-curated"}]}},
            )
            self.assertEqual(
                (home / "config.toml").read_text(encoding="utf-8"),
                '[tool_suggest]\ndisabled_tools = [{ type = "plugin", id = "slack@openai-curated" }]\n',
            )

    def test_builder_can_persist_disabled_skill_config_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)

            changed = ConfigEditsBuilder.new(home).set_skill_config_by_name("github:yeet", False).apply_blocking()

            self.assertTrue(changed)
            self.assertEqual(
                read_toml_mapping(home / "config.toml"),
                {"skills": {"config": [{"name": "github:yeet", "enabled": False}]}},
            )
            self.assertEqual(
                (home / "config.toml").read_text(encoding="utf-8"),
                '[[skills.config]]\nname = "github:yeet"\nenabled = false\n',
            )

    def test_skill_config_selector_rejects_unknown_kind(self) -> None:
        with self.assertRaises(ConfigEditError):
            ConfigEdit.set_skill_config(SkillConfigSelector("unknown", "value"), False)

    def test_replace_mcp_servers_serializes_stdio_and_http_servers(self) -> None:
        servers = {
            "stdio": McpServerConfig(
                McpServerTransportConfig(
                    kind="stdio",
                    command="cmd",
                    args=("--flag",),
                    env={"B": "2", "A": "1"},
                    env_vars=("FOO",),
                ),
                supports_parallel_tool_calls=True,
                enabled_tools=("one", "two"),
            ),
            "http": McpServerConfig(
                McpServerTransportConfig(
                    kind="streamable_http",
                    url="https://example.com",
                    bearer_token_env_var="TOKEN",
                    http_headers={"Z-Header": "z"},
                ),
                enabled=False,
                startup_timeout_sec=5,
                disabled_tools=("forbidden",),
                oauth={"client_id": "eci-prd-pub-codex-123"},
                oauth_resource="https://resource.example.com",
            ),
        }
        config = {"mcp_servers": {"old": {"command": "old"}}}

        mutated = apply_config_edit(config, replace_mcp_servers_edit(servers))

        self.assertTrue(mutated)
        self.assertEqual(
            config,
            {
                "mcp_servers": {
                    "http": {
                        "url": "https://example.com",
                        "bearer_token_env_var": "TOKEN",
                        "http_headers": {"Z-Header": "z"},
                        "enabled": False,
                        "startup_timeout_sec": 5.0,
                        "disabled_tools": ["forbidden"],
                        "oauth": {"client_id": "eci-prd-pub-codex-123"},
                        "oauth_resource": "https://resource.example.com",
                    },
                    "stdio": {
                        "command": "cmd",
                        "args": ["--flag"],
                        "env": {"A": "1", "B": "2"},
                        "env_vars": ["FOO"],
                        "supports_parallel_tool_calls": True,
                        "enabled_tools": ["one", "two"],
                    },
                }
            },
        )

    def test_replace_mcp_servers_empty_mapping_clears_table(self) -> None:
        config = {"mcp_servers": {"old": {"command": "old"}}}

        self.assertTrue(apply_config_edit(config, replace_mcp_servers_edit({})))
        self.assertEqual(config, {})

    def test_replace_mcp_servers_rejects_unsupported_transport(self) -> None:
        config = {}

        with self.assertRaises(ConfigEditError):
            apply_config_edit(
                config,
                replace_mcp_servers_edit({"bad": McpServerConfig(McpServerTransportConfig(kind="websocket"))}),
            )

    def test_builder_can_persist_mcp_servers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            servers = {
                "runner": McpServerConfig(
                    McpServerTransportConfig(
                        kind="stdio",
                        command="uvx",
                        args=("mcp-runner",),
                    ),
                    required=True,
                    tool_timeout_sec=3,
                )
            }

            changed = ConfigEditsBuilder.new(home).replace_mcp_servers(servers).apply_blocking()

            self.assertTrue(changed)
            self.assertEqual(
                read_toml_mapping(home / "config.toml"),
                {
                    "mcp_servers": {
                        "runner": {
                            "command": "uvx",
                            "args": ["mcp-runner"],
                            "required": True,
                            "tool_timeout_sec": 3.0,
                        }
                    }
                },
            )
            self.assertEqual(
                (home / "config.toml").read_text(encoding="utf-8"),
                '[mcp_servers.runner]\ncommand = "uvx"\nargs = ["mcp-runner"]\nrequired = true\ntool_timeout_sec = 3.0\n',
            )

    def test_async_builder_apply_uses_blocking_writer(self) -> None:
        async def run() -> tuple[bool, dict]:
            with tempfile.TemporaryDirectory() as tmpdir:
                home = Path(tmpdir)
                changed = await ConfigEditsBuilder.new(home).set_feature_enabled("shell_tool", False).apply()
                return changed, read_toml_mapping(home / "config.toml")

        self.assertEqual(
            asyncio.run(run()),
            (True, {"features": {"shell_tool": False}}),
        )


    def test_config_edit_helpers_reject_implicit_coercions(self) -> None:
        with self.assertRaises(ConfigEditError):
            status_line_items_edit(["model", 123])
        with self.assertRaises(ConfigEditError):
            status_line_use_colors_edit(1)
        with self.assertRaises(ConfigEditError):
            keymap_binding_edit("composer", "submit", 123)
        with self.assertRaises(ConfigEditError):
            model_availability_nux_count_edits({"gpt-foo": -1})
        with self.assertRaises(ConfigEditError):
            model_availability_nux_count_edits({123: 1})
        with self.assertRaises(ConfigEditError):
            notice_hide_full_access_warning_edit("true")
        with self.assertRaises(ConfigEditError):
            ConfigEdit.set_path(("features", 123), True)

    def test_config_edit_structures_reject_non_string_mapping_keys(self) -> None:
        with self.assertRaises(ConfigEditError):
            ConfigEdit.set_path(("root",), {1: "value"})
        with self.assertRaises(ConfigEditError):
            replace_mcp_servers_edit({1: McpServerConfig(McpServerTransportConfig(kind="stdio", command="cmd"))})
        self.assertIsNone(ToolSuggestDisabledTool.from_mapping({"type": "plugin", "id": 123}))
        with self.assertRaises(ConfigEditError):
            SkillConfigSelector.name(123)
        with self.assertRaises(ConfigEditError):
            ConfigEdit.set_skill_config(SkillConfigSelector.name("demo"), 1)

    def test_empty_segments_are_rejected(self) -> None:
        with self.assertRaises(ConfigEditError):
            ConfigEdit.set_path((), True)


if __name__ == "__main__":
    unittest.main()
