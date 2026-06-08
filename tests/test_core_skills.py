import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.core_skills.model import SkillError, SkillMetadata
from pycodex.core_skills.invocation_utils import SkillLoadOutcome
from pycodex.core_skills.rendering import (
    SKILLS_INTRO_WITH_ABSOLUTE_PATHS,
    SkillRenderSideEffects,
)
from pycodex.core.skills import (
    SkillInvocation,
    SkillsLoadInput,
    maybe_emit_implicit_skill_invocation,
    render,
    render_available_skills_body,
    skills_load_input_from_config,
)


class Telemetry:
    def __init__(self) -> None:
        self.counters: list[tuple[str, int, tuple[tuple[str, str], ...]]] = []

    def counter(self, name: str, inc: int, tags: tuple[tuple[str, str], ...]) -> None:
        self.counters.append((name, inc, tags))


class Analytics:
    def __init__(self) -> None:
        self.invocations: list[tuple[dict[str, str], tuple[SkillInvocation, ...]]] = []

    def track_skill_invocations(self, context: dict[str, str], invocations: tuple[SkillInvocation, ...]) -> None:
        self.invocations.append((context, invocations))


class SkillsTests(unittest.IsolatedAsyncioTestCase):
    def test_skills_load_input_from_config_matches_rust_fields(self) -> None:
        config = SimpleNamespace(
            cwd=Path("/work"),
            config_layer_stack=("base", "profile"),
            bundled_skills_enabled=lambda: False,
        )

        self.assertEqual(
            skills_load_input_from_config(config, ("root-a", "root-b")),
            SkillsLoadInput(
                cwd=Path("/work"),
                effective_skill_roots=("root-a", "root-b"),
                config_layer_stack=("base", "profile"),
                bundled_skills_enabled=False,
            ),
        )

    def test_skills_load_input_from_mapping_defaults_bundled_enabled(self) -> None:
        self.assertEqual(
            skills_load_input_from_config({"cwd": "/work"}, ()),
            SkillsLoadInput(Path("/work"), (), None, True),
        )

    def test_core_skills_facade_reexports_rust_public_surface(self) -> None:
        # Rust: codex-core/src/skills.rs re-exports model/render/remote names from codex_core_skills.
        self.assertEqual(SkillError("/skills/bad/SKILL.md", "bad").path, Path("/skills/bad/SKILL.md"))
        self.assertIs(render.SkillRenderSideEffects, SkillRenderSideEffects)
        self.assertEqual(render.SKILLS_INTRO_WITH_ABSOLUTE_PATHS, SKILLS_INTRO_WITH_ABSOLUTE_PATHS)
        self.assertTrue(render_available_skills_body((), ()).startswith("\n## Skills\n"))

        from pycodex.core import skills as core_skills

        self.assertIs(core_skills.model.SkillMetadata, SkillMetadata)
        self.assertIs(core_skills.remote.list_remote_skills, core_skills.remote.list_remote_skills)
        self.assertIs(core_skills.render.render_available_skills_body, render_available_skills_body)

    def test_skill_render_side_effects_matches_rust_variants(self) -> None:
        # Rust: SkillRenderSideEffects::{None, ThreadStart { session_telemetry }}.
        telemetry = object()

        self.assertEqual(SkillRenderSideEffects.none(), SkillRenderSideEffects("none"))
        self.assertEqual(
            SkillRenderSideEffects.thread_start(telemetry),
            SkillRenderSideEffects("thread_start", telemetry),
        )

    async def test_maybe_emit_implicit_skill_invocation_records_once(self) -> None:
        skill = SkillMetadata(
            name="script-runner",
            path_to_skills_md=Path("/skills/script-runner/SKILL.md"),
            scope="repo",
            plugin_id="plugin-a",
        )
        outcome = SkillLoadOutcome(
            skills=(skill,),
            implicit_skills_by_scripts_dir={Path("/work/scripts"): skill},
        )
        telemetry = Telemetry()
        analytics = Analytics()
        turn_context = SimpleNamespace(
            turn_skills=SimpleNamespace(outcome=outcome, implicit_invocation_seen_skills=set()),
            session_telemetry=telemetry,
            model_info=SimpleNamespace(slug="gpt-test"),
            sub_id="turn-1",
        )
        sess = SimpleNamespace(
            conversation_id="conversation-1",
            services=SimpleNamespace(analytics_events_client=analytics),
        )

        invocation = await maybe_emit_implicit_skill_invocation(
            sess,
            turn_context,
            "python scripts/run.py",
            Path("/work"),
        )
        duplicate = await maybe_emit_implicit_skill_invocation(
            sess,
            turn_context,
            "python scripts/run.py",
            Path("/work"),
        )

        self.assertEqual(
            invocation,
            SkillInvocation(
                skill_name="script-runner",
                skill_scope="repo",
                skill_path=Path("/skills/script-runner/SKILL.md"),
                plugin_id="plugin-a",
            ),
        )
        self.assertIsNone(duplicate)
        self.assertEqual(len(telemetry.counters), 1)
        self.assertEqual(telemetry.counters[0][0], "codex.skill.injected")
        self.assertEqual(len(analytics.invocations), 1)
        self.assertEqual(analytics.invocations[0][0]["model"], "gpt-test")

    async def test_maybe_emit_implicit_skill_invocation_returns_none_without_candidate(self) -> None:
        turn_context = SimpleNamespace(
            turn_skills=SimpleNamespace(outcome=SkillLoadOutcome(), implicit_invocation_seen_skills=set()),
            session_telemetry=Telemetry(),
            model_info=SimpleNamespace(slug="gpt-test"),
            sub_id="turn-1",
        )
        sess = SimpleNamespace(conversation_id="conversation-1", services=SimpleNamespace(analytics_events_client=Analytics()))

        self.assertIsNone(await maybe_emit_implicit_skill_invocation(sess, turn_context, "echo hi", Path("/work")))


if __name__ == "__main__":
    unittest.main()
