import tempfile
import unittest
from pathlib import Path

from pycodex.config import (
    ConfigLayerEntry,
    ConfigLayerSource,
    ConfigLayerStack,
    ConfigLayerStackOrdering,
    ConfigLoadOptions,
    LoaderOverrides,
)


class ConfigStateTests(unittest.TestCase):
    def test_origins_use_canonical_key_aliases(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/state.rs
        # Rust test: origins_use_canonical_key_aliases
        layer = ConfigLayerEntry.new(
            ConfigLayerSource.session_flags(),
            {"memories": {"no_memories_if_mcp_or_web_search": True}},
        )
        metadata = layer.metadata()
        stack = ConfigLayerStack.new([layer])

        origins = stack.origins()

        self.assertEqual(origins.get("memories.disable_on_external_context"), metadata)
        self.assertNotIn("memories.no_memories_if_mcp_or_web_search", origins)

    def test_active_user_layer_is_highest_precedence_user_layer(self) -> None:
        # Rust test: active_user_layer_is_highest_precedence_user_layer
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base_file = root / "config.toml"
            profile_file = root / "work.config.toml"
            base_layer = ConfigLayerEntry.new(
                ConfigLayerSource.user(base_file),
                {"model": "base", "approval_policy": "on-failure"},
            )
            profile_layer = ConfigLayerEntry.new(
                ConfigLayerSource.user(profile_file),
                {"model": "profile"},
            )
            stack = ConfigLayerStack.new([base_layer, profile_layer])

            self.assertEqual(stack.get_user_config_file(), profile_file)
            self.assertEqual(
                stack.effective_user_config(),
                {"model": "profile", "approval_policy": "on-failure"},
            )

    def test_with_user_config_updates_matching_user_layer_without_replacing_active_profile(self) -> None:
        # Rust test: with_user_config_updates_matching_user_layer_without_replacing_active_profile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base_file = root / "config.toml"
            profile_file = root / "work.config.toml"
            base_layer = ConfigLayerEntry.new(ConfigLayerSource.user(base_file), {"model": "base"})
            profile_layer = ConfigLayerEntry.new(
                ConfigLayerSource.user(profile_file, "work"),
                {"approval_policy": "on-failure"},
            )
            stack = ConfigLayerStack.new([base_layer, profile_layer])

            updated = stack.with_user_config(base_file, {"model": "updated-base"})

            self.assertEqual(updated.get_user_config_file(), profile_file)
            self.assertEqual(
                updated.effective_user_config(),
                {"model": "updated-base", "approval_policy": "on-failure"},
            )
            self.assertIsNone(updated.layers[0].name.profile)
            self.assertEqual(updated.layers[1].name.profile, "work")

            updated_profile = stack.with_user_config(profile_file, {"approval_policy": "never"})

            self.assertEqual(updated_profile.get_user_config_file(), profile_file)
            self.assertEqual(updated_profile.layers[1].name.profile, "work")
            self.assertEqual(
                updated_profile.effective_user_config(),
                {"model": "base", "approval_policy": "never"},
            )

    def test_with_user_config_profile_inserts_profile_metadata_like_rust(self) -> None:
        # Rust source: ConfigLayerStack::with_user_config_profile.
        system = ConfigLayerEntry.new(ConfigLayerSource.system("/tmp/system.toml"), {"model": "system"})
        session = ConfigLayerEntry.new(ConfigLayerSource.session_flags(), {"approval_policy": "never"})
        stack = ConfigLayerStack.new([system, session])

        updated = stack.with_user_config_profile("/tmp/work.config.toml", "work", {"model": "work"})

        self.assertEqual([layer.name.type for layer in updated.layers], ["system", "user", "session_flags"])
        self.assertEqual(updated.get_user_config_file(), Path("/tmp/work.config.toml"))
        self.assertEqual(updated.get_active_user_layer().name.profile, "work")
        self.assertEqual(updated.effective_user_config(), {"model": "work"})

    def test_get_user_layers_supports_precedence_order_and_disabled_filter(self) -> None:
        # Rust source: ConfigLayerStack::get_user_layers.
        base = ConfigLayerEntry.new(ConfigLayerSource.user("/tmp/config.toml"), {"model": "base"})
        profile = ConfigLayerEntry.new(ConfigLayerSource.user("/tmp/work.config.toml", "work"), {"model": "work"})
        disabled = ConfigLayerEntry.new_disabled(
            ConfigLayerSource.user("/tmp/disabled.config.toml", "disabled"),
            {"model": "disabled"},
            "disabled by test",
        )
        stack = ConfigLayerStack.new([base, profile, disabled])

        self.assertEqual(
            [layer.name.profile for layer in stack.get_user_layers(ConfigLayerStackOrdering.LOWEST_PRECEDENCE_FIRST, False)],
            [None, "work"],
        )
        self.assertEqual(
            [layer.name.profile for layer in stack.get_user_layers(ConfigLayerStackOrdering.HIGHEST_PRECEDENCE_FIRST, True)],
            ["disabled", "work", None],
        )

    def test_stack_accessors_preserve_requirements_flags_and_startup_warnings(self) -> None:
        # Rust source: ConfigLayerStack accessors for requirements, flags, and warnings.
        requirements = object()
        requirements_toml = object()
        stack = ConfigLayerStack.new([], requirements, requirements_toml)

        updated = stack.with_user_and_project_exec_policy_rules_ignored(True).with_startup_warnings(
            ["first", "second"]
        )

        self.assertIs(updated.requirements, requirements)
        self.assertIs(updated.requirements_toml, requirements_toml)
        self.assertTrue(updated.ignore_user_and_project_exec_policy_rules())
        self.assertEqual(updated.startup_warnings(), ("first", "second"))

    def test_effective_config_skips_disabled_layers_and_high_to_low_reverses_order(self) -> None:
        system = ConfigLayerEntry.new(ConfigLayerSource.system("/tmp/system.toml"), {"model": "system"})
        user = ConfigLayerEntry.new(ConfigLayerSource.user("/tmp/user.toml"), {"model": "user"})
        disabled_project = ConfigLayerEntry.new_disabled(
            ConfigLayerSource.project("/tmp/project/.codex"),
            {"model": "project"},
            "disabled by test",
        )
        session = ConfigLayerEntry.new(ConfigLayerSource.session_flags(), {"approval_policy": "never"})
        stack = ConfigLayerStack.new([system, user, disabled_project, session])

        self.assertEqual(stack.effective_config(), {"model": "user", "approval_policy": "never"})
        self.assertEqual(stack.layers_high_to_low(), [session, user, system])
        self.assertEqual(
            stack.get_layers(ConfigLayerStackOrdering.LOWEST_PRECEDENCE_FIRST, include_disabled=True),
            [system, user, disabled_project, session],
        )

    def test_layer_entry_metadata_raw_toml_as_layer_and_config_folders(self) -> None:
        layer = ConfigLayerEntry.new_with_raw_toml(
            ConfigLayerSource.user("/tmp/codex/config.toml"),
            {"model": "gpt-5"},
            'model = "gpt-5"',
        )
        overridden = layer.with_hooks_config_folder_override("/tmp/root/.codex")

        self.assertEqual(layer.raw_toml_text(), 'model = "gpt-5"')
        self.assertFalse(layer.is_disabled())
        self.assertEqual(layer.config_folder(), Path("/tmp/codex"))
        self.assertEqual(overridden.hooks_config_folder(), Path("/tmp/root/.codex"))
        self.assertEqual(layer.as_layer().name, layer.name)
        self.assertEqual(layer.as_layer().config, {"model": "gpt-5"})
        self.assertTrue(layer.metadata().version.startswith("sha256:"))

    def test_verify_layer_ordering_rejects_precedence_and_project_order_errors(self) -> None:
        session = ConfigLayerEntry.new(ConfigLayerSource.session_flags(), {})
        system = ConfigLayerEntry.new(ConfigLayerSource.system("/tmp/system.toml"), {})
        with self.assertRaisesRegex(ValueError, "correct precedence order"):
            ConfigLayerStack.new([session, system])

        root_project = ConfigLayerEntry.new(ConfigLayerSource.project("/tmp/project/.codex"), {})
        same_project = ConfigLayerEntry.new(ConfigLayerSource.project("/tmp/project/.codex"), {})
        with self.assertRaisesRegex(ValueError, "root to cwd"):
            ConfigLayerStack.new([root_project, same_project])

    def test_with_user_layer_from_preserves_non_user_layers(self) -> None:
        system = ConfigLayerEntry.new(ConfigLayerSource.system("/tmp/system.toml"), {"model": "system"})
        session = ConfigLayerEntry.new(ConfigLayerSource.session_flags(), {"approval_policy": "never"})
        base = ConfigLayerStack.new([system, session])
        user = ConfigLayerEntry.new(ConfigLayerSource.user("/tmp/user.toml"), {"model": "user"})
        other = ConfigLayerStack.new([user])

        updated = base.with_user_layer_from(other)

        self.assertEqual(updated.effective_config(), {"model": "user", "approval_policy": "never"})
        self.assertEqual([layer.name.type for layer in updated.layers], ["system", "user", "session_flags"])

    def test_loader_overrides_and_config_load_options(self) -> None:
        overrides = LoaderOverrides.without_managed_config_for_tests()

        self.assertTrue(str(overrides.managed_config_path).endswith("managed_config.toml"))
        self.assertEqual(overrides.user_config_file(Path("/tmp/codex-home")), Path("/tmp/codex-home/config.toml"))
        self.assertFalse(ConfigLoadOptions.from_loader_overrides(overrides).strict_config)


if __name__ == "__main__":
    unittest.main()
