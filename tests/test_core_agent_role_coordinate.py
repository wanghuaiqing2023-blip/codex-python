from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pycodex.core.agent.role import (
    AGENT_TYPE_UNAVAILABLE_ERROR,
    DEFAULT_ROLE_NAME,
    AgentRoleConfig,
    apply_role_to_config,
    build_spawn_agent_role_description,
    built_in_agent_role_configs,
    built_in_config_file_contents,
    load_role_layer_toml,
    resolve_role_config,
)
from pycodex.network_proxy import ConfigLayerEntry, ConfigLayerSource


@dataclass
class RoleConfigForTest:
    codex_home: Path
    cwd: Path
    agent_roles: dict[str, AgentRoleConfig] = field(default_factory=dict)
    config_layer_stack: list[ConfigLayerEntry] = field(default_factory=list)
    model: str | None = None
    model_provider_id: str = "openai"
    model_reasoning_effort: str | None = None
    service_tier: str | None = None
    codex_linux_sandbox_exe: Path | None = None
    main_execve_wrapper_exe: Path | None = None
    developer_instructions: str | None = None
    skills: dict[str, Any] | None = None


class AgentRoleCoordinateTests(unittest.TestCase):
    def test_builtin_roles_match_rust_order_and_config_lookup(self) -> None:
        # Rust source: codex-rs/core/src/agent/role.rs::built_in.
        roles = built_in_agent_role_configs()

        self.assertEqual(list(roles), ["default", "explorer", "worker"])
        self.assertEqual(roles[DEFAULT_ROLE_NAME].description, "Default agent.")
        self.assertEqual(built_in_config_file_contents("explorer.toml"), "")
        self.assertIsNotNone(built_in_config_file_contents("awaiter.toml"))
        self.assertIsNone(built_in_config_file_contents("missing.toml"))

    def test_resolve_role_config_prefers_user_defined_then_builtins(self) -> None:
        # Rust source: codex-rs/core/src/agent/role.rs::resolve_role_config.
        user_role = AgentRoleConfig(description="User override")

        self.assertEqual(resolve_role_config({"explorer": user_role}, "explorer"), user_role)
        self.assertEqual(resolve_role_config({}, "default"), built_in_agent_role_configs()["default"])
        self.assertIsNone(resolve_role_config({}, "missing"))

    def test_spawn_agent_role_description_deduplicates_user_defined_builtins(self) -> None:
        # Rust source: role_tests.rs::spawn_tool_spec_build_deduplicates_user_defined_built_in_roles.
        spec = build_spawn_agent_role_description(
            {
                "explorer": AgentRoleConfig(description="user override"),
                "researcher": AgentRoleConfig(),
            }
        )

        self.assertIn("researcher: no description", spec)
        self.assertIn("explorer: {\nuser override\n}", spec)
        self.assertIn("default: {\nDefault agent.\n}", spec)
        self.assertNotIn("Explorers are fast and authoritative.", spec)

    def test_spawn_agent_role_description_marks_locked_settings(self) -> None:
        # Rust source: role_tests.rs locked model/reasoning/service-tier cases.
        with tempfile.TemporaryDirectory() as tmpdir:
            role_path = Path(tmpdir) / "tiered.toml"
            role_path.write_text(
                'developer_instructions = "Stay fast"\n'
                'model = "gpt-5"\n'
                'model_reasoning_effort = "high"\n'
                'service_tier = "priority"\n',
                encoding="utf-8",
            )

            spec = build_spawn_agent_role_description(
                {"tiered": AgentRoleConfig(description="Stay fast.", config_file=role_path)}
            )

        self.assertIn(
            "Stay fast.\n- This role's model is set to `gpt-5` and its reasoning effort is set to `high`.",
            spec,
        )
        self.assertIn("service tier is set to `priority`", spec)

    def test_apply_role_defaults_to_default_and_leaves_config_unchanged(self) -> None:
        # Rust source: role_tests.rs::apply_role_defaults_to_default_and_leaves_config_unchanged.
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RoleConfigForTest(Path(tmpdir), Path(tmpdir), model="base-model", service_tier="priority")
            before = (config.model, config.service_tier, list(config.config_layer_stack))

            apply_role_to_config(config, None)

        self.assertEqual((config.model, config.service_tier, list(config.config_layer_stack)), before)

    def test_apply_role_returns_error_for_unknown_role(self) -> None:
        # Rust source: role_tests.rs::apply_role_returns_error_for_unknown_role.
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RoleConfigForTest(Path(tmpdir), Path(tmpdir))

            with self.assertRaisesRegex(ValueError, "unknown agent_type 'missing-role'"):
                apply_role_to_config(config, "missing-role")

    def test_apply_role_returns_unavailable_for_missing_or_invalid_user_role_file(self) -> None:
        # Rust source: role_tests.rs missing and invalid user role file cases.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing = RoleConfigForTest(root, root)
            missing.agent_roles["custom"] = AgentRoleConfig(config_file=root / "missing.toml")

            with self.assertRaisesRegex(ValueError, AGENT_TYPE_UNAVAILABLE_ERROR):
                apply_role_to_config(missing, "custom")

            invalid_path = root / "invalid.toml"
            invalid_path.write_text("model = [", encoding="utf-8")
            invalid = RoleConfigForTest(root, root)
            invalid.agent_roles["custom"] = AgentRoleConfig(config_file=invalid_path)

            with self.assertRaisesRegex(ValueError, AGENT_TYPE_UNAVAILABLE_ERROR):
                apply_role_to_config(invalid, "custom")

    def test_apply_role_ignores_metadata_and_adds_session_flags_layer(self) -> None:
        # Rust source: role_tests.rs::apply_role_ignores_agent_metadata_fields_in_user_role_file.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            role_path = root / "metadata-role.toml"
            role_path.write_text(
                'name = "archivist"\n'
                'description = "Role metadata"\n'
                'nickname_candidates = ["Hypatia"]\n'
                'developer_instructions = "Stay focused"\n'
                'model = "role-model"\n',
                encoding="utf-8",
            )
            config = RoleConfigForTest(root, root, model="base-model")
            config.agent_roles["custom"] = AgentRoleConfig(config_file=role_path)

            apply_role_to_config(config, "custom")

        self.assertEqual(config.model, "role-model")
        self.assertEqual(config.developer_instructions, "Stay focused")
        self.assertFalse(hasattr(config, "name"))
        self.assertFalse(hasattr(config, "description"))
        self.assertEqual(len(config.config_layer_stack), 1)
        self.assertEqual(config.config_layer_stack[0].name, ConfigLayerSource.session_flags())
        self.assertNotIn("name", config.config_layer_stack[0].config)
        self.assertNotIn("description", config.config_layer_stack[0].config)
        self.assertNotIn("nickname_candidates", config.config_layer_stack[0].config)

    def test_apply_role_preserves_unspecified_keys_and_provider_service_tier(self) -> None:
        # Rust source: role_tests.rs::apply_role_preserves_unspecified_keys and service-tier sticky case.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            role_path = root / "effort-only.toml"
            role_path.write_text(
                'developer_instructions = "Stay focused"\nmodel_reasoning_effort = "high"\n',
                encoding="utf-8",
            )
            config = RoleConfigForTest(
                root,
                root,
                model="base-model",
                model_provider_id="custom-provider",
                service_tier="priority",
                codex_linux_sandbox_exe=Path("/tmp/codex-linux-sandbox"),
                main_execve_wrapper_exe=Path("/tmp/codex-execve-wrapper"),
            )
            config.agent_roles["custom"] = AgentRoleConfig(config_file=role_path)

            apply_role_to_config(config, "custom")

        self.assertEqual(config.model, "base-model")
        self.assertEqual(config.model_provider_id, "custom-provider")
        self.assertEqual(config.service_tier, "priority")
        self.assertEqual(config.model_reasoning_effort, "high")
        self.assertEqual(config.codex_linux_sandbox_exe, Path("/tmp/codex-linux-sandbox"))
        self.assertEqual(config.main_execve_wrapper_exe, Path("/tmp/codex-execve-wrapper"))

    def test_apply_role_overrides_explicit_provider_service_tier_and_precedence(self) -> None:
        # Rust source: role_tests.rs explicit service tier and precedence-over-session-flags cases.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            role_path = root / "model-role.toml"
            role_path.write_text(
                'developer_instructions = "Stay focused"\n'
                'model = "role-model"\n'
                'model_provider = "role-provider"\n'
                'service_tier = "priority"\n',
                encoding="utf-8",
            )
            config = RoleConfigForTest(root, root, model="cli-model", model_provider_id="parent-provider")
            config.config_layer_stack.append(ConfigLayerEntry(ConfigLayerSource.session_flags(), {"model": "cli-model"}))
            config.agent_roles["custom"] = AgentRoleConfig(config_file=role_path)

            apply_role_to_config(config, "custom")

        self.assertEqual(config.model, "role-model")
        self.assertEqual(config.model_provider_id, "role-provider")
        self.assertEqual(config.service_tier, "priority")
        self.assertEqual(len(config.config_layer_stack), 2)
        self.assertEqual(config.config_layer_stack[-1].config["model"], "role-model")

    def test_load_role_layer_toml_resolves_relative_paths_against_role_file(self) -> None:
        # Rust source: load_role_layer_toml resolves relative paths using the role file parent.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            role_dir = root / "roles"
            role_dir.mkdir()
            role_path = role_dir / "path-role.toml"
            role_path.write_text(
                'developer_instructions = "Stay focused"\n'
                'config_file = "metadata-removed.toml"\n'
                'log_path = "logs/out.txt"\n',
                encoding="utf-8",
            )
            config = RoleConfigForTest(root, root)

            layer = load_role_layer_toml(config, role_path, False, "custom")

        self.assertEqual(layer["config_file"], str(role_dir / "metadata-removed.toml"))
        self.assertEqual(layer["log_path"], str(role_dir / "logs" / "out.txt"))


if __name__ == "__main__":
    unittest.main()
