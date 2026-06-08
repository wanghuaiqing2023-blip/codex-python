import unittest
from pathlib import Path

from pycodex.core.review_prompts import (
    ResolvedReviewRequest,
    render_review_prompt,
    resolve_review_request,
    review_prompt,
    user_facing_hint,
)
from pycodex.protocol import ReviewRequest, ReviewTarget


class ReviewPromptsTests(unittest.TestCase):
    def test_review_prompt_template_renders_base_branch_backup_variant(self) -> None:
        self.assertEqual(
            render_review_prompt(
                "Review {{branch}} against {{branch}}.",
                {"branch": "main"},
            ),
            "Review main against main.",
        )

    def test_review_prompt_template_renders_base_branch_variant(self) -> None:
        self.assertEqual(
            review_prompt(
                ReviewTarget.base_branch("main"),
                Path.cwd(),
                merge_base_with_head=lambda _cwd, branch: "abc123" if branch == "main" else None,
            ),
            "Review the code changes against the base branch 'main'. The merge base commit for this comparison is abc123. Run `git diff abc123` to inspect the changes relative to main. Provide prioritized, actionable findings.",
        )

    def test_review_prompt_template_renders_base_branch_backup_when_no_merge_base(self) -> None:
        self.assertEqual(
            review_prompt(
                ReviewTarget.base_branch("main"),
                Path.cwd(),
                merge_base_with_head=lambda _cwd, _branch: None,
            ),
            'Review the code changes against the base branch \'main\'. Start by finding the merge diff between the current branch and main\'s upstream e.g. (`git merge-base HEAD "$(git rev-parse --abbrev-ref "main@{upstream}")"`), then run `git diff` against that SHA to see what changes we would merge into the main branch. Provide prioritized, actionable findings.',
        )

    def test_review_prompt_template_renders_commit_variants(self) -> None:
        self.assertEqual(
            review_prompt(ReviewTarget.commit("deadbeef"), Path.cwd()),
            "Review the code changes introduced by commit deadbeef. Provide prioritized, actionable findings.",
        )
        self.assertEqual(
            review_prompt(ReviewTarget.commit("deadbeef", "Fix bug"), Path.cwd()),
            'Review the code changes introduced by commit deadbeef ("Fix bug"). Provide prioritized, actionable findings.',
        )

    def test_custom_review_prompt_trims_and_rejects_empty(self) -> None:
        self.assertEqual(review_prompt(ReviewTarget.custom("  inspect this  "), Path.cwd()), "inspect this")
        with self.assertRaises(ValueError):
            review_prompt(ReviewTarget.custom("   "), Path.cwd())

    def test_user_facing_hint_matches_rust_variants(self) -> None:
        self.assertEqual(user_facing_hint(ReviewTarget.uncommitted_changes()), "current changes")
        self.assertEqual(user_facing_hint(ReviewTarget.base_branch("main")), "changes against 'main'")
        self.assertEqual(user_facing_hint(ReviewTarget.commit("123456789", "Fix")), "commit 1234567: Fix")
        self.assertEqual(user_facing_hint(ReviewTarget.commit("123456789")), "commit 1234567")
        self.assertEqual(user_facing_hint(ReviewTarget.custom("  review this  ")), "review this")

    def test_resolve_review_request_preserves_user_supplied_hint(self) -> None:
        request = ReviewRequest(ReviewTarget.commit("abc123456"), user_facing_hint="custom hint")

        self.assertEqual(
            resolve_review_request(request, Path.cwd()),
            ResolvedReviewRequest(
                target=ReviewTarget.commit("abc123456"),
                prompt="Review the code changes introduced by commit abc123456. Provide prioritized, actionable findings.",
                user_facing_hint="custom hint",
            ),
        )

    def test_resolve_review_request_uses_default_hint_and_round_trips_to_request(self) -> None:
        # Rust: codex-core::review_prompts::resolve_review_request and
        # impl From<ResolvedReviewRequest> for ReviewRequest.
        resolved = resolve_review_request(ReviewRequest(ReviewTarget.base_branch("main")), Path.cwd())

        self.assertEqual(resolved.user_facing_hint, "changes against 'main'")
        self.assertEqual(resolved.to_review_request(), ReviewRequest(ReviewTarget.base_branch("main"), user_facing_hint="changes against 'main'"))


if __name__ == "__main__":
    unittest.main()
