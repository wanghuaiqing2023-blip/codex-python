from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from pycodex.core import (
    SkillConfigRule,
    SkillConfigRuleSelector,
    SkillConfigRules,
    SkillMetadata,
    resolve_disabled_skill_paths,
    skill_config_rule_selector,
    skill_config_rules_from_stack,
)
from pycodex.core.skill_invocation_utils import canonicalize_if_exists


def skill(name: str, path: Path | str) -> SkillMetadata:
    return SkillMetadata(name=name, path_to_skills_md=Path(path))


def layer(name: str, config: dict[str, object]) -> dict[str, object]:
    return {"name": name, "config": config}


def skills_config(*entries: dict[str, object]) -> dict[str, object]:
    return {"skills": {"config": list(entries)}}


class SkillConfigRulesTests(unittest.TestCase):
    def test_selector_accepts_path_or_non_empty_name_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SKILL.md"
            path.write_text("skill", encoding="utf-8")

            self.assertEqual(
                skill_config_rule_selector({"path": str(path)}),
                SkillConfigRuleSelector.path(path),
            )
            self.assertEqual(
                skill_config_rule_selector({"name": " github:yeet "}),
                SkillConfigRuleSelector.name("github:yeet"),
            )
            self.assertIsNone(skill_config_rule_selector({"name": "   "}))
            self.assertIsNone(skill_config_rule_selector({"name": "x", "path": str(path)}))
            self.assertIsNone(skill_config_rule_selector({"enabled": False}))

    def test_rules_from_stack_ignores_non_user_or_session_layers(self) -> None:
        rules = skill_config_rules_from_stack(
            [
                layer("Default", skills_config({"name": "default", "enabled": False})),
                layer("User", skills_config({"name": "user", "enabled": False})),
                layer("SessionFlags", skills_config({"name": "session", "enabled": True})),
            ]
        )

        self.assertEqual(
            rules,
            SkillConfigRules(
                (
                    SkillConfigRule(SkillConfigRuleSelector.name("user"), False),
                    SkillConfigRule(SkillConfigRuleSelector.name("session"), True),
                )
            ),
        )

    def test_rules_from_stack_later_same_selector_overrides_earlier(self) -> None:
        rules = skill_config_rules_from_stack(
            [
                layer("User", skills_config({"name": "github:yeet", "enabled": False})),
                layer("SessionFlags", skills_config({"name": "github:yeet", "enabled": True})),
            ]
        )

        self.assertEqual(
            rules,
            SkillConfigRules((SkillConfigRule(SkillConfigRuleSelector.name("github:yeet"), True),)),
        )

    def test_resolve_disabled_paths_allows_session_flags_to_reenable_user_disabled_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo" / "SKILL.md"
            path.parent.mkdir()
            path.write_text("skill", encoding="utf-8")
            rules = skill_config_rules_from_stack(
                [
                    layer("User", skills_config({"path": str(path), "enabled": False})),
                    layer("SessionFlags", skills_config({"path": str(path), "enabled": True})),
                ]
            )

            self.assertEqual(resolve_disabled_skill_paths([skill("demo-skill", path)], rules), set())

    def test_resolve_disabled_paths_allows_session_flags_to_disable_user_enabled_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo" / "SKILL.md"
            path.parent.mkdir()
            path.write_text("skill", encoding="utf-8")
            rules = skill_config_rules_from_stack(
                [
                    layer("User", skills_config({"path": str(path), "enabled": True})),
                    layer("SessionFlags", skills_config({"path": str(path), "enabled": False})),
                ]
            )

            self.assertEqual(
                resolve_disabled_skill_paths([skill("demo-skill", path)], rules),
                {canonicalize_if_exists(path)},
            )

    def test_resolve_disabled_paths_disables_matching_name_selectors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo" / "SKILL.md"
            other = Path(tmp) / "other" / "SKILL.md"
            path.parent.mkdir()
            other.parent.mkdir()
            path.write_text("skill", encoding="utf-8")
            other.write_text("other", encoding="utf-8")
            rules = skill_config_rules_from_stack(
                [layer("User", skills_config({"name": "github:yeet", "enabled": False}))]
            )

            self.assertEqual(
                resolve_disabled_skill_paths(
                    [skill("github:yeet", path), skill("other", other)],
                    rules,
                ),
                {canonicalize_if_exists(path)},
            )

    def test_name_selector_can_override_path_selector_for_same_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo" / "SKILL.md"
            path.parent.mkdir()
            path.write_text("skill", encoding="utf-8")
            rules = skill_config_rules_from_stack(
                [
                    layer("User", skills_config({"path": str(path), "enabled": False})),
                    layer("SessionFlags", skills_config({"name": "github:yeet", "enabled": True})),
                ]
            )

            self.assertEqual(resolve_disabled_skill_paths([skill("github:yeet", path)], rules), set())

    def test_resolve_disabled_paths_accepts_direct_rule_iterable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo" / "SKILL.md"
            path.parent.mkdir()
            path.write_text("skill", encoding="utf-8")

            disabled = resolve_disabled_skill_paths(
                [skill("demo", path)],
                [SkillConfigRule(SkillConfigRuleSelector.path(path), False)],
            )

            self.assertEqual(disabled, {canonicalize_if_exists(path)})


if __name__ == "__main__":
    unittest.main()
