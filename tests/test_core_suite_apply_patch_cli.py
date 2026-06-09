import os
import shutil
import tempfile
import unittest
from pathlib import Path

from pycodex.apply_patch import (
    StreamingPatchParser,
    ApplyPatchFileChange,
    apply_patch_action_to_disk,
    convert_apply_patch_hunks_to_protocol,
    maybe_parse_apply_patch_verified,
)
from pycodex.core.shell import Shell, ShellType
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.handlers.unified_exec import ExecCommandHandler
from pycodex.core.tools.registry import ToolInvocation


def _verified_action(root: Path, patch: str):
    result = maybe_parse_apply_patch_verified(("apply_patch", patch), root)
    if result.type != "body":
        raise AssertionError(f"expected verified patch body, got {result.type}: {result.error}")
    return result.body


def _verification_error(root: Path, patch: str) -> str:
    result = maybe_parse_apply_patch_verified(("apply_patch", patch), root)
    if result.type == "body":
        raise AssertionError("expected verification error")
    return str(result.error)


def _apply(root: Path, patch: str) -> str:
    action = _verified_action(root, patch)
    return apply_patch_action_to_disk(action)


class CoreSuiteApplyPatchCliTests(unittest.TestCase):
    def test_apply_patch_cli_uses_codex_self_exe_with_linux_sandbox_helper_alias(self) -> None:
        # Rust source: codex/codex-rs/core/tests/suite/apply_patch_cli.rs
        # Rust test: apply_patch_cli_uses_codex_self_exe_with_linux_sandbox_helper_alias.
        # Python parity scope: direct apply_patch entrypoint applies the same add-file patch.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out = _apply(
                root,
                "*** Begin Patch\n*** Add File: helper-alias.txt\n+hello\n*** End Patch",
            )

            self.assertIn("Success. Updated the following files:", out)
            self.assertEqual((root / "helper-alias.txt").read_text(encoding="utf-8"), "hello\n")

    def test_apply_patch_cli_multiple_operations_integration(self) -> None:
        # Rust test: apply_patch_cli_multiple_operations_integration.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "modify.txt").write_text("line1\nline2\n", encoding="utf-8")
            (root / "delete.txt").write_text("obsolete\n", encoding="utf-8")

            out = _apply(
                root,
                "*** Begin Patch\n"
                "*** Add File: nested/new.txt\n"
                "+created\n"
                "*** Delete File: delete.txt\n"
                "*** Update File: modify.txt\n"
                "@@\n"
                "-line2\n"
                "+changed\n"
                "*** End Patch",
            )

            self.assertIn("A ", out)
            self.assertIn("M ", out)
            self.assertIn("D ", out)
            self.assertEqual((root / "nested/new.txt").read_text(encoding="utf-8"), "created\n")
            self.assertEqual((root / "modify.txt").read_text(encoding="utf-8"), "line1\nchanged\n")
            self.assertFalse((root / "delete.txt").exists())

    def test_apply_patch_cli_multiple_chunks(self) -> None:
        # Rust test: apply_patch_cli_multiple_chunks.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "multi.txt").write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")
            _apply(
                root,
                "*** Begin Patch\n*** Update File: multi.txt\n@@\n-line2\n+changed2\n@@\n-line4\n+changed4\n*** End Patch",
            )
            self.assertEqual(
                (root / "multi.txt").read_text(encoding="utf-8"),
                "line1\nchanged2\nline3\nchanged4\n",
            )

    def test_apply_patch_cli_moves_file_to_new_directory(self) -> None:
        # Rust test: apply_patch_cli_moves_file_to_new_directory.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "old").mkdir()
            (root / "old/name.txt").write_text("old content\n", encoding="utf-8")
            _apply(
                root,
                "*** Begin Patch\n*** Update File: old/name.txt\n*** Move to: renamed/dir/name.txt\n@@\n-old content\n+new content\n*** End Patch",
            )
            self.assertFalse((root / "old/name.txt").exists())
            self.assertEqual((root / "renamed/dir/name.txt").read_text(encoding="utf-8"), "new content\n")

    def test_apply_patch_cli_updates_file_appends_trailing_newline(self) -> None:
        # Rust test: apply_patch_cli_updates_file_appends_trailing_newline.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "no_newline.txt").write_text("no newline at end", encoding="utf-8")
            _apply(
                root,
                "*** Begin Patch\n*** Update File: no_newline.txt\n@@\n-no newline at end\n+first line\n+second line\n*** End Patch",
            )
            self.assertEqual((root / "no_newline.txt").read_text(encoding="utf-8"), "first line\nsecond line\n")

    def test_apply_patch_cli_insert_only_hunk_modifies_file(self) -> None:
        # Rust test: apply_patch_cli_insert_only_hunk_modifies_file.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "insert_only.txt").write_text("alpha\nomega\n", encoding="utf-8")
            _apply(
                root,
                "*** Begin Patch\n*** Update File: insert_only.txt\n@@\n alpha\n+beta\n omega\n*** End Patch",
            )
            self.assertEqual((root / "insert_only.txt").read_text(encoding="utf-8"), "alpha\nbeta\nomega\n")

    def test_apply_patch_cli_move_overwrites_existing_destination(self) -> None:
        # Rust test: apply_patch_cli_move_overwrites_existing_destination.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "old").mkdir()
            (root / "renamed/dir").mkdir(parents=True)
            (root / "old/name.txt").write_text("from\n", encoding="utf-8")
            (root / "renamed/dir/name.txt").write_text("existing\n", encoding="utf-8")
            _apply(
                root,
                "*** Begin Patch\n*** Update File: old/name.txt\n*** Move to: renamed/dir/name.txt\n@@\n-from\n+new\n*** End Patch",
            )
            self.assertFalse((root / "old/name.txt").exists())
            self.assertEqual((root / "renamed/dir/name.txt").read_text(encoding="utf-8"), "new\n")

    def test_apply_patch_cli_move_without_content_change_has_no_turn_diff(self) -> None:
        # Rust test: apply_patch_cli_move_without_content_change_has_no_turn_diff.
        # Python parity scope: pure move action carries no textual unified diff.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "old").mkdir()
            (root / "old/name.txt").write_text("same\n", encoding="utf-8")
            action = _verified_action(
                root,
                "*** Begin Patch\n*** Update File: old/name.txt\n*** Move to: renamed/name.txt\n@@\n same\n*** End Patch",
            )
            change = action.changes[Path(root / "old/name.txt")]
            self.assertEqual(change.unified_diff, "")
            apply_patch_action_to_disk(action)
            self.assertFalse((root / "old/name.txt").exists())
            self.assertEqual((root / "renamed/name.txt").read_text(encoding="utf-8"), "same\n")

    def test_apply_patch_cli_add_overwrites_existing_file(self) -> None:
        # Rust test: apply_patch_cli_add_overwrites_existing_file.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "duplicate.txt").write_text("old content\n", encoding="utf-8")
            _apply(root, "*** Begin Patch\n*** Add File: duplicate.txt\n+new content\n*** End Patch")
            self.assertEqual((root / "duplicate.txt").read_text(encoding="utf-8"), "new content\n")

    def test_apply_patch_cli_rejects_invalid_hunk_header(self) -> None:
        # Rust test: apply_patch_cli_rejects_invalid_hunk_header.
        with tempfile.TemporaryDirectory() as tmpdir:
            error = _verification_error(
                Path(tmpdir),
                "*** Begin Patch\n*** Frobnicate File: foo\n*** End Patch",
            )
            self.assertIn("is not a valid hunk header", error)

    def test_apply_patch_cli_reports_missing_context(self) -> None:
        # Rust test: apply_patch_cli_reports_missing_context.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "modify.txt").write_text("line1\nline2\n", encoding="utf-8")
            error = _verification_error(
                root,
                "*** Begin Patch\n*** Update File: modify.txt\n@@\n-missing\n+changed\n*** End Patch",
            )
            self.assertIn("Failed to find expected lines in", error)
            self.assertEqual((root / "modify.txt").read_text(encoding="utf-8"), "line1\nline2\n")

    def test_apply_patch_cli_reports_missing_target_file(self) -> None:
        # Rust test: apply_patch_cli_reports_missing_target_file.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            error = _verification_error(
                root,
                "*** Begin Patch\n*** Update File: missing.txt\n@@\n-nope\n+better\n*** End Patch",
            )
            self.assertIn("Failed to read file to update", error)
            self.assertIn("missing.txt", error)
            self.assertFalse((root / "missing.txt").exists())

    def test_apply_patch_cli_delete_missing_file_reports_error(self) -> None:
        # Rust test: apply_patch_cli_delete_missing_file_reports_error.
        with tempfile.TemporaryDirectory() as tmpdir:
            error = _verification_error(Path(tmpdir), "*** Begin Patch\n*** Delete File: missing.txt\n*** End Patch")
            self.assertIn("Failed to read", error)
            self.assertIn("missing.txt", error)

    def test_apply_patch_cli_rejects_empty_patch(self) -> None:
        # Rust test: apply_patch_cli_rejects_empty_patch.
        with tempfile.TemporaryDirectory() as tmpdir:
            error = _verification_error(Path(tmpdir), "*** Begin Patch\n*** End Patch")
            self.assertIn("must contain at least one hunk", error)

    def test_apply_patch_cli_delete_directory_reports_verification_error(self) -> None:
        # Rust test: apply_patch_cli_delete_directory_reports_verification_error.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "dir").mkdir()
            error = _verification_error(root, "*** Begin Patch\n*** Delete File: dir\n*** End Patch")
            self.assertIn("Failed to read", error)
            self.assertTrue((root / "dir").is_dir())

    def test_apply_patch_cli_rejects_path_traversal_outside_workspace(self) -> None:
        # Rust test: apply_patch_cli_rejects_path_traversal_outside_workspace.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            error = _verification_error(root, "*** Begin Patch\n*** Add File: ../escape.txt\n+escape\n*** End Patch")
            self.assertIn("escapes workspace", error)
            self.assertFalse((root.parent / "escape.txt").exists())

    def test_intercepted_apply_patch_verification_uses_local_sandbox(self) -> None:
        # Rust test: intercepted_apply_patch_verification_uses_local_sandbox.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            action = _verified_action(root, "*** Begin Patch\n*** Add File: local.txt\n+ok\n*** End Patch")
            self.assertEqual(list(action.changes), [root / "local.txt"])

    def test_apply_patch_cli_does_not_write_through_symlink_escape_outside_workspace(self) -> None:
        # Rust test: apply_patch_cli_does_not_write_through_symlink_escape_outside_workspace.
        if not hasattr(os, "symlink"):
            self.skipTest("symlink is unavailable")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "root"
            outside = Path(tmpdir) / "outside"
            root.mkdir()
            outside.write_text("outside\n", encoding="utf-8")
            try:
                os.symlink(outside, root / "link.txt")
            except OSError as exc:
                self.skipTest(f"symlink unavailable: {exc}")
            error = _verification_error(root, "*** Begin Patch\n*** Update File: link.txt\n@@\n-outside\n+changed\n*** End Patch")
            self.assertIn("escapes workspace", error)
            self.assertEqual(outside.read_text(encoding="utf-8"), "outside\n")

    def test_apply_patch_cli_preserves_existing_hard_link_outside_workspace(self) -> None:
        # Rust test: apply_patch_cli_preserves_existing_hard_link_outside_workspace.
        if not hasattr(os, "link"):
            self.skipTest("hard links are unavailable")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "root"
            root.mkdir()
            outside = Path(tmpdir) / "outside.txt"
            inside = root / "inside.txt"
            outside.write_text("old\n", encoding="utf-8")
            try:
                os.link(outside, inside)
            except OSError as exc:
                self.skipTest(f"hard links unavailable: {exc}")
            _apply(root, "*** Begin Patch\n*** Update File: inside.txt\n@@\n-old\n+new\n*** End Patch")
            self.assertEqual(inside.read_text(encoding="utf-8"), "new\n")
            self.assertEqual(outside.read_text(encoding="utf-8"), "new\n")

    def test_apply_patch_cli_rejects_move_path_traversal_outside_workspace(self) -> None:
        # Rust test: apply_patch_cli_rejects_move_path_traversal_outside_workspace.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "inside.txt").write_text("old\n", encoding="utf-8")
            error = _verification_error(
                root,
                "*** Begin Patch\n*** Update File: inside.txt\n*** Move to: ../outside.txt\n@@\n-old\n+new\n*** End Patch",
            )
            self.assertIn("escapes workspace", error)
            self.assertTrue((root / "inside.txt").exists())

    def test_apply_patch_cli_verification_failure_has_no_side_effects(self) -> None:
        # Rust test: apply_patch_cli_verification_failure_has_no_side_effects.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "stable.txt").write_text("stable\n", encoding="utf-8")
            error = _verification_error(
                root,
                "*** Begin Patch\n*** Add File: added.txt\n+new\n*** Update File: stable.txt\n@@\n-missing\n+changed\n*** End Patch",
            )
            self.assertIn("Failed to find expected lines in", error)
            self.assertFalse((root / "added.txt").exists())
            self.assertEqual((root / "stable.txt").read_text(encoding="utf-8"), "stable\n")

    def test_apply_patch_shell_command_heredoc_with_cd_updates_relative_workdir(self) -> None:
        # Rust test: apply_patch_shell_command_heredoc_with_cd_updates_relative_workdir.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "sub").mkdir()
            (root / "sub/in_sub.txt").write_text("before\n", encoding="utf-8")
            script = "cd sub && apply_patch <<'EOF'\n*** Begin Patch\n*** Update File: in_sub.txt\n@@\n-before\n+after\n*** End Patch\nEOF\n"
            action = maybe_parse_apply_patch_verified(("sh", "-c", script), root).body
            self.assertIsNotNone(action)
            apply_patch_action_to_disk(action)
            self.assertEqual((root / "sub/in_sub.txt").read_text(encoding="utf-8"), "after\n")

    def test_apply_patch_cli_can_use_shell_command_output_as_patch_input(self) -> None:
        # Rust test: apply_patch_cli_can_use_shell_command_output_as_patch_input.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            patch = "*** Begin Patch\n*** Add File: stdout.txt\n+from stdout\n*** End Patch"
            action = _verified_action(root, patch)
            self.assertEqual(action.changes[root / "stdout.txt"].content, "from stdout\n")

    def test_apply_patch_custom_tool_streaming_emits_updated_changes(self) -> None:
        # Rust test: apply_patch_custom_tool_streaming_emits_updated_changes.
        parser = StreamingPatchParser()
        first = convert_apply_patch_hunks_to_protocol(
            parser.push_delta("*** Begin Patch\n*** Add File: streamed.txt\n")
        )
        second = convert_apply_patch_hunks_to_protocol(
            parser.push_delta("+hello\n+world\n*** End Patch")
        )
        self.assertIn(Path("streamed.txt"), first)
        self.assertEqual(first[Path("streamed.txt")].type, "add")
        self.assertEqual(first[Path("streamed.txt")].content, "")
        self.assertEqual(second[Path("streamed.txt")].type, "add")
        self.assertEqual(second[Path("streamed.txt")].content, "hello\nworld\n")

    def test_apply_patch_shell_command_heredoc_with_cd_emits_turn_diff(self) -> None:
        # Rust test: apply_patch_shell_command_heredoc_with_cd_emits_turn_diff.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "sub").mkdir()
            (root / "sub/in_sub.txt").write_text("before\n", encoding="utf-8")
            script = "cd sub && apply_patch <<'EOF'\n*** Begin Patch\n*** Update File: in_sub.txt\n@@\n-before\n+after\n*** End Patch\nEOF\n"
            action = maybe_parse_apply_patch_verified(("sh", "-c", script), root).body
            self.assertIsNotNone(action)
            diff = action.changes[root / "sub/in_sub.txt"].unified_diff
            self.assertIn("-before", diff)
            self.assertIn("+after", diff)

    def test_apply_patch_turn_diff_paths_stay_repo_relative_when_session_cwd_is_nested(self) -> None:
        # Rust test: apply_patch_turn_diff_paths_stay_repo_relative_when_session_cwd_is_nested.
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            nested = repo / "subdir"
            nested.mkdir()
            (repo / ".git").write_text("gitdir: /tmp/fake-worktree\n", encoding="utf-8")
            (repo / "repo.txt").write_text("before\n", encoding="utf-8")
            action = _verified_action(
                nested,
                "*** Begin Patch\n*** Update File: ../repo.txt\n@@\n-before\n+after\n*** End Patch",
            )
            path, change = next(iter(action.changes.items()))
            diff = change.unified_diff or ""
            self.assertEqual(path.resolve(), (repo / "repo.txt").resolve())
            self.assertIn("-before", diff)
            self.assertIn("+after", diff)
            self.assertNotIn(str(repo), diff)

    def test_apply_patch_shell_command_failure_propagates_error_and_skips_diff(self) -> None:
        # Rust test: apply_patch_shell_command_failure_propagates_error_and_skips_diff.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "invalid.txt").write_text("ok\n", encoding="utf-8")
            script = "apply_patch <<'EOF'\n*** Begin Patch\n*** Update File: invalid.txt\n@@\n-nope\n+changed\n*** End Patch\nEOF\n"
            result = maybe_parse_apply_patch_verified(("sh", "-c", script), root)
            self.assertNotEqual(result.type, "body")
            self.assertIn("Failed to find expected lines in", str(result.error))
            self.assertEqual((root / "invalid.txt").read_text(encoding="utf-8"), "ok\n")

    def test_apply_patch_shell_accepts_lenient_heredoc_wrapped_patch(self) -> None:
        # Rust test: apply_patch_shell_accepts_lenient_heredoc_wrapped_patch.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            script = "apply_patch <<'EOF'\n*** Begin Patch\n*** Add File: lenient.txt\n+lenient\n*** End Patch\nEOF\n"
            action = maybe_parse_apply_patch_verified(("sh", "-c", script), root).body
            self.assertIsNotNone(action)
            out = apply_patch_action_to_disk(action)
            self.assertIn("A ", out)
            self.assertEqual((root / "lenient.txt").read_text(encoding="utf-8"), "lenient\n")

    def test_apply_patch_cli_end_of_file_anchor(self) -> None:
        # Rust test: apply_patch_cli_end_of_file_anchor.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "tail.txt").write_text("alpha\nlast\n", encoding="utf-8")
            _apply(root, "*** Begin Patch\n*** Update File: tail.txt\n@@\n-last\n+end\n*** End of File\n*** End Patch")
            self.assertEqual((root / "tail.txt").read_text(encoding="utf-8"), "alpha\nend\n")

    def test_apply_patch_cli_missing_second_chunk_context_rejected(self) -> None:
        # Rust test: apply_patch_cli_missing_second_chunk_context_rejected.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "two_chunks.txt").write_text("a\nb\nc\nd\n", encoding="utf-8")
            error = _verification_error(
                root,
                "*** Begin Patch\n*** Update File: two_chunks.txt\n@@\n-b\n+B\n\n-d\n+D\n*** End Patch",
            )
            self.assertIn("Failed to find expected lines in", error)
            self.assertEqual((root / "two_chunks.txt").read_text(encoding="utf-8"), "a\nb\nc\nd\n")

    def test_apply_patch_emits_turn_diff_event_with_unified_diff(self) -> None:
        # Rust test: apply_patch_emits_turn_diff_event_with_unified_diff.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            action = _verified_action(root, "*** Begin Patch\n*** Add File: udiff.txt\n+hello\n*** End Patch\n")
            change = action.changes[root / "udiff.txt"]
            self.assertEqual(change.type, "add")
            self.assertEqual(change.content, "hello\n")

    def test_apply_patch_aggregates_diff_across_multiple_tool_calls(self) -> None:
        # Rust test: apply_patch_aggregates_diff_across_multiple_tool_calls.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _apply(root, "*** Begin Patch\n*** Add File: agg/a.txt\n+v1\n*** End Patch")
            action = _verified_action(
                root,
                "*** Begin Patch\n*** Update File: agg/a.txt\n@@\n-v1\n+v2\n*** Add File: agg/b.txt\n+B\n*** End Patch",
            )
            diff = "\n".join(change.unified_diff or change.content or "" for change in action.changes.values())
            self.assertIn("+v2", diff)
            self.assertIn("B\n", diff)

    def test_apply_patch_aggregates_diff_preserves_success_after_failure(self) -> None:
        # Rust test: apply_patch_aggregates_diff_preserves_success_after_failure.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _apply(root, "*** Begin Patch\n*** Add File: partial/success.txt\n+ok\n*** End Patch")
            error = _verification_error(
                root,
                "*** Begin Patch\n*** Update File: partial/success.txt\n@@\n-missing\n+new\n*** End Patch",
            )
            self.assertIn("Failed to find expected lines in", error)
            self.assertEqual((root / "partial/success.txt").read_text(encoding="utf-8"), "ok\n")

    def test_apply_patch_clears_aggregated_diff_after_inexact_delta(self) -> None:
        # Rust test: apply_patch_clears_aggregated_diff_after_inexact_delta.
        # Python parity scope: overwriting a non-text prior state yields no exact unified diff.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "binary.dat").write_bytes(b"\xff\xfe\xfd")
            action = _verified_action(root, "*** Begin Patch\n*** Add File: binary.dat\n+text\n*** End Patch")
            change = action.changes[root / "binary.dat"]
            self.assertEqual(change.content, "text\n")
            self.assertIsNone(change.overwritten_content)

    def test_apply_patch_change_context_disambiguates_target(self) -> None:
        # Rust test: apply_patch_change_context_disambiguates_target.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "multi_ctx.txt").write_text("fn a\nx=10\ny=2\nfn b\nx=10\ny=20\n", encoding="utf-8")
            _apply(
                root,
                "*** Begin Patch\n*** Update File: multi_ctx.txt\n@@ fn b\n-x=10\n+x=11\n*** End Patch",
            )
            self.assertEqual(
                (root / "multi_ctx.txt").read_text(encoding="utf-8"),
                "fn a\nx=10\ny=2\nfn b\nx=11\ny=20\n",
            )

