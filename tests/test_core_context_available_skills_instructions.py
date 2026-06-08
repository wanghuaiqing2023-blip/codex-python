import unittest
from types import SimpleNamespace

from pycodex.core.context import AvailableSkillsInstructions, is_standard_contextual_user_text
from pycodex.protocol import (
    ContentItem,
    ResponseInputItem,
    ResponseItem,
    SKILLS_INSTRUCTIONS_CLOSE_TAG,
    SKILLS_INSTRUCTIONS_OPEN_TAG,
)


SKILLS_INTRO_WITH_ABSOLUTE_PATHS = "A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills that can be used. Each entry includes a name, description, and file path so you can open the source for full instructions when using a specific skill."
SKILLS_INTRO_WITH_ALIASES = "A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills that can be used. Each entry includes a name, description, and a short path that can be expanded into an absolute path using the skill roots table."
SKILLS_HOW_TO_USE_WITH_ALIASES = """- Discovery: The list above is the skills available in this session (name + description + short path). Skill bodies live on disk at the listed paths after expanding the matching alias from `### Skill roots`.
- Trigger rules: If the user names a skill (with `$SkillName` or plain text) OR the task clearly matches a skill's description shown above, you must use that skill for that turn. Multiple mentions mean use them all. Do not carry skills across turns unless re-mentioned.
- Missing/blocked: If a named skill isn't in the list or the path can't be read, say so briefly and continue with the best fallback.
- How to use a skill (progressive disclosure):
  1) After deciding to use a skill, expand the listed short `path` with the matching alias from `### Skill roots`, then open its `SKILL.md`. Read only enough to follow the workflow.
  2) When `SKILL.md` references relative paths (e.g., `scripts/foo.py`), resolve them relative to the directory containing that expanded `SKILL.md` first, and only consider other paths if needed.
  3) If `SKILL.md` points to extra folders such as `references/`, load only the specific files needed for the request; don't bulk-load everything.
  4) If `scripts/` exist, prefer running or patching them instead of retyping large code blocks.
  5) If `assets/` or templates exist, reuse them instead of recreating from scratch.
- Coordination and sequencing:
  - If multiple skills apply, choose the minimal set that covers the request and state the order you'll use them.
  - Announce which skill(s) you're using and why (one short line). If you skip an obvious skill, say why.
- Context hygiene:
  - Keep context small: summarize long sections instead of pasting them; only load extra files when needed.
  - Avoid deep reference-chasing: prefer opening only files directly linked from `SKILL.md` unless you're blocked.
  - When variants exist (frameworks, providers, domains), pick only the relevant reference file(s) and note that choice.
- Safety and fallback: If a skill can't be applied cleanly (missing files, unclear instructions), state the issue, pick the next-best approach, and continue."""


class AvailableSkillsInstructionsTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/available_skills_instructions.rs
    # - codex/codex-rs/core-skills/src/render.rs::render_available_skills_body

    def test_available_skills_instructions_matches_marked_text_but_not_user_context_registry(
        self,
    ) -> None:
        rendered = f"{SKILLS_INSTRUCTIONS_OPEN_TAG}\n## Skills\n{SKILLS_INSTRUCTIONS_CLOSE_TAG}"

        self.assertTrue(AvailableSkillsInstructions.matches_text(rendered))
        self.assertTrue(AvailableSkillsInstructions.matches_text(f"  {rendered.upper()}\n"))
        self.assertFalse(is_standard_contextual_user_text(rendered))
        self.assertFalse(AvailableSkillsInstructions.matches_text("## Skills"))

    def test_available_skills_instructions_alias_branch_matches_rust_fragment_contract(
        self,
    ) -> None:
        available_skills = SimpleNamespace(
            skill_root_lines=("local => C:/Users/me/.codex/skills",),
            skill_lines=(
                "- shell-helper: Use safe shell slices (path: local/shell-helper/SKILL.md)",
            ),
        )
        fragment = AvailableSkillsInstructions.from_available_skills(available_skills)
        expected_body = "\n" + "\n".join(
            (
                "## Skills",
                SKILLS_INTRO_WITH_ALIASES,
                "### Skill roots",
                "local => C:/Users/me/.codex/skills",
                "### Available skills",
                "- shell-helper: Use safe shell slices (path: local/shell-helper/SKILL.md)",
                "### How to use skills",
                SKILLS_HOW_TO_USE_WITH_ALIASES,
            )
        ) + "\n"
        expected_render = f"{SKILLS_INSTRUCTIONS_OPEN_TAG}{expected_body}{SKILLS_INSTRUCTIONS_CLOSE_TAG}"

        self.assertEqual(fragment.role(), "developer")
        self.assertEqual(fragment.markers(), (SKILLS_INSTRUCTIONS_OPEN_TAG, SKILLS_INSTRUCTIONS_CLOSE_TAG))
        self.assertEqual(fragment.type_markers(), (SKILLS_INSTRUCTIONS_OPEN_TAG, SKILLS_INSTRUCTIONS_CLOSE_TAG))
        self.assertEqual(fragment.body(), expected_body)
        self.assertEqual(fragment.render(), expected_render)
        self.assertEqual(
            fragment.into_response_item(),
            ResponseItem.message("developer", (ContentItem.input_text(expected_render),)),
        )
        self.assertEqual(
            fragment.into_response_input_item(),
            ResponseInputItem.message("developer", (ContentItem.input_text(expected_render),)),
        )

    def test_available_skills_instructions_absolute_path_branch_omits_skill_roots(self) -> None:
        fragment = AvailableSkillsInstructions(
            (),
            ("- imagegen: Generate raster images (path: C:/skills/imagegen/SKILL.md)",),
        )
        body = fragment.body()

        self.assertIn(SKILLS_INTRO_WITH_ABSOLUTE_PATHS, body)
        self.assertNotIn("### Skill roots", body)
        self.assertIn("### Available skills", body)
        self.assertIn("- imagegen: Generate raster images (path: C:/skills/imagegen/SKILL.md)", body)
        self.assertIn("name + description + file path", body)
        self.assertNotIn("name + description + short path", body)


if __name__ == "__main__":
    unittest.main()
