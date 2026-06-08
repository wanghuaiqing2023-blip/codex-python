from __future__ import annotations

import os
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
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust test: no_doc_file_returns_none.
        # Behavior anchor: no configured instructions and no project doc yields None.
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = AgentsMdManager(self.make_config(Path(tmpdir), instructions=None))
            self.assertIsNone(manager.user_instructions())

    def test_doc_smaller_than_limit_is_returned(self) -> None:
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust test: doc_smaller_than_limit_is_returned.
        # Behavior anchor: project doc below project_doc_max_bytes is returned verbatim.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text("hello world", encoding="utf-8")

            self.assertEqual(AgentsMdManager(self.make_config(root)).user_instructions(), "hello world")

    def test_project_doc_invalid_utf8_warns_and_uses_lossy_text(self) -> None:
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust test: project_doc_invalid_utf8_warns_and_uses_lossy_text.
        # Behavior anchor: invalid UTF-8 emits a Project warning and uses lossy replacement text.
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
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust test: global_doc_invalid_utf8_warns_and_uses_lossy_text.
        # Behavior anchor: global AGENTS.md invalid UTF-8 emits a Global warning and uses lossy text.
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
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust test: doc_larger_than_limit_is_truncated.
        # Behavior anchor: project docs are truncated to the remaining byte budget.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            text = "A" * 2048
            (root / "AGENTS.md").write_text(text, encoding="utf-8")

            self.assertEqual(len(AgentsMdManager(self.make_config(root, limit=1024)).user_instructions() or ""), 1024)

    def test_zero_byte_limit_disables_docs_and_discovery(self) -> None:
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust tests: zero_byte_limit_disables_docs and zero_byte_limit_disables_discovery.
        # Behavior anchor: project_doc_max_bytes=0 disables both content loading and path discovery.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text("something", encoding="utf-8")
            manager = AgentsMdManager(self.make_config(root, limit=0))

            self.assertIsNone(manager.user_instructions())
            self.assertEqual(manager.agents_md_paths(), [])

    def test_merges_existing_instructions_with_agents_md(self) -> None:
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust test: merges_existing_instructions_with_agents_md.
        # Behavior anchor: configured instructions and AGENTS.md are joined with AGENTS_MD_SEPARATOR.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text("proj doc", encoding="utf-8")

            self.assertEqual(
                AgentsMdManager(self.make_config(root, instructions="base instructions")).user_instructions(),
                f"base instructions{AGENTS_MD_SEPARATOR}proj doc",
            )

    def test_keeps_existing_instructions_when_doc_missing(self) -> None:
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust test: keeps_existing_instructions_when_doc_missing.
        # Behavior anchor: configured instructions are preserved when no project doc is discovered.
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(
                AgentsMdManager(self.make_config(Path(tmpdir), instructions="some instructions")).user_instructions(),
                "some instructions",
            )

    def test_finds_and_concatenates_root_to_cwd_docs(self) -> None:
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust tests: finds_doc_in_repo_root and concatenates_root_and_cwd_docs.
        # Behavior anchor: discovery stops at the project root and concatenates docs root-to-cwd.
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
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust test: project_root_markers_are_honored_for_agents_discovery.
        # Behavior anchor: configured markers replace default marker behavior for discovery.
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
        # Rust source: codex-rs/core/src/agents_md.rs
        # Behavior anchor: an empty project_root_markers list disables parent traversal.
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
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust test: agents_local_md_preferred.
        # Behavior anchor: AGENTS.override.md wins over AGENTS.md in the same directory.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / DEFAULT_AGENTS_MD_FILENAME).write_text("versioned", encoding="utf-8")
            (root / LOCAL_AGENTS_MD_FILENAME).write_text("local", encoding="utf-8")
            manager = AgentsMdManager(self.make_config(root))

            self.assertEqual(manager.user_instructions(), "local")
            self.assertEqual(manager.agents_md_paths()[0].name, LOCAL_AGENTS_MD_FILENAME)

    def test_configured_fallbacks_are_used_after_primary_names(self) -> None:
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust tests: uses_configured_fallback_when_agents_missing and agents_md_preferred_over_fallbacks.
        # Behavior anchor: fallback filenames are considered after override/default names and deduplicated.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "EXAMPLE.md").write_text("example instructions", encoding="utf-8")

            manager = AgentsMdManager(self.make_config(root, fallbacks=("EXAMPLE.md", ".example.md", "EXAMPLE.md")))

            self.assertEqual(manager.candidate_filenames(), ("AGENTS.override.md", "AGENTS.md", "EXAMPLE.md", ".example.md"))
            self.assertEqual(manager.user_instructions(), "example instructions")

            (root / "AGENTS.md").write_text("primary", encoding="utf-8")
            self.assertEqual(manager.user_instructions(), "primary")

    def test_agents_md_directory_is_ignored(self) -> None:
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust test: agents_md_directory_is_ignored.
        # Behavior anchor: AGENTS.md directory entries are not treated as instruction files.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / DEFAULT_AGENTS_MD_FILENAME).mkdir()

            manager = AgentsMdManager(self.make_config(root))

            self.assertIsNone(manager.user_instructions())
            self.assertEqual(manager.agents_md_paths(), [])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO special-file behavior is Unix-specific upstream")
    def test_agents_md_special_file_is_ignored(self) -> None:
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust test: agents_md_special_file_is_ignored.
        # Behavior anchor: non-regular AGENTS.md filesystem entries are not treated as instruction files.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            os.mkfifo(root / DEFAULT_AGENTS_MD_FILENAME, 0o644)

            manager = AgentsMdManager(self.make_config(root))

            self.assertIsNone(manager.user_instructions())
            self.assertEqual(manager.agents_md_paths(), [])

    def test_override_directory_falls_back_to_agents_md_file(self) -> None:
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust test: override_directory_falls_back_to_agents_md_file.
        # Behavior anchor: an AGENTS.override.md directory is ignored, allowing AGENTS.md to win.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / LOCAL_AGENTS_MD_FILENAME).mkdir()
            (root / DEFAULT_AGENTS_MD_FILENAME).write_text("primary", encoding="utf-8")

            manager = AgentsMdManager(self.make_config(root))

            self.assertEqual(manager.user_instructions(), "primary")
            self.assertEqual(manager.agents_md_paths()[0].name, DEFAULT_AGENTS_MD_FILENAME)

    def test_instruction_sources_include_global_before_project_docs(self) -> None:
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust test: instruction_sources_include_global_before_agents_md_docs.
        # Behavior anchor: global instruction source paths are listed before project doc paths.
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
        # Rust source: codex-rs/core/src/agents_md.rs
        # Behavior anchor: ChildAgentsMd appends the hierarchical AGENTS.md guidance only when enabled.
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

    def test_skills_are_not_appended_to_agents_md(self) -> None:
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust test: skills_are_not_appended_to_agents_md.
        # Behavior anchor: skill metadata under codex_home is not appended to AGENTS.md user instructions.
        with tempfile.TemporaryDirectory() as home_dir, tempfile.TemporaryDirectory() as project_dir:
            home = Path(home_dir)
            project = Path(project_dir)
            (project / DEFAULT_AGENTS_MD_FILENAME).write_text("base doc", encoding="utf-8")
            skill_dir = home / "skills" / "pdf-processing"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: pdf-processing\ndescription: extract from pdfs\n---\n\n# Body\n",
                encoding="utf-8",
            )

            manager = AgentsMdManager(self.make_config(project, codex_home=home))

            self.assertEqual(manager.user_instructions(), "base doc")

    def test_apps_do_not_emit_or_append_user_instructions(self) -> None:
        # Rust source: codex-rs/core/src/agents_md.rs
        # Rust tests: apps_feature_does_not_emit_user_instructions_by_itself
        # and apps_feature_does_not_append_to_agents_md_user_instructions.
        # Behavior anchor: app/plugin availability does not affect this AGENTS.md assembly contract.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.assertIsNone(AgentsMdManager(self.make_config(root)).user_instructions())

            (root / DEFAULT_AGENTS_MD_FILENAME).write_text("base doc", encoding="utf-8")
            self.assertEqual(AgentsMdManager(self.make_config(root)).user_instructions(), "base doc")


if __name__ == "__main__":
    unittest.main()
