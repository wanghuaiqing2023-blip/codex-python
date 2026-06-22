import unittest
from pathlib import Path

from pycodex.config import BundledSkillsConfig, SkillConfig, SkillsConfig


class ConfigSkillsConfigTests(unittest.TestCase):
    def test_bundled_skills_config_defaults_enabled_true(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/skills_config.rs
        # Behavior anchor: BundledSkillsConfig::default sets enabled=true.
        self.assertEqual(BundledSkillsConfig(), BundledSkillsConfig(enabled=True))
        self.assertEqual(BundledSkillsConfig.from_mapping({}), BundledSkillsConfig(enabled=True))

    def test_skills_config_defaults_to_no_bundled_no_include_and_empty_config(self) -> None:
        # Rust module: src/skills_config.rs
        # Behavior anchor: SkillsConfig derives Default; optional fields are
        # None and config defaults to an empty Vec.
        config = SkillsConfig.from_mapping(None)

        self.assertIsNone(config.bundled)
        self.assertIsNone(config.include_instructions)
        self.assertEqual(config.config, ())
        self.assertEqual(config.to_mapping(), {})

    def test_skill_config_accepts_path_or_name_with_required_enabled(self) -> None:
        # Rust module: src/skills_config.rs
        path_entry = SkillConfig.from_mapping({"path": "/skills/demo", "enabled": True})
        name_entry = SkillConfig.from_mapping({"name": "github:yeet", "enabled": False})

        self.assertEqual(path_entry.path, Path("/skills/demo"))
        self.assertIsNone(path_entry.name)
        self.assertTrue(path_entry.enabled)
        self.assertEqual(path_entry.to_mapping(), {"enabled": True, "path": str(Path("/skills/demo"))})
        self.assertEqual(name_entry.to_mapping(), {"enabled": False, "name": "github:yeet"})

    def test_skills_config_from_mapping_preserves_bundled_include_and_config_entries(self) -> None:
        # Rust module: src/skills_config.rs
        config = SkillsConfig.from_mapping(
            {
                "bundled": {"enabled": False},
                "include_instructions": True,
                "config": [
                    {"name": "github:yeet", "enabled": False},
                    {"path": "/skills/local", "enabled": True},
                ],
            }
        )

        self.assertEqual(config.bundled, BundledSkillsConfig(enabled=False))
        self.assertTrue(config.include_instructions)
        self.assertEqual(
            config.config,
            (
                SkillConfig(name="github:yeet", enabled=False),
                SkillConfig(path=Path("/skills/local"), enabled=True),
            ),
        )
        self.assertEqual(
            config.to_mapping(),
            {
                "bundled": {"enabled": False},
                "include_instructions": True,
                "config": [
                    {"enabled": False, "name": "github:yeet"},
                    {"enabled": True, "path": str(Path("/skills/local"))},
                ],
            },
        )

    def test_skills_config_rejects_unknown_fields_like_deny_unknown_fields(self) -> None:
        # Rust module: src/skills_config.rs
        # Behavior anchor: all three structs have schemars deny_unknown_fields.
        with self.assertRaisesRegex(ValueError, "unknown fields for SkillsConfig: extra"):
            SkillsConfig.from_mapping({"extra": True})
        with self.assertRaisesRegex(ValueError, "unknown fields for BundledSkillsConfig: extra"):
            BundledSkillsConfig.from_mapping({"extra": True})
        with self.assertRaisesRegex(ValueError, "unknown fields for SkillConfig: extra"):
            SkillConfig.from_mapping({"name": "demo", "extra": True})

    def test_skills_config_rejects_invalid_field_shapes(self) -> None:
        # Rust serde behavior: field types must match the TOML shape.
        with self.assertRaisesRegex(TypeError, "enabled must be a bool"):
            SkillConfig.from_mapping({"name": "demo", "enabled": "yes"})
        with self.assertRaisesRegex(TypeError, "enabled is required"):
            SkillConfig.from_mapping({"name": "demo"})
        with self.assertRaisesRegex(TypeError, "bundled must be a table or None"):
            SkillsConfig.from_mapping({"bundled": True})
        with self.assertRaisesRegex(TypeError, "include_instructions must be a bool or None"):
            SkillsConfig.from_mapping({"include_instructions": "yes"})
        with self.assertRaisesRegex(TypeError, "config must be an array"):
            SkillsConfig.from_mapping({"config": {"name": "demo"}})


if __name__ == "__main__":
    unittest.main()
