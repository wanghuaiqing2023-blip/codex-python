from __future__ import annotations

from pathlib import Path
import unittest

from pycodex.core import (
    DEFAULT_SKILL_METADATA_CHAR_BUDGET,
    SKILL_DESCRIPTION_TRUNCATED_WARNING,
    SKILL_DESCRIPTION_TRUNCATED_WARNING_WITH_PERCENT,
    SKILL_DESCRIPTIONS_REMOVED_WARNING_PREFIX,
    SkillLine,
    SkillLoadOutcome,
    SkillMetadata,
    SkillMetadataBudget,
    SkillMetadataBudgetKind,
    approx_skill_token_count,
    approx_token_count_from_bytes,
    build_alias_plan,
    build_available_skills,
    build_available_skills_from_metadata,
    default_skill_metadata_budget,
    render_skill_path_with_aliases,
)


def make_skill(
    name: str,
    scope: str = "repo",
    description: str = "desc",
    policy: object | None = None,
    path: Path | str | None = None,
) -> SkillMetadata:
    return SkillMetadata(
        name=name,
        description=description,
        path_to_skills_md=Path(path) if path is not None else Path("/tmp") / name / "SKILL.md",
        scope=scope,
        policy=policy,
    )


def expected_skill_line(skill: SkillMetadata, description: str) -> str:
    return SkillLine.from_skill(skill).render_with_description(description)


def normalized_path(path: Path | str) -> str:
    return str(Path(path)).replace("\\", "/")


def outcome_with_roots(skills: list[SkillMetadata], roots: list[Path]) -> SkillLoadOutcome:
    skill_root_by_path = {}
    for skill in skills:
        assert skill.path_to_skills_md is not None
        skill_path = Path(skill.path_to_skills_md)
        for root in roots:
            try:
                skill_path.relative_to(root)
            except ValueError:
                continue
            skill_root_by_path[skill_path] = root
            break
    return SkillLoadOutcome(skills=tuple(skills), skill_roots=tuple(roots), skill_root_by_path=skill_root_by_path)


