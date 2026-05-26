from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pycodex.core import (
    AWAITER_TOML,
    DEFAULT_ROLE_NAME,
    EXPLORER_TOML,
    AgentRoleConfig,
    AgentRoleError,
    build_spawn_agent_tool_description,
    built_in_agent_role_config_file_contents,
    built_in_agent_role_configs,
    collect_agent_role_files,
    discover_agent_roles_in_dir,
    format_agent_nickname,
    locked_settings_note_for_role,
    merge_missing_role_fields,
    normalize_agent_role_description,
    normalize_agent_role_nickname_candidates,
    parse_agent_role_file_contents,
    resolve_role_config,
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

    def test_built_in_roles_and_config_contents(self) -> None:
        roles = built_in_agent_role_configs()

        self.assertEqual(list(roles), ["default", "explorer", "worker"])
        self.assertEqual(roles[DEFAULT_ROLE_NAME].description, "Default agent.")
        self.assertEqual(built_in_agent_role_config_file_contents("explorer.toml"), EXPLORER_TOML)
        self.assertEqual(built_in_agent_role_config_file_contents("awaiter.toml"), AWAITER_TOML)
        self.assertIsNone(built_in_agent_role_config_file_contents("missing.toml"))

    def test_resolve_role_config_prefers_user_defined_role(self) -> None:
        user_role = AgentRoleConfig(description="User override")

        self.assertEqual(resolve_role_config({"explorer": user_role}, "explorer"), user_role)
        self.assertEqual(resolve_role_config({}, "default"), built_in_agent_role_configs()["default"])
        self.assertIsNone(resolve_role_config({}, "missing"))

    def test_build_spawn_agent_tool_description_deduplicates_and_orders_roles(self) -> None:
        spec = build_spawn_agent_tool_description(
            {
                "explorer": AgentRoleConfig(description="user override"),
                "researcher": AgentRoleConfig(),
            }
        )

        self.assertIn("Optional type name for the new agent. If omitted, `default` is used.", spec)
        self.assertIn("researcher: no description", spec)
        self.assertIn("explorer: {\nuser override\n}", spec)
        self.assertIn("default: {\nDefault agent.\n}", spec)
        self.assertNotIn("Explorers are fast and authoritative.", spec)
        self.assertLess(spec.index("explorer: {\nuser override\n}"), spec.index("default: {\nDefault agent.\n}"))

    def test_locked_settings_note_for_role_marks_model_reasoning_and_service_tier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            role_path = Path(tmpdir) / "researcher.toml"
            role_path.write_text(
                'developer_instructions = "Research carefully"\n'
                'model = "gpt-5"\n'
                'model_reasoning_effort = "high"\n'
                'service_tier = "priority"\n',
                encoding="utf-8",
            )

            note = locked_settings_note_for_role(AgentRoleConfig(description="Research", config_file=role_path))

        self.assertIn("model is set to `gpt-5`", note)
        self.assertIn("reasoning effort is set to `high`", note)
        self.assertIn("service tier is set to `priority`", note)

    def test_locked_settings_note_for_role_marks_reasoning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            role_path = Path(tmpdir) / "reviewer.toml"
            role_path.write_text(
                'developer_instructions = "Review carefully"\nmodel_reasoning_effort = "medium"\n',
                encoding="utf-8",
            )

            note = locked_settings_note_for_role(AgentRoleConfig(description="Review", config_file=role_path))

        self.assertIn("reasoning effort is set to `medium` and cannot be changed", note)

    def test_format_agent_nickname_adds_ordinal_suffixes(self) -> None:
        self.assertEqual(format_agent_nickname("Ada", 0), "Ada")
        self.assertEqual(format_agent_nickname("Ada", 1), "Ada the 2nd")
        self.assertEqual(format_agent_nickname("Ada", 2), "Ada the 3rd")
        self.assertEqual(format_agent_nickname("Ada", 10), "Ada the 11th")
        self.assertEqual(format_agent_nickname("Ada", 20), "Ada the 21st")


if __name__ == "__main__":
    unittest.main()
