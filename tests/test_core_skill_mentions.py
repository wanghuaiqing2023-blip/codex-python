from __future__ import annotations

from pathlib import Path
import unittest

from pycodex.core_skills.model import SkillMetadata
from pycodex.core_skills.mentions import (
    build_skill_name_counts,
    collect_explicit_skill_mentions,
    text_mentions_skill,
)
from pycodex.protocol import UserInput


def make_skill(name: str, path: str) -> SkillMetadata:
    return SkillMetadata(
        name=name,
        description=f"{name} skill",
        path_to_skills_md=path,
        scope="user",
    )


def linked_skill_mention(name: str, path: str) -> str:
    return f"[${name}]({path})"


def collect_mentions(
    inputs: list[UserInput | dict[str, object]],
    skills: list[SkillMetadata],
    disabled_paths: set[str] | None = None,
    connector_slug_counts: dict[str, int] | None = None,
) -> list[SkillMetadata]:
    return collect_explicit_skill_mentions(
        inputs,
        skills,
        disabled_paths or set(),
        connector_slug_counts or {},
    )


class SkillMentionsTests(unittest.TestCase):
    def test_text_mentions_skill_requires_exact_boundary(self) -> None:
        self.assertTrue(text_mentions_skill("use $notion-research-doc please", "notion-research-doc"))
        self.assertTrue(text_mentions_skill("($notion-research-doc)", "notion-research-doc"))
        self.assertTrue(text_mentions_skill("$notion-research-doc.", "notion-research-doc"))
        self.assertFalse(text_mentions_skill("$notion-research-docs", "notion-research-doc"))
        self.assertFalse(text_mentions_skill("$notion-research-doc_extra", "notion-research-doc"))

    def test_text_mentions_skill_handles_end_boundary_and_near_misses(self) -> None:
        self.assertTrue(text_mentions_skill("$alpha-skill", "alpha-skill"))
        self.assertFalse(text_mentions_skill("$alpha-skillx", "alpha-skill"))
        self.assertTrue(text_mentions_skill("$alpha-skillx and later $alpha-skill ", "alpha-skill"))
        self.assertFalse(text_mentions_skill("$" * 256 + " not-a-mention", "alpha-skill"))

    def test_build_skill_name_counts_skips_disabled_paths(self) -> None:
        alpha = make_skill("demo", "/tmp/alpha")
        beta = make_skill("Demo", "/tmp/beta")

        exact, lower = build_skill_name_counts([alpha, beta], {"/tmp/beta"})

        self.assertEqual(exact, {"demo": 1})
        self.assertEqual(lower, {"demo": 1})

    def test_collect_explicit_skill_mentions_text_respects_skill_order(self) -> None:
        alpha = make_skill("alpha-skill", "/tmp/alpha")
        beta = make_skill("beta-skill", "/tmp/beta")
        skills = [beta, alpha]

        selected = collect_mentions([UserInput.text_input("first $alpha-skill then $beta-skill")], skills)

        self.assertEqual(selected, [beta, alpha])

    def test_collect_explicit_skill_mentions_prioritizes_structured_inputs(self) -> None:
        alpha = make_skill("alpha-skill", "/tmp/alpha")
        beta = make_skill("beta-skill", "/tmp/beta")
        skills = [alpha, beta]

        selected = collect_mentions(
            [
                UserInput.text_input("please run $alpha-skill"),
                UserInput.skill("beta-skill", Path("/tmp/beta")),
            ],
            skills,
        )

        self.assertEqual(selected, [beta, alpha])

    def test_collect_explicit_skill_mentions_skips_invalid_structured_and_blocks_plain_fallback(self) -> None:
        alpha = make_skill("alpha-skill", "/tmp/alpha")

        selected = collect_mentions(
            [
                UserInput.text_input("please run $alpha-skill"),
                UserInput.skill("alpha-skill", Path("/tmp/missing")),
            ],
            [alpha],
        )

        self.assertEqual(selected, [])

    def test_collect_explicit_skill_mentions_skips_disabled_structured_and_blocks_plain_fallback(self) -> None:
        alpha = make_skill("alpha-skill", "/tmp/alpha")

        selected = collect_mentions(
            [
                UserInput.text_input("please run $alpha-skill"),
                UserInput.skill("alpha-skill", Path("/tmp/alpha")),
            ],
            [alpha],
            {"/tmp/alpha"},
        )

        self.assertEqual(selected, [])

    def test_collect_explicit_skill_mentions_dedupes_by_path(self) -> None:
        alpha = make_skill("alpha-skill", "/tmp/alpha")
        mention = linked_skill_mention("alpha-skill", "/tmp/alpha")

        selected = collect_mentions([UserInput.text_input(f"use {mention} and {mention}")], [alpha])

        self.assertEqual(selected, [alpha])

    def test_collect_explicit_skill_mentions_skips_ambiguous_name(self) -> None:
        alpha = make_skill("demo-skill", "/tmp/alpha")
        beta = make_skill("demo-skill", "/tmp/beta")

        selected = collect_mentions([UserInput.text_input("use $demo-skill and again $demo-skill")], [alpha, beta])

        self.assertEqual(selected, [])

    def test_collect_explicit_skill_mentions_prefers_linked_path_over_name(self) -> None:
        alpha = make_skill("demo-skill", "/tmp/alpha")
        beta = make_skill("demo-skill", "/tmp/beta")

        selected = collect_mentions(
            [UserInput.text_input(f"use $demo-skill and {linked_skill_mention('demo-skill', '/tmp/beta')}")],
            [alpha, beta],
        )

        self.assertEqual(selected, [beta])

    def test_collect_explicit_skill_mentions_skips_plain_name_when_connector_matches(self) -> None:
        alpha = make_skill("alpha-skill", "/tmp/alpha")

        selected = collect_mentions(
            [UserInput.text_input("use $alpha-skill")],
            [alpha],
            connector_slug_counts={"alpha-skill": 1},
        )

        self.assertEqual(selected, [])

    def test_collect_explicit_skill_mentions_allows_explicit_path_with_connector_conflict(self) -> None:
        alpha = make_skill("alpha-skill", "/tmp/alpha")

        selected = collect_mentions(
            [UserInput.text_input(f"use {linked_skill_mention('alpha-skill', '/tmp/alpha')}")],
            [alpha],
            connector_slug_counts={"alpha-skill": 1},
        )

        self.assertEqual(selected, [alpha])

    def test_collect_explicit_skill_mentions_skips_when_linked_path_disabled(self) -> None:
        alpha = make_skill("demo-skill", "/tmp/alpha")
        beta = make_skill("demo-skill", "/tmp/beta")

        selected = collect_mentions(
            [UserInput.text_input(f"use {linked_skill_mention('demo-skill', '/tmp/alpha')}")],
            [alpha, beta],
            {"/tmp/alpha"},
        )

        self.assertEqual(selected, [])

    def test_collect_explicit_skill_mentions_prefers_resource_path(self) -> None:
        alpha = make_skill("demo-skill", "/tmp/alpha")
        beta = make_skill("demo-skill", "/tmp/beta")

        selected = collect_mentions(
            [UserInput.text_input(f"use {linked_skill_mention('demo-skill', '/tmp/beta')}")],
            [alpha, beta],
        )

        self.assertEqual(selected, [beta])

    def test_collect_explicit_skill_mentions_skips_missing_path_with_no_fallback(self) -> None:
        alpha = make_skill("demo-skill", "/tmp/alpha")
        beta = make_skill("demo-skill", "/tmp/beta")

        selected = collect_mentions(
            [UserInput.text_input(f"use {linked_skill_mention('demo-skill', '/tmp/missing')}")],
            [alpha, beta],
        )

        self.assertEqual(selected, [])

    def test_collect_explicit_skill_mentions_accepts_mapping_inputs(self) -> None:
        alpha = make_skill("alpha-skill", "/tmp/alpha")

        selected = collect_mentions(
            [{"type": "skill", "name": "alpha-skill", "path": "/tmp/alpha"}],
            [alpha],
        )

        self.assertEqual(selected, [alpha])


if __name__ == "__main__":
    unittest.main()