class SkillRenderingTests(unittest.TestCase):
    def test_default_budget_uses_two_percent_or_character_fallback(self) -> None:
        self.assertEqual(default_skill_metadata_budget(200_000), SkillMetadataBudget.tokens(4_000))
        self.assertEqual(default_skill_metadata_budget(99), SkillMetadataBudget.tokens(1))
        self.assertEqual(default_skill_metadata_budget(None), SkillMetadataBudget.characters(DEFAULT_SKILL_METADATA_CHAR_BUDGET))
        self.assertEqual(default_skill_metadata_budget(-1), SkillMetadataBudget.characters(DEFAULT_SKILL_METADATA_CHAR_BUDGET))

    def test_budget_kind_is_coerced_and_token_count_uses_four_byte_chunks(self) -> None:
        budget = SkillMetadataBudget("characters", -5)

        self.assertEqual(budget.kind, SkillMetadataBudgetKind.CHARACTERS)
        self.assertEqual(budget.limit, 0)
        self.assertEqual(approx_token_count_from_bytes(5), 2)
        self.assertEqual(approx_skill_token_count("abcd"), 1)
        self.assertEqual(approx_skill_token_count("abcde"), 2)

    def test_skill_line_rendering_matches_upstream_shape(self) -> None:
        skill = make_skill("alpha-skill", description="does work")
        line = SkillLine.from_skill(skill)

        self.assertEqual(line.render_full(), "- alpha-skill: does work (file: /tmp/alpha-skill/SKILL.md)")
        self.assertEqual(line.render_minimum(), "- alpha-skill: (file: /tmp/alpha-skill/SKILL.md)")
        self.assertEqual(line.render_with_description_chars(4), "- alpha-skill: does (file: /tmp/alpha-skill/SKILL.md)")

    def test_budgeted_rendering_truncates_descriptions_equally_before_omitting_skills(self) -> None:
        alpha = make_skill("alpha-skill", description="abcdef")
        beta = make_skill("beta-skill", description="uvwxyz")
        minimum_cost = SkillLine.from_skill(alpha).minimum_cost(SkillMetadataBudget.characters(9999))
        minimum_cost += SkillLine.from_skill(beta).minimum_cost(SkillMetadataBudget.characters(9999))

        rendered = build_available_skills_from_metadata(
            [beta, alpha],
            SkillMetadataBudget.characters(minimum_cost + 6),
        )

        self.assertIsNotNone(rendered)
        assert rendered is not None
        self.assertEqual(rendered.report.included_count, 2)
        self.assertEqual(rendered.report.omitted_count, 0)
        self.assertEqual(rendered.report.truncated_description_chars, 8)
        self.assertIsNone(rendered.warning_message)
        self.assertEqual(
            rendered.skill_lines,
            (
                expected_skill_line(alpha, "ab"),
                expected_skill_line(beta, "uv"),
            ),
        )

    def test_budgeted_rendering_warns_when_average_description_truncation_exceeds_threshold(self) -> None:
        long_skill = make_skill("long-skill", description="a" * 250)
        empty_skill = make_skill("empty-skill", description="")
        minimum_cost = SkillLine.from_skill(long_skill).minimum_cost(SkillMetadataBudget.characters(9999))
        minimum_cost += SkillLine.from_skill(empty_skill).minimum_cost(SkillMetadataBudget.characters(9999))

        rendered = build_available_skills_from_metadata(
            [long_skill, empty_skill],
            SkillMetadataBudget.characters(minimum_cost + 49),
        )

        self.assertIsNotNone(rendered)
        assert rendered is not None
        self.assertEqual(rendered.report.total_count, 2)
        self.assertEqual(rendered.report.included_count, 2)
        self.assertEqual(rendered.report.omitted_count, 0)
        self.assertEqual(rendered.report.truncated_description_chars, 202)
        self.assertEqual(rendered.report.truncated_description_count, 1)
        self.assertEqual(rendered.warning_message, SKILL_DESCRIPTION_TRUNCATED_WARNING)

    def test_token_budget_truncation_warning_mentions_two_percent(self) -> None:
        long_skill = make_skill("long-skill", description="a" * 1000)
        minimum_cost = SkillLine.from_skill(long_skill).minimum_cost(SkillMetadataBudget.tokens(9999))

        rendered = build_available_skills_from_metadata(
            [long_skill],
            SkillMetadataBudget.tokens(minimum_cost + 1),
        )

        self.assertIsNotNone(rendered)
        assert rendered is not None
        self.assertEqual(rendered.warning_message, SKILL_DESCRIPTION_TRUNCATED_WARNING_WITH_PERCENT)

    def test_budgeted_rendering_redistributes_unused_description_budget(self) -> None:
        short = make_skill("short-skill", description="x")
        long = make_skill("long-skill", description="abcdefghi")
        minimum_cost = SkillLine.from_skill(short).minimum_cost(SkillMetadataBudget.characters(9999))
        minimum_cost += SkillLine.from_skill(long).minimum_cost(SkillMetadataBudget.characters(9999))

        rendered = build_available_skills_from_metadata(
            [short, long],
            SkillMetadataBudget.characters(minimum_cost + 11),
        )

        self.assertIsNotNone(rendered)
        assert rendered is not None
        self.assertEqual(rendered.report.included_count, 2)
        self.assertEqual(rendered.report.omitted_count, 0)
        self.assertEqual(
            rendered.skill_lines,
            (
                expected_skill_line(long, "abcdefgh"),
                expected_skill_line(short, "x"),
            ),
        )

    def test_budgeted_rendering_preserves_prompt_priority_when_minimum_lines_exceed_budget(self) -> None:
        system = make_skill("system-skill", scope="system")
        user = make_skill("user-skill", scope="user")
        repo = make_skill("repo-skill", scope="repo")
        admin = make_skill("admin-skill", scope="admin")
        system_cost = SkillLine.from_skill(system).minimum_cost(SkillMetadataBudget.characters(9999))
        admin_cost = SkillLine.from_skill(admin).minimum_cost(SkillMetadataBudget.characters(9999))

        rendered = build_available_skills_from_metadata(
            [system, user, repo, admin],
            SkillMetadataBudget.characters(system_cost + admin_cost),
        )

        self.assertIsNotNone(rendered)
        assert rendered is not None
        self.assertEqual(rendered.report.included_count, 2)
        self.assertEqual(rendered.report.omitted_count, 2)
        self.assertEqual(
            rendered.skill_lines,
            (
                expected_skill_line(system, ""),
                expected_skill_line(admin, ""),
            ),
        )
        self.assertTrue(rendered.warning_message)
        assert rendered.warning_message is not None
        self.assertTrue(rendered.warning_message.startswith(SKILL_DESCRIPTIONS_REMOVED_WARNING_PREFIX))

    def test_build_available_skills_uses_allowed_implicit_skills_only(self) -> None:
        enabled = make_skill("enabled")
        disabled = make_skill("disabled")
        no_implicit = make_skill("no-implicit", policy={"allowImplicitInvocation": False})
        outcome = SkillLoadOutcome(
            skills=(enabled, disabled, no_implicit),
            disabled_paths=frozenset({Path("/tmp") / "disabled" / "SKILL.md"}),
        )

        rendered = build_available_skills(outcome, SkillMetadataBudget.characters(9999))

        self.assertIsNotNone(rendered)
        assert rendered is not None
        self.assertEqual(rendered.skill_lines, (expected_skill_line(enabled, "desc"),))
        self.assertIsNone(build_available_skills_from_metadata([], SkillMetadataBudget.characters(9999)))

    def test_build_available_skills_omits_aliases_without_budget_pressure(self) -> None:
        root = Path("/tmp/skills")
        alpha = make_skill("alpha-skill", path=root / "alpha" / "SKILL.md")
        beta = make_skill("beta-skill", path=root / "beta" / "SKILL.md")
        outcome = outcome_with_roots([alpha, beta], [root])

        rendered = build_available_skills(outcome, SkillMetadataBudget.characters(9999))

        self.assertIsNotNone(rendered)
        assert rendered is not None
        self.assertEqual(rendered.skill_root_lines, ())
        self.assertEqual(rendered.report.included_count, 2)

    def test_build_available_skills_uses_aliases_when_they_allow_more_skills_to_fit(self) -> None:
        root = Path(
            "/Users/xl/.codex/plugins/cache/openai-curated/example/hash1234567890/skills-with-a-very-long-shared-prefix"
        )
        skills = [
            make_skill(f"shared-root-skill-{index}", path=root / f"skill-{index}" / "SKILL.md")
            for index in range(12)
        ]
        outcome = outcome_with_roots(skills, [root])
        plan = build_alias_plan(outcome, skills, SkillMetadataBudget.characters(9999))
        self.assertIsNotNone(plan)
        assert plan is not None
        alias_minimum = plan.table_cost + sum(
            SkillLine.with_path(skill, render_skill_path_with_aliases(skill, plan)).minimum_cost(
                SkillMetadataBudget.characters(9999)
            )
            for skill in skills
        )

        rendered = build_available_skills(outcome, SkillMetadataBudget.characters(alias_minimum))

        self.assertIsNotNone(rendered)
        assert rendered is not None
        self.assertEqual(rendered.report.included_count, len(skills))
        self.assertEqual(rendered.report.omitted_count, 0)
        self.assertEqual(rendered.skill_root_lines, (f"- `r0` = `{normalized_path(root)}`",))
        rendered_text = "\n".join(rendered.skill_lines)
        self.assertIn("r0/skill-0/SKILL.md", rendered_text)
        self.assertIn("r0/skill-11/SKILL.md", rendered_text)

    def test_alias_plan_uses_marketplace_root_for_single_skill_plugin_versions(self) -> None:
        github_root = Path("/Users/xl/.codex/plugins/cache/openai-curated/github/hash123/skills")
        marketplace_root = Path("/Users/xl/.codex/plugins/cache/openai-curated")
        github = make_skill("github:gh-fix-ci", path=github_root / "gh-fix-ci" / "SKILL.md")
        outcome = outcome_with_roots([github], [github_root])

        plan = build_alias_plan(outcome, [github], SkillMetadataBudget.characters(9999))

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.aliases.skill_root_lines, (f"- `r0` = `{normalized_path(marketplace_root)}`",))
        self.assertEqual(
            render_skill_path_with_aliases(github, plan),
            "r0/github/hash123/skills/gh-fix-ci/SKILL.md",
        )

    def test_alias_plan_uses_skill_root_for_multiple_skills_in_one_plugin_version(self) -> None:
        github_root = Path("/Users/xl/.codex/plugins/cache/openai-curated/github/hash123/skills")
        fix_ci = make_skill("github:gh-fix-ci", path=github_root / "gh-fix-ci" / "SKILL.md")
        yeet = make_skill("github:yeet", path=github_root / "yeet" / "SKILL.md")
        outcome = outcome_with_roots([fix_ci, yeet], [github_root])

        plan = build_alias_plan(outcome, [fix_ci, yeet], SkillMetadataBudget.characters(9999))

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.aliases.skill_root_lines, (f"- `r0` = `{normalized_path(github_root)}`",))
        self.assertEqual(render_skill_path_with_aliases(fix_ci, plan), "r0/gh-fix-ci/SKILL.md")
        self.assertEqual(render_skill_path_with_aliases(yeet, plan), "r0/yeet/SKILL.md")

    def test_alias_plan_uses_one_marketplace_root_for_multiple_plugin_versions(self) -> None:
        skills_root = Path("/Users/xl/.codex/plugins/cache/openai-curated/github/hash123/skills")
        extra_root = Path("/Users/xl/.codex/plugins/cache/openai-curated/github/hash456/extra-skills")
        marketplace_root = Path("/Users/xl/.codex/plugins/cache/openai-curated")
        fix_ci = make_skill("github:gh-fix-ci", path=skills_root / "gh-fix-ci" / "SKILL.md")
        yeet = make_skill("github:yeet", path=extra_root / "yeet" / "SKILL.md")
        outcome = outcome_with_roots([fix_ci, yeet], [skills_root, extra_root])

        plan = build_alias_plan(outcome, [fix_ci, yeet], SkillMetadataBudget.characters(9999))

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.aliases.skill_root_lines, (f"- `r0` = `{normalized_path(marketplace_root)}`",))
        self.assertEqual(
            render_skill_path_with_aliases(fix_ci, plan),
            "r0/github/hash123/skills/gh-fix-ci/SKILL.md",
        )
        self.assertEqual(
            render_skill_path_with_aliases(yeet, plan),
            "r0/github/hash456/extra-skills/yeet/SKILL.md",
        )


if __name__ == "__main__":
    unittest.main()
