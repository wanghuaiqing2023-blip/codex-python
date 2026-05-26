from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pycodex.core.agents_md import (
    AGENTS_MD_SEPARATOR,
    DEFAULT_AGENTS_MD_FILENAME,
    HIERARCHICAL_AGENTS_MESSAGE,
    LOCAL_AGENTS_MD_FILENAME,
    AgentsMdConfig,
    AgentsMdManager,
)


class AgentsMdTests(unittest.TestCase):
    def make_config(
        self,
        root: Path,
        *,
        limit: int = 4096,
        instructions: str | None = None,
        fallbacks: tuple[str, ...] = (),
        markers: tuple[str, ...] | None = None,
        child_agents_md: bool = False,
        codex_home: Path | None = None,
    ) -> AgentsMdConfig:
        return AgentsMdConfig(
            cwd=root,
            codex_home=codex_home,
            user_instructions=instructions,
            project_doc_max_bytes=limit,
            project_doc_fallback_filenames=fallbacks,
            project_root_markers=markers,
            child_agents_md=child_agents_md,
        )

    def test_no_doc_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = AgentsMdManager(self.make_config(Path(tmpdir), instructions=None))
            self.assertIsNone(manager.user_instructions())

    def test_doc_smaller_than_limit_is_returned(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text("hello world", encoding="utf-8")

            self.assertEqual(AgentsMdManager(self.make_config(root)).user_instructions(), "hello world")

    def test_project_doc_invalid_utf8_warns_and_uses_lossy_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / "AGENTS.md"
            path.write_bytes(b"project\xff doc")
            warnings: list[str] = []

            result = AgentsMdManager(self.make_config(root)).user_instructions(warnings)

            self.assertEqual(result, "project\ufffd doc")
            self.assertEqual(len(warnings), 1)
            self.assertIn("Project AGENTS.md instructions", warnings[0])
            self.assertIn(str(path.resolve()), warnings[0])
            self.assertIn("invalid UTF-8", warnings[0])
            self.assertIn("Invalid byte sequences were replaced.", warnings[0])

    def test_global_doc_invalid_utf8_warns_and_uses_lossy_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / DEFAULT_AGENTS_MD_FILENAME
            path.write_bytes(b"global\xff doc")
            warnings: list[str] = []

            loaded = AgentsMdManager.load_global_instructions(root, warnings)

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.contents, "global\ufffd doc")
            self.assertEqual(loaded.path, path)
            self.assertEqual(len(warnings), 1)
            self.assertIn("Global AGENTS.md instructions", warnings[0])

    def test_doc_larger_than_limit_is_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            text = "A" * 2048
            (root / "AGENTS.md").write_text(text, encoding="utf-8")

            self.assertEqual(len(AgentsMdManager(self.make_config(root, limit=1024)).user_instructions() or ""), 1024)

    def test_zero_byte_limit_disables_docs_and_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text("something", encoding="utf-8")
            manager = AgentsMdManager(self.make_config(root, limit=0))

            self.assertIsNone(manager.user_instructions())
            self.assertEqual(manager.agents_md_paths(), [])

    def test_merges_existing_instructions_with_agents_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text("proj doc", encoding="utf-8")

            self.assertEqual(
                AgentsMdManager(self.make_config(root, instructions="base instructions")).user_instructions(),
                f"base instructions{AGENTS_MD_SEPARATOR}proj doc",
            )

    def test_keeps_existing_instructions_when_doc_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(
                AgentsMdManager(self.make_config(Path(tmpdir), instructions="some instructions")).user_instructions(),
                "some instructions",
            )

    def test_finds_and_concatenates_root_to_cwd_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / ".git").write_text("gitdir: /path/to/git\n", encoding="utf-8")
            (repo / "AGENTS.md").write_text("root doc", encoding="utf-8")
            nested = repo / "workspace" / "crate_a"
            nested.mkdir(parents=True)
            (nested / "AGENTS.md").write_text("crate doc", encoding="utf-8")

            manager = AgentsMdManager(self.make_config(nested))

            self.assertEqual(manager.user_instructions(), "root doc\n\ncrate doc")
            self.assertEqual(
                [path.name for path in manager.agents_md_paths()],
                ["AGENTS.md", "AGENTS.md"],
            )

    def test_project_root_markers_are_honored_for_agents_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".codex-root").write_text("", encoding="utf-8")
            (root / "AGENTS.md").write_text("parent doc", encoding="utf-8")
            nested = root / "dir1"
            nested.mkdir()
            (nested / ".git").mkdir()
            (nested / "AGENTS.md").write_text("child doc", encoding="utf-8")

            manager = AgentsMdManager(self.make_config(nested, markers=(".codex-root",)))

            self.assertEqual(manager.user_instructions(), "parent doc\n\nchild doc")
            self.assertEqual(manager.agents_md_paths(), [root.resolve() / "AGENTS.md", nested.resolve() / "AGENTS.md"])

    def test_empty_project_root_markers_disable_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            (root / "AGENTS.md").write_text("parent doc", encoding="utf-8")
            nested = root / "dir1"
            nested.mkdir()

            manager = AgentsMdManager(self.make_config(nested, markers=()))

            self.assertIsNone(manager.user_instructions())
            self.assertEqual(manager.agents_md_paths(), [])

    def test_agents_local_md_preferred(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / DEFAULT_AGENTS_MD_FILENAME).write_text("versioned", encoding="utf-8")
            (root / LOCAL_AGENTS_MD_FILENAME).write_text("local", encoding="utf-8")
            manager = AgentsMdManager(self.make_config(root))

            self.assertEqual(manager.user_instructions(), "local")
            self.assertEqual(manager.agents_md_paths()[0].name, LOCAL_AGENTS_MD_FILENAME)

    def test_configured_fallbacks_are_used_after_primary_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "EXAMPLE.md").write_text("example instructions", encoding="utf-8")

            manager = AgentsMdManager(self.make_config(root, fallbacks=("EXAMPLE.md", ".example.md", "EXAMPLE.md")))

            self.assertEqual(manager.candidate_filenames(), ("AGENTS.override.md", "AGENTS.md", "EXAMPLE.md", ".example.md"))
            self.assertEqual(manager.user_instructions(), "example instructions")

            (root / "AGENTS.md").write_text("primary", encoding="utf-8")
            self.assertEqual(manager.user_instructions(), "primary")

    def test_agents_md_directory_is_ignored_and_override_directory_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / LOCAL_AGENTS_MD_FILENAME).mkdir()
            (root / DEFAULT_AGENTS_MD_FILENAME).write_text("primary", encoding="utf-8")

            manager = AgentsMdManager(self.make_config(root))

            self.assertEqual(manager.user_instructions(), "primary")
            self.assertEqual(manager.agents_md_paths()[0].name, DEFAULT_AGENTS_MD_FILENAME)

    def test_instruction_sources_include_global_before_project_docs(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir, tempfile.TemporaryDirectory() as project_dir:
            home = Path(home_dir)
            project = Path(project_dir)
            global_path = home / DEFAULT_AGENTS_MD_FILENAME
            project_path = project / DEFAULT_AGENTS_MD_FILENAME
            global_path.write_text("global doc", encoding="utf-8")
            project_path.write_text("project doc", encoding="utf-8")

            manager = AgentsMdManager(self.make_config(project, codex_home=home))

            self.assertEqual(manager.instruction_sources(), [global_path, project_path.resolve()])

    def test_child_agents_message_appends_only_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.assertIsNone(AgentsMdManager(self.make_config(root)).user_instructions())
            self.assertEqual(
                AgentsMdManager(self.make_config(root, child_agents_md=True)).user_instructions(),
                HIERARCHICAL_AGENTS_MESSAGE,
            )

            (root / "AGENTS.md").write_text("base doc", encoding="utf-8")
            self.assertEqual(
                AgentsMdManager(self.make_config(root, child_agents_md=True)).user_instructions(),
                f"base doc\n\n{HIERARCHICAL_AGENTS_MESSAGE}",
            )


if __name__ == "__main__":
    unittest.main()
