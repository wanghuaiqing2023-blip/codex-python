from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from pycodex.core_skills.model import SkillMetadata
from pycodex.core_skills.invocation_utils import (
    SkillLoadOutcome,
    SkillPolicy,
    build_implicit_skill_path_indexes,
    canonicalize_if_exists,
    command_basename,
    command_reads_file,
    detect_implicit_skill_invocation_for_command,
    detect_skill_doc_read,
    detect_skill_script_run,
    filter_skill_load_outcome_for_product,
    script_run_token,
    skill_allows_implicit_invocation,
    skill_matches_product_restriction,
    skill_load_outcome_with_implicit_indexes,
    tokenize_command,
)
from pycodex.protocol import Product


def make_skill(name: str, skill_doc_path: Path | str, policy: object | None = None) -> SkillMetadata:
    return SkillMetadata(
        name=name,
        description="test",
        path_to_skills_md=Path(skill_doc_path),
        policy=policy,
    )


class SkillInvocationUtilsTests(unittest.TestCase):
    def test_tokenize_command_uses_shlex_and_falls_back(self) -> None:
        self.assertEqual(tokenize_command('python "scripts/run me.py"'), ["python", "scripts/run me.py"])
        self.assertEqual(tokenize_command('python "unterminated'), ["python", '"unterminated'])

    def test_script_run_detection_matches_runner_plus_extension(self) -> None:
        self.assertEqual(script_run_token(["python3", "-u", "scripts/fetch_comments.py"]), "scripts/fetch_comments.py")
        self.assertEqual(script_run_token([r"C:\Python\python.exe", "--", "scripts/run.ps1"]), "scripts/run.ps1")

    def test_script_run_detection_excludes_python_c(self) -> None:
        self.assertIsNone(script_run_token(["python3", "-c", "print(1)"]))
        self.assertIsNone(script_run_token(["python3", "-m", "module.name"]))
        self.assertIsNone(script_run_token(["git", "scripts/run.py"]))

    def test_command_reads_file_uses_reader_basenames(self) -> None:
        self.assertTrue(command_reads_file(["cat", "SKILL.md"]))
        self.assertTrue(command_reads_file(["/usr/bin/sed", "-n", "1p", "SKILL.md"]))
        self.assertFalse(command_reads_file(["python", "SKILL.md"]))
        self.assertEqual(command_basename("/usr/bin/python3"), "python3")

    def test_build_implicit_skill_path_indexes_maps_doc_and_scripts_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skill-test"
            scripts = root / "scripts"
            scripts.mkdir(parents=True)
            doc = root / "SKILL.md"
            doc.write_text("skill", encoding="utf-8")
            skill = make_skill("test-skill", doc)

            by_scripts_dir, by_doc_path = build_implicit_skill_path_indexes([skill])

            self.assertEqual(by_scripts_dir[canonicalize_if_exists(scripts)], skill)
            self.assertEqual(by_doc_path[canonicalize_if_exists(doc)], skill)

    def test_skill_doc_read_detection_matches_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            doc = workdir / "skill-test" / "SKILL.md"
            doc.parent.mkdir()
            doc.write_text("skill", encoding="utf-8")
            skill = make_skill("test-skill", doc)
            outcome = SkillLoadOutcome(implicit_skills_by_doc_path={canonicalize_if_exists(doc): skill})

            found = detect_skill_doc_read(outcome, ["cat", str(doc), "|", "head"], workdir)

            self.assertEqual(found, skill)

    def test_skill_script_run_detection_matches_relative_path_from_skill_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skill-test"
            script = root / "scripts" / "fetch_comments.py"
            script.parent.mkdir(parents=True)
            script.write_text("print('ok')", encoding="utf-8")
            doc = root / "SKILL.md"
            doc.write_text("skill", encoding="utf-8")
            skill = make_skill("test-skill", doc)
            outcome = SkillLoadOutcome(
                implicit_skills_by_scripts_dir={canonicalize_if_exists(script.parent): skill},
            )

            found = detect_skill_script_run(outcome, ["python3", "scripts/fetch_comments.py"], root)

            self.assertEqual(found, skill)

    def test_skill_script_run_detection_matches_absolute_path_from_any_workdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skill-test"
            other = Path(tmp) / "other"
            script = root / "scripts" / "fetch_comments.py"
            script.parent.mkdir(parents=True)
            other.mkdir()
            script.write_text("print('ok')", encoding="utf-8")
            doc = root / "SKILL.md"
            doc.write_text("skill", encoding="utf-8")
            skill = make_skill("test-skill", doc)
            outcome = SkillLoadOutcome(
                implicit_skills_by_scripts_dir={canonicalize_if_exists(script.parent): skill},
            )

            found = detect_skill_script_run(outcome, ["python3", str(script)], other)

            self.assertEqual(found, skill)

    def test_detect_implicit_skill_invocation_prefers_script_over_doc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skill-test"
            script = root / "scripts" / "run.py"
            doc = root / "SKILL.md"
            script.parent.mkdir(parents=True)
            script.write_text("print('ok')", encoding="utf-8")
            doc.write_text("skill", encoding="utf-8")
            script_skill = make_skill("script-skill", doc)
            doc_skill = make_skill("doc-skill", doc)
            outcome = SkillLoadOutcome(
                implicit_skills_by_scripts_dir={canonicalize_if_exists(script.parent): script_skill},
                implicit_skills_by_doc_path={canonicalize_if_exists(doc): doc_skill},
            )

            found = detect_implicit_skill_invocation_for_command(outcome, "python scripts/run.py", root)

            self.assertEqual(found, script_skill)

    def test_skill_load_outcome_filters_disabled_and_implicit_policy(self) -> None:
        enabled = make_skill("enabled", "/tmp/enabled/SKILL.md")
        disabled = make_skill("disabled", "/tmp/disabled/SKILL.md")
        no_implicit = make_skill("no-implicit", "/tmp/no/SKILL.md", {"allowImplicitInvocation": False})
        outcome = SkillLoadOutcome(
            skills=(enabled, disabled, no_implicit),
            disabled_paths=frozenset({Path("/tmp/disabled/SKILL.md")}),
        )

        self.assertTrue(skill_allows_implicit_invocation(enabled))
        self.assertFalse(skill_allows_implicit_invocation(no_implicit))
        self.assertEqual(outcome.allowed_skills_for_implicit_invocation(), (enabled,))
        self.assertEqual(outcome.skills_with_enabled(), ((enabled, True), (disabled, False), (no_implicit, True)))

    def test_skill_load_outcome_with_implicit_indexes_uses_allowed_skills_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            enabled_doc = Path(tmp) / "enabled" / "SKILL.md"
            disabled_doc = Path(tmp) / "disabled" / "SKILL.md"
            enabled_doc.parent.mkdir()
            disabled_doc.parent.mkdir()
            enabled_doc.write_text("ok", encoding="utf-8")
            disabled_doc.write_text("disabled", encoding="utf-8")
            enabled = make_skill("enabled", enabled_doc)
            disabled = make_skill("disabled", disabled_doc)
            outcome = SkillLoadOutcome(
                skills=(enabled, disabled),
                disabled_paths=frozenset({disabled_doc}),
            )

            indexed = skill_load_outcome_with_implicit_indexes(outcome)

            self.assertIn(canonicalize_if_exists(enabled_doc), indexed.implicit_skills_by_doc_path)
            self.assertNotIn(canonicalize_if_exists(disabled_doc), indexed.implicit_skills_by_doc_path)

    def test_skill_policy_product_matching_defaults_to_allowed(self) -> None:
        unrestricted = make_skill("unrestricted", "/tmp/unrestricted/SKILL.md")
        codex_only = make_skill(
            "codex-only",
            "/tmp/codex/SKILL.md",
            SkillPolicy(products=(Product.CODEX,)),
        )
        chatgpt_only = make_skill(
            "chatgpt-only",
            "/tmp/chatgpt/SKILL.md",
            {"products": ["chatgpt"]},
        )

        self.assertTrue(skill_matches_product_restriction(unrestricted, None))
        self.assertTrue(skill_matches_product_restriction(codex_only, Product.CODEX))
        self.assertFalse(skill_matches_product_restriction(codex_only, Product.CHATGPT))
        self.assertFalse(skill_matches_product_restriction(codex_only, None))
        self.assertTrue(skill_matches_product_restriction(chatgpt_only, "CHATGPT"))

    def test_filter_skill_load_outcome_for_product_trims_skills_roots_and_indexes(self) -> None:
        codex_skill = make_skill("codex", "/tmp/codex/SKILL.md", SkillPolicy(products=(Product.CODEX,)))
        chat_skill = make_skill("chatgpt", "/tmp/chat/SKILL.md", SkillPolicy(products=(Product.CHATGPT,)))
        shared_skill = make_skill("shared", "/tmp/shared/SKILL.md")
        outcome = SkillLoadOutcome(
            skills=(codex_skill, chat_skill, shared_skill),
            skill_roots=(Path("/tmp/codex"), Path("/tmp/chat"), Path("/tmp/shared")),
            skill_root_by_path={
                Path("/tmp/codex/SKILL.md"): Path("/tmp/codex"),
                Path("/tmp/chat/SKILL.md"): Path("/tmp/chat"),
                Path("/tmp/shared/SKILL.md"): Path("/tmp/shared"),
            },
            implicit_skills_by_scripts_dir={
                Path("/tmp/codex/scripts"): codex_skill,
                Path("/tmp/chat/scripts"): chat_skill,
                Path("/tmp/shared/scripts"): shared_skill,
            },
            implicit_skills_by_doc_path={
                Path("/tmp/codex/SKILL.md"): codex_skill,
                Path("/tmp/chat/SKILL.md"): chat_skill,
                Path("/tmp/shared/SKILL.md"): shared_skill,
            },
        )

        filtered = filter_skill_load_outcome_for_product(outcome, Product.CODEX)

        self.assertEqual(filtered.skills, (codex_skill, shared_skill))
        self.assertEqual(filtered.skill_roots, (Path("/tmp/codex"), Path("/tmp/shared")))
        self.assertEqual(
            filtered.skill_root_by_path,
            {
                Path("/tmp/codex/SKILL.md"): Path("/tmp/codex"),
                Path("/tmp/shared/SKILL.md"): Path("/tmp/shared"),
            },
        )
        self.assertEqual(
            filtered.implicit_skills_by_scripts_dir,
            {
                Path("/tmp/codex/scripts"): codex_skill,
                Path("/tmp/shared/scripts"): shared_skill,
            },
        )
        self.assertEqual(
            filtered.implicit_skills_by_doc_path,
            {
                Path("/tmp/codex/SKILL.md"): codex_skill,
                Path("/tmp/shared/SKILL.md"): shared_skill,
            },
        )

    def test_filter_skill_load_outcome_for_product_none_keeps_unrestricted_only(self) -> None:
        restricted = make_skill("restricted", "/tmp/restricted/SKILL.md", SkillPolicy(products=(Product.CODEX,)))
        unrestricted = make_skill("unrestricted", "/tmp/unrestricted/SKILL.md")
        outcome = SkillLoadOutcome(skills=(restricted, unrestricted))

        filtered = filter_skill_load_outcome_for_product(outcome, None)

        self.assertEqual(filtered.skills, (unrestricted,))


if __name__ == "__main__":
    unittest.main()
