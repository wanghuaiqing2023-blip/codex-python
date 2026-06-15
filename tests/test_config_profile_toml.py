import unittest
from pathlib import Path

from pycodex.config import ConfigProfile, ProfileTui


class ConfigProfileTomlTests(unittest.TestCase):
    def test_config_profile_round_trips_source_confirmed_fields(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/profile_toml.rs
        # Contract: ConfigProfile field names and optional profile-scoped TUI settings.
        profile = ConfigProfile.from_mapping(
            {
                "model": "gpt-5",
                "service_tier": "priority",
                "model_provider": "openai",
                "approval_policy": "on-request",
                "approvals_reviewer": "human",
                "sandbox_mode": "workspace-write",
                "model_reasoning_effort": "medium",
                "plan_mode_reasoning_effort": "high",
                "model_reasoning_summary": "auto",
                "model_verbosity": "medium",
                "model_catalog_json": "/tmp/catalog.json",
                "personality": "default",
                "chatgpt_base_url": "https://chatgpt.example",
                "model_instructions_file": "/tmp/instructions.md",
                "js_repl_node_path": "/tmp/node",
                "js_repl_node_module_dirs": ["/tmp/node_modules"],
                "experimental_compact_prompt_file": "/tmp/compact.md",
                "include_permissions_instructions": True,
                "include_apps_instructions": False,
                "include_collaboration_mode_instructions": True,
                "include_environment_context": False,
                "experimental_use_unified_exec_tool": True,
                "tools": {"web_search": True},
                "web_search": "enabled",
                "analytics": {"enabled": False},
                "tui": {"session_picker_view": "comfortable"},
                "windows": {"sandbox_mode": "enabled"},
                "features": {"foo": True},
                "oss_provider": "ollama",
            }
        )

        self.assertEqual(profile.model, "gpt-5")
        self.assertEqual(profile.model_catalog_json, Path("/tmp/catalog.json"))
        self.assertEqual(profile.js_repl_node_module_dirs, (Path("/tmp/node_modules"),))
        self.assertEqual(profile.tui, ProfileTui(session_picker_view="comfortable"))
        self.assertEqual(
            profile.to_mapping()["tui"],
            {"session_picker_view": "comfortable"},
        )

    def test_profile_tui_rejects_unknown_and_bad_session_picker_view(self) -> None:
        # Rust source: ProfileTui uses serde deny_unknown_fields and
        # SessionPickerViewMode has only comfortable/dense wire values.
        with self.assertRaisesRegex(KeyError, "unknown"):
            ProfileTui.from_mapping({"unknown": True})
        with self.assertRaisesRegex(ValueError, "session_picker_view"):
            ProfileTui.from_mapping({"session_picker_view": "wide"})

    def test_config_profile_rejects_unknown_and_bad_field_shapes(self) -> None:
        # Rust source: ConfigProfile is schemars deny_unknown_fields.
        with self.assertRaisesRegex(KeyError, "unknown"):
            ConfigProfile.from_mapping({"unknown": True})
        with self.assertRaisesRegex(TypeError, "model"):
            ConfigProfile.from_mapping({"model": 123})
        with self.assertRaisesRegex(TypeError, "include_environment_context"):
            ConfigProfile.from_mapping({"include_environment_context": "yes"})
        with self.assertRaisesRegex(TypeError, "tools"):
            ConfigProfile.from_mapping({"tools": []})


if __name__ == "__main__":
    unittest.main()
