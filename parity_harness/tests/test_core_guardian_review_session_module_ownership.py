"""Rust-derived ownership checks for ``core::guardian::review_session``."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _defined_items(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


class CoreGuardianReviewSessionModuleOwnershipTests(unittest.TestCase):
    def test_review_session_owns_the_rust_production_items(self) -> None:
        owner = REPO_ROOT / "pycodex/core/guardian/review_session.py"
        expected = {
            "GuardianReviewSessionOutcome",
            "GuardianReviewSessionParams",
            "GuardianReviewSessionManager",
            "GuardianReviewSession",
            "GuardianReviewState",
            "GuardianReviewForkSnapshot",
            "GuardianReviewSessionReuseKey",
            "had_prior_review_context",
            "token_usage_delta",
            "prompt_cache_key_override_for_review_session",
            "spawn_guardian_review_session",
            "run_review_on_session",
            "append_guardian_followup_reminder",
            "load_rollout_items_for_fork",
            "wait_for_guardian_review",
            "event_matches_turn",
            "build_guardian_review_session_config",
            "run_before_review_deadline",
            "run_before_review_deadline_with_cancel",
            "interrupt_and_drain_turn",
        }

        self.assertTrue(owner.is_file(), f"missing Python owner {owner}")
        self.assertTrue(expected.issubset(_defined_items(owner)))


if __name__ == "__main__":
    unittest.main()
