import shutil
import unittest
import uuid
from pathlib import Path

from pycodex.apply_patch import (
    maybe_parse_apply_patch_verified,
)
from pycodex.core import (
    DEV_NULL,
    REGULAR_FILE_MODE,
    ZERO_OID,
    AppliedPatchChange,
    AppliedPatchDelta,
    AppliedPatchFileChange,
    TurnDiffTracker,
    git_blob_oid,
)


def workspace_tempdir() -> Path:
    root = Path.cwd() / "tmp_tests_workspace"
    root.mkdir(exist_ok=True)
    path = root / f"turn-diff-{uuid.uuid4()}"
    path.mkdir()
    return path


def change(path: Path, file_change: AppliedPatchFileChange) -> AppliedPatchChange:
    return AppliedPatchChange(path, file_change)


def delta(*changes: AppliedPatchChange, exact: bool = True) -> AppliedPatchDelta:
    return AppliedPatchDelta(tuple(changes), exact)


def blob_oid(content: str) -> str:
    return git_blob_oid(content.encode())


class CoreTurnDiffTrackerTests(unittest.TestCase):
    # Rust crate/module: codex-core::turn_diff_tracker.
    # Rust source: codex/codex-rs/core/src/turn_diff_tracker.rs.
    # Rust tests: codex/codex-rs/core/src/turn_diff_tracker_tests.rs.
    # These tests mirror the Rust module-scoped behavior contract for net turn
    # diffs from exact apply_patch deltas without rereading the workspace for
    # diff reconstruction.
    def setUp(self) -> None:
        self.root = workspace_tempdir()
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    def path(self, relative: str) -> Path:
        return self.root / relative

    def test_accumulates_add_then_update_as_single_add(self) -> None:
        # Rust test: accumulates_add_then_update_as_single_add.
        tracker = TurnDiffTracker.with_display_root(self.root)

        tracker.track_delta(delta(change(self.path("a.txt"), AppliedPatchFileChange.add("foo\n"))))
        tracker.track_delta(
            delta(
                change(
                    self.path("a.txt"),
                    AppliedPatchFileChange.update("foo\n", "foo\nbar\n"),
                )
            )
        )

        right_oid = blob_oid("foo\nbar\n")
        expected = (
            "diff --git a/a.txt b/a.txt\n"
            f"new file mode {REGULAR_FILE_MODE}\n"
            f"index {ZERO_OID}..{right_oid}\n"
            f"--- {DEV_NULL}\n"
            "+++ b/a.txt\n"
            "@@ -0,0 +1,2 @@\n"
            "+foo\n"
            "+bar\n"
        )
        self.assertEqual(tracker.get_unified_diff(), expected)

    def test_invalidated_tracker_suppresses_existing_diff(self) -> None:
        # Rust test: invalidated_tracker_suppresses_existing_diff.
        tracker = TurnDiffTracker.with_display_root(self.root)
        tracker.track_delta(delta(change(self.path("a.txt"), AppliedPatchFileChange.add("foo\n"))))

        tracker.invalidate()

        self.assertIsNone(tracker.get_unified_diff())

    def test_non_exact_delta_invalidates_tracker(self) -> None:
        # Rust source contract: TurnDiffTracker::track_delta invalidates on
        # non-exact AppliedPatchDelta.
        tracker = TurnDiffTracker.with_display_root(self.root)

        tracker.track_delta(delta(change(self.path("a.txt"), AppliedPatchFileChange.add("foo\n")), exact=False))

        self.assertIsNone(tracker.get_unified_diff())

    def test_accumulates_delete(self) -> None:
        # Rust test: accumulates_delete.
        tracker = TurnDiffTracker.with_display_root(self.root)

        tracker.track_delta(delta(change(self.path("b.txt"), AppliedPatchFileChange.delete("x\n"))))

        left_oid = blob_oid("x\n")
        expected = (
            "diff --git a/b.txt b/b.txt\n"
            f"deleted file mode {REGULAR_FILE_MODE}\n"
            f"index {left_oid}..{ZERO_OID}\n"
            "--- a/b.txt\n"
            f"+++ {DEV_NULL}\n"
            "@@ -1 +0,0 @@\n"
            "-x\n"
        )
        self.assertEqual(tracker.get_unified_diff(), expected)

    def test_accumulates_move_and_update(self) -> None:
        # Rust test: accumulates_move_and_update.
        tracker = TurnDiffTracker.with_display_root(self.root)

        tracker.track_delta(
            delta(
                change(
                    self.path("src.txt"),
                    AppliedPatchFileChange.update(
                        "line\n",
                        "line2\n",
                        move_path=self.path("dst.txt"),
                    ),
                )
            )
        )

        left_oid = blob_oid("line\n")
        right_oid = blob_oid("line2\n")
        expected = (
            "diff --git a/src.txt b/dst.txt\n"
            f"index {left_oid}..{right_oid}\n"
            "--- a/src.txt\n"
            "+++ b/dst.txt\n"
            "@@ -1 +1 @@\n"
            "-line\n"
            "+line2\n"
        )
        self.assertEqual(tracker.get_unified_diff(), expected)

    def test_pure_rename_yields_no_diff(self) -> None:
        # Rust test: pure_rename_yields_no_diff.
        tracker = TurnDiffTracker.with_display_root(self.root)

        tracker.track_delta(
            delta(
                change(
                    self.path("old.txt"),
                    AppliedPatchFileChange.update(
                        "same\n",
                        "same\n",
                        move_path=self.path("new.txt"),
                    ),
                )
            )
        )

        self.assertIsNone(tracker.get_unified_diff())

    def test_add_over_existing_file_becomes_update(self) -> None:
        # Rust test: add_over_existing_file_becomes_update.
        tracker = TurnDiffTracker.with_display_root(self.root)

        tracker.track_delta(
            delta(
                change(
                    self.path("dup.txt"),
                    AppliedPatchFileChange.add("after\n", overwritten_content="before\n"),
                )
            )
        )

        left_oid = blob_oid("before\n")
        right_oid = blob_oid("after\n")
        expected = (
            "diff --git a/dup.txt b/dup.txt\n"
            f"index {left_oid}..{right_oid}\n"
            "--- a/dup.txt\n"
            "+++ b/dup.txt\n"
            "@@ -1 +1 @@\n"
            "-before\n"
            "+after\n"
        )
        self.assertEqual(tracker.get_unified_diff(), expected)

    def test_delete_then_readd_same_path_becomes_update(self) -> None:
        # Rust test: delete_then_readd_same_path_becomes_update.
        tracker = TurnDiffTracker.with_display_root(self.root)

        tracker.track_delta(delta(change(self.path("cycle.txt"), AppliedPatchFileChange.delete("before\n"))))
        tracker.track_delta(delta(change(self.path("cycle.txt"), AppliedPatchFileChange.add("after\n"))))

        left_oid = blob_oid("before\n")
        right_oid = blob_oid("after\n")
        expected = (
            "diff --git a/cycle.txt b/cycle.txt\n"
            f"index {left_oid}..{right_oid}\n"
            "--- a/cycle.txt\n"
            "+++ b/cycle.txt\n"
            "@@ -1 +1 @@\n"
            "-before\n"
            "+after\n"
        )
        self.assertEqual(tracker.get_unified_diff(), expected)

    def test_move_over_existing_destination_without_content_change_deletes_source_only(self) -> None:
        # Rust test: move_over_existing_destination_without_content_change_deletes_source_only.
        tracker = TurnDiffTracker.with_display_root(self.root)

        tracker.track_delta(
            delta(
                change(
                    self.path("a.txt"),
                    AppliedPatchFileChange.update(
                        "same\n",
                        "same\n",
                        move_path=self.path("b.txt"),
                        overwritten_move_content="same\n",
                    ),
                )
            )
        )

        left_oid = blob_oid("same\n")
        expected = (
            "diff --git a/a.txt b/a.txt\n"
            f"deleted file mode {REGULAR_FILE_MODE}\n"
            f"index {left_oid}..{ZERO_OID}\n"
            "--- a/a.txt\n"
            f"+++ {DEV_NULL}\n"
            "@@ -1 +0,0 @@\n"
            "-same\n"
        )
        self.assertEqual(tracker.get_unified_diff(), expected)

    def test_move_over_existing_destination_with_content_change_deletes_source_and_updates_destination(self) -> None:
        # Rust test: move_over_existing_destination_with_content_change_deletes_source_and_updates_destination.
        tracker = TurnDiffTracker.with_display_root(self.root)

        tracker.track_delta(
            delta(
                change(
                    self.path("a.txt"),
                    AppliedPatchFileChange.update(
                        "from\n",
                        "new\n",
                        move_path=self.path("b.txt"),
                        overwritten_move_content="existing\n",
                    ),
                )
            )
        )

        left_oid_a = blob_oid("from\n")
        left_oid_b = blob_oid("existing\n")
        right_oid_b = blob_oid("new\n")
        expected = (
            "diff --git a/a.txt b/a.txt\n"
            f"deleted file mode {REGULAR_FILE_MODE}\n"
            f"index {left_oid_a}..{ZERO_OID}\n"
            "--- a/a.txt\n"
            f"+++ {DEV_NULL}\n"
            "@@ -1 +0,0 @@\n"
            "-from\n"
            "diff --git a/b.txt b/b.txt\n"
            f"index {left_oid_b}..{right_oid_b}\n"
            "--- a/b.txt\n"
            "+++ b/b.txt\n"
            "@@ -1 +1 @@\n"
            "-existing\n"
            "+new\n"
        )
        self.assertEqual(tracker.get_unified_diff(), expected)

    def test_preserves_committed_change_order_with_delete_then_move_overwrite(self) -> None:
        # Rust test: preserves_committed_change_order_with_delete_then_move_overwrite.
        tracker = TurnDiffTracker.with_display_root(self.root)

        tracker.track_delta(delta(change(self.path("b.txt"), AppliedPatchFileChange.delete("existing\n"))))
        tracker.track_delta(
            delta(
                change(
                    self.path("a.txt"),
                    AppliedPatchFileChange.update(
                        "from\n",
                        "new\n",
                        move_path=self.path("b.txt"),
                    ),
                )
            )
        )

        left_oid_a = blob_oid("from\n")
        left_oid_b = blob_oid("existing\n")
        right_oid_b = blob_oid("new\n")
        expected = (
            "diff --git a/a.txt b/a.txt\n"
            f"deleted file mode {REGULAR_FILE_MODE}\n"
            f"index {left_oid_a}..{ZERO_OID}\n"
            "--- a/a.txt\n"
            f"+++ {DEV_NULL}\n"
            "@@ -1 +0,0 @@\n"
            "-from\n"
            "diff --git a/b.txt b/b.txt\n"
            f"index {left_oid_b}..{right_oid_b}\n"
            "--- a/b.txt\n"
            "+++ b/b.txt\n"
            "@@ -1 +1 @@\n"
            "-existing\n"
            "+new\n"
        )
        self.assertEqual(tracker.get_unified_diff(), expected)

    def test_can_track_verified_apply_patch_action_without_rereading_for_diff(self) -> None:
        # Rust source contract: TurnDiffTracker tracks exact AppliedPatchDelta
        # content carried by apply_patch, so turn diff rendering does not need
        # to reread workspace files.
        (self.path("dup.txt")).write_text("before\n", encoding="utf-8")
        result = maybe_parse_apply_patch_verified(
            (
                "apply_patch",
                "*** Begin Patch\n*** Add File: dup.txt\n+after\n*** End Patch",
            ),
            self.root,
        )
        self.assertEqual(result.type, "body")
        self.assertIsNotNone(result.body)
        tracker = TurnDiffTracker.with_display_root(self.root)

        tracker.track_action(result.body)

        self.assertIn("--- a/dup.txt\n+++ b/dup.txt\n", tracker.get_unified_diff())
        self.assertIn("-before\n+after\n", tracker.get_unified_diff())


if __name__ == "__main__":
    unittest.main()
