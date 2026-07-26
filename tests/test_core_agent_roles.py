from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pycodex.app_server_protocol.config import ConfigLayerSource
from pycodex.config.state import ConfigLayerEntry
from pycodex.core.config.agent_roles import (
    AgentRoleConfig,
    AgentRoleError,
    collect_agent_role_files,
    discover_agent_roles_in_dir,
    load_agent_roles_from_config,
    load_agent_roles_from_layers,
    merge_missing_role_fields,
    normalize_agent_role_description,
    normalize_agent_role_nickname_candidates,
    parse_agent_role_file_contents,
    validate_agent_role_file_developer_instructions,
    validate_required_agent_role_description,
)


class AgentRolesTests(unittest.TestCase):
    def test_normalize_agent_role_description_trims_and_rejects_blank(self) -> None:
        self.assertEqual(normalize_agent_role_description("agents.reviewer.description", " Review "), "Review")
        self.assertIsNone(normalize_agent_role_description("agents.reviewer.description", None))
        with self.assertRaisesRegex(AgentRoleError, "cannot be blank"):
            normalize_agent_role_description("agents.reviewer.description", "   ")

    def test_validate_required_agent_role_description(self) -> None:
        validate_required_agent_role_description("reviewer", "Review carefully")
        with self.assertRaisesRegex(AgentRoleError, "agent role `reviewer` must define a description"):
            validate_required_agent_role_description("reviewer", None)

    def test_validate_agent_role_file_developer_instructions(self) -> None:
        validate_agent_role_file_developer_instructions("reviewer.toml", "Stay focused", True)
        validate_agent_role_file_developer_instructions("reviewer.toml", None, False)
        with self.assertRaisesRegex(AgentRoleError, "must define `developer_instructions`"):
            validate_agent_role_file_developer_instructions("reviewer.toml", None, True)
        with self.assertRaisesRegex(AgentRoleError, "developer_instructions cannot be blank"):
            validate_agent_role_file_developer_instructions("reviewer.toml", "  ", True)

    def test_normalize_agent_role_nickname_candidates(self) -> None:
        self.assertEqual(
            normalize_agent_role_nickname_candidates("agents.reviewer.nickname_candidates", [" Ada ", "Grace-1"]),
            ("Ada", "Grace-1"),
        )
        with self.assertRaisesRegex(TypeError, "nickname_candidates must be an iterable of strings"):
            normalize_agent_role_nickname_candidates("agents.reviewer.nickname_candidates", "Ada")
        with self.assertRaisesRegex(TypeError, "nickname_candidates must contain only strings"):
            normalize_agent_role_nickname_candidates("agents.reviewer.nickname_candidates", ["Ada", 7])  # type: ignore[list-item]
        with self.assertRaisesRegex(AgentRoleError, "must contain at least one name"):
            normalize_agent_role_nickname_candidates("agents.reviewer.nickname_candidates", [])
        with self.assertRaisesRegex(AgentRoleError, "cannot contain blank names"):
            normalize_agent_role_nickname_candidates("agents.reviewer.nickname_candidates", ["Ada", " "])
        with self.assertRaisesRegex(AgentRoleError, "cannot contain duplicates"):
            normalize_agent_role_nickname_candidates("agents.reviewer.nickname_candidates", ["Ada", " Ada "])
        with self.assertRaisesRegex(AgentRoleError, "ASCII letters"):
            normalize_agent_role_nickname_candidates("agents.reviewer.nickname_candidates", ["Ada!"])

    def test_parse_agent_role_file_contents_removes_metadata_fields(self) -> None:
        parsed = parse_agent_role_file_contents(
            """
name = " reviewer "
description = " Review carefully "
nickname_candidates = [" Ada ", "Grace"]
developer_instructions = "Stay focused"
model = "gpt-5"
""",
            "reviewer.toml",
        )

        self.assertEqual(parsed.role_name, "reviewer")
        self.assertEqual(parsed.description, "Review carefully")
        self.assertEqual(parsed.nickname_candidates, ("Ada", "Grace"))
        self.assertEqual(parsed.config, {"developer_instructions": "Stay focused", "model": "gpt-5"})

    def test_parse_agent_role_file_contents_uses_hint_and_allows_empty_config(self) -> None:
        parsed = parse_agent_role_file_contents("", "inline.toml", role_name_hint="inline")

        self.assertEqual(parsed.role_name, "inline")
        self.assertIsNone(parsed.description)
        self.assertEqual(parsed.config, {})

    def test_parse_agent_role_file_contents_requires_name_without_hint(self) -> None:
        with self.assertRaisesRegex(AgentRoleError, "must define a non-empty `name`"):
            parse_agent_role_file_contents('developer_instructions = "Focus"\n', "missing-name.toml")

    def test_parse_agent_role_file_contents_wraps_invalid_toml(self) -> None:
        with self.assertRaisesRegex(AgentRoleError, "failed to parse agent role file"):
            parse_agent_role_file_contents("model = [", "broken.toml")

    def test_parse_agent_role_file_contents_rejects_non_string_metadata(self) -> None:
        with self.assertRaisesRegex(AgentRoleError, "description must be a string"):
            parse_agent_role_file_contents(
                'name = "reviewer"\ndescription = 7\ndeveloper_instructions = "Focus"\n',
                "bad-description.toml",
            )

    def test_collect_agent_role_files_recurses_and_sorts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "nested").mkdir()
            (root / "b.toml").write_text('name = "b"\ndeveloper_instructions = "B"\n', encoding="utf-8")
            (root / "nested" / "a.toml").write_text('name = "a"\ndeveloper_instructions = "A"\n', encoding="utf-8")
            (root / "ignore.txt").write_text("ignored", encoding="utf-8")

            files = collect_agent_role_files(root)

        self.assertEqual([path.name for path in files], ["b.toml", "a.toml"])

    def test_discover_agent_roles_in_dir_skips_declared_and_warns_on_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            declared = root / "declared.toml"
            declared.write_text('name = "declared"\ndescription = "Declared"\ndeveloper_instructions = "D"\n', encoding="utf-8")
            valid = root / "valid.toml"
            valid.write_text(
                'name = "valid"\ndescription = "Valid role"\ndeveloper_instructions = "V"\n',
                encoding="utf-8",
            )
            malformed = root / "malformed.toml"
            malformed.write_text('name = "broken"\ndeveloper_instructions = "B"\n', encoding="utf-8")
            warnings: list[str] = []

            roles = discover_agent_roles_in_dir(root, declared_role_files=[declared], startup_warnings=warnings)

        self.assertEqual(set(roles), {"valid"})
        self.assertEqual(roles["valid"].description, "Valid role")
        self.assertEqual(len(warnings), 1)
        self.assertIn("Ignoring malformed agent role definition", warnings[0])

    def test_merge_missing_role_fields(self) -> None:
        merged = merge_missing_role_fields(
            AgentRoleConfig(config_file=Path("role.toml")),
            AgentRoleConfig(description="Fallback", nickname_candidates=("Ada",)),
        )

        self.assertEqual(merged.description, "Fallback")
        self.assertEqual(merged.config_file, Path("role.toml"))
        self.assertEqual(merged.nickname_candidates, ("Ada",))

    def test_load_agent_roles_from_layers_merges_missing_fields_from_lower_precedence(self) -> None:
        # Rust source: codex-rs/core/src/config/agent_roles.rs::load_agent_roles.
        lower = ConfigLayerEntry(
            ConfigLayerSource.session_flags(),
            {
                "agents": {
                    "roles": {
                        "reviewer": {
                            "description": "Review carefully",
                            "nickname_candidates": [" Ada "],
                        }
                    }
                }
            },
        )
        higher = ConfigLayerEntry(
            ConfigLayerSource.session_flags(),
            {"agents": {"roles": {"reviewer": {}}}},
        )

        warnings: list[str] = []
        roles = load_agent_roles_from_layers([lower, higher], warnings)

        self.assertEqual(warnings, [])
        self.assertEqual(roles["reviewer"].description, "Review carefully")
        self.assertEqual(roles["reviewer"].nickname_candidates, ("Ada",))

    def test_load_agent_roles_from_layers_resolves_declared_config_file_and_renamed_role(self) -> None:
        # Rust source: codex-rs/core/src/config/agent_roles.rs::read_declared_role.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            role_file = root / "reviewer.toml"
            role_file.write_text(
                'name = "specialist"\n'
                'description = "File description"\n'
                'nickname_candidates = [" FileNick "]\n'
                'developer_instructions = "Focus"\n',
                encoding="utf-8",
            )
            layer = ConfigLayerEntry(
                ConfigLayerSource.user(root / "config.toml"),
                {
                    "agents": {
                        "roles": {
                            "reviewer": {
                                "description": "Inline description",
                                "config_file": "reviewer.toml",
                            }
                        }
                    }
                },
            )

            roles = load_agent_roles_from_layers([layer], [])

        self.assertEqual(set(roles), {"specialist"})
        self.assertEqual(roles["specialist"].description, "File description")
        self.assertEqual(roles["specialist"].nickname_candidates, ("FileNick",))
        self.assertEqual(roles["specialist"].config_file.name, "reviewer.toml")

    def test_load_agent_roles_from_layers_warns_and_skips_same_layer_duplicates(self) -> None:
        # Rust source: codex-rs/core/src/config/agent_roles.rs::load_agent_roles duplicate handling.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            agents = root / "agents"
            agents.mkdir()
            (agents / "duplicate.toml").write_text(
                'name = "reviewer"\ndescription = "Discovered"\ndeveloper_instructions = "D"\n',
                encoding="utf-8",
            )
            layer = ConfigLayerEntry(
                ConfigLayerSource.user(root / "config.toml"),
                {"agents": {"roles": {"reviewer": {"description": "Declared"}}}},
            )
            warnings: list[str] = []

            roles = load_agent_roles_from_layers([layer], warnings)

        self.assertEqual(roles["reviewer"].description, "Declared")
        self.assertEqual(len(warnings), 1)
        self.assertIn("duplicate agent role name `reviewer` declared in the same config layer", warnings[0])

    def test_load_agent_roles_from_config_errors_without_layer_warning_recovery(self) -> None:
        # Rust source: codex-rs/core/src/config/agent_roles.rs::load_agent_roles_without_layers.
        with self.assertRaisesRegex(AgentRoleError, "agent role `reviewer` must define a description"):
            load_agent_roles_from_config({"agents": {"roles": {"reviewer": {}}}})

    def test_agent_role_config_rejects_non_rust_field_shapes(self) -> None:
        with self.assertRaisesRegex(TypeError, "description must be a string"):
            AgentRoleConfig(description=object())  # type: ignore[arg-type]

        with self.assertRaisesRegex(TypeError, "config_file must be a Path"):
            AgentRoleConfig(config_file="role.toml")  # type: ignore[arg-type]

        with self.assertRaisesRegex(TypeError, "nickname_candidates must contain only strings"):
            AgentRoleConfig(nickname_candidates=("Ada", 1))  # type: ignore[arg-type]

if __name__ == "__main__":
    unittest.main()
