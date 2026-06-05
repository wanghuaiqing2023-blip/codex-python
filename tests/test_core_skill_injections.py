from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from pycodex.core_skills.model import SkillMetadata
from pycodex.core_skills.injections import (
    SkillInjection,
    SkillInjections,
    build_skill_injections,
)


def make_skill(name: str, path: str) -> SkillMetadata:
    return SkillMetadata(name=name, path_to_skills_md=path)


class SkillInjectionsTests(unittest.TestCase):
    def test_empty_mentions_return_default(self) -> None:
        self.assertEqual(build_skill_injections([]), SkillInjections())

    def test_build_skill_injections_reads_files_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first" / "SKILL.md"
            second = Path(tmp) / "second" / "SKILL.md"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_text("first contents", encoding="utf-8")
            second.write_text("second contents", encoding="utf-8")

            result = build_skill_injections(
                [
                    make_skill("first", str(first)),
                    make_skill("second", str(second)),
                ]
            )

        self.assertEqual(
            result,
            SkillInjections(
                (
                    SkillInjection("first", str(first), "first contents"),
                    SkillInjection("second", str(second), "second contents"),
                ),
                (),
            ),
        )

    def test_build_skill_injections_uses_reader_callback(self) -> None:
        seen: list[Path] = []

        def reader(path: Path) -> str:
            seen.append(path)
            return f"loaded {path.name}"

        result = build_skill_injections([make_skill("alpha", "/tmp/alpha/SKILL.md")], reader)

        self.assertEqual(seen, [Path("/tmp/alpha/SKILL.md")])
        self.assertEqual(
            result,
            SkillInjections((SkillInjection("alpha", str(Path("/tmp/alpha/SKILL.md")), "loaded SKILL.md"),), ()),
        )

    def test_build_skill_injections_keeps_warnings_and_continues_after_errors(self) -> None:
        def reader(path: Path) -> str:
            if path.name == "missing.md":
                raise OSError("boom")
            return "ok"

        result = build_skill_injections(
            [
                make_skill("missing", "/tmp/missing.md"),
                make_skill("ok", "/tmp/ok.md"),
            ],
            reader,
        )

        missing_path = Path("/tmp/missing.md")
        ok_path = Path("/tmp/ok.md")
        self.assertEqual(result.items, (SkillInjection("ok", str(ok_path), "ok"),))
        self.assertEqual(result.warnings, (f"Failed to load skill missing at {missing_path}: boom",))

    def test_build_skill_injections_accepts_mapping_inputs(self) -> None:
        result = build_skill_injections(
            [{"name": "alpha", "path": "/tmp/alpha/SKILL.md"}],
            lambda path: path.as_posix(),
        )

        self.assertEqual(
            result,
            SkillInjections((SkillInjection("alpha", str(Path("/tmp/alpha/SKILL.md")), "/tmp/alpha/SKILL.md"),), ()),
        )

    def test_build_skill_injections_warns_for_missing_path(self) -> None:
        result = build_skill_injections([SkillMetadata(name="alpha")])

        self.assertEqual(result.items, ())
        self.assertEqual(result.warnings, ("Failed to load skill alpha at : missing skill path",))


if __name__ == "__main__":
    unittest.main()
