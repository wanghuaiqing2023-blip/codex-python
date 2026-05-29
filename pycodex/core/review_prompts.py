"""Review request prompt helpers.

Ported from ``codex/codex-rs/core/src/review_prompts.rs``. The Rust module
uses git to resolve a base-branch merge base; this stdlib slice keeps that as
an injectable boundary so the prompt rendering semantics remain pure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pycodex.protocol import ReviewRequest, ReviewTarget


UNCOMMITTED_PROMPT = "Review the current code changes (staged, unstaged, and untracked files) and provide prioritized findings."
BASE_BRANCH_PROMPT_BACKUP = 'Review the code changes against the base branch \'{{branch}}\'. Start by finding the merge diff between the current branch and {{branch}}\'s upstream e.g. (`git merge-base HEAD "$(git rev-parse --abbrev-ref "{{branch}}@{upstream}")"`), then run `git diff` against that SHA to see what changes we would merge into the {{branch}} branch. Provide prioritized, actionable findings.'
BASE_BRANCH_PROMPT = "Review the code changes against the base branch '{{base_branch}}'. The merge base commit for this comparison is {{merge_base_sha}}. Run `git diff {{merge_base_sha}}` to inspect the changes relative to {{base_branch}}. Provide prioritized, actionable findings."
COMMIT_PROMPT_WITH_TITLE = 'Review the code changes introduced by commit {{sha}} ("{{title}}"). Provide prioritized, actionable findings.'
COMMIT_PROMPT = "Review the code changes introduced by commit {{sha}}. Provide prioritized, actionable findings."

MergeBaseResolver = Callable[[Path, str], str | None]


@dataclass(frozen=True)
class ResolvedReviewRequest:
    target: ReviewTarget
    prompt: str
    user_facing_hint: str

    def __post_init__(self) -> None:
        if not isinstance(self.target, ReviewTarget):
            raise TypeError("target must be a ReviewTarget")
        if not isinstance(self.prompt, str):
            raise TypeError("prompt must be a string")
        if not isinstance(self.user_facing_hint, str):
            raise TypeError("user_facing_hint must be a string")

    def to_review_request(self) -> ReviewRequest:
        return ReviewRequest(target=self.target, user_facing_hint=self.user_facing_hint)


def resolve_review_request(
    request: ReviewRequest,
    cwd: str | Path,
    *,
    merge_base_with_head: MergeBaseResolver | None = None,
) -> ResolvedReviewRequest:
    if not isinstance(request, ReviewRequest):
        raise TypeError("request must be a ReviewRequest")
    target = request.target
    prompt = review_prompt(target, cwd, merge_base_with_head=merge_base_with_head)
    hint = request.user_facing_hint if request.user_facing_hint is not None else user_facing_hint(target)
    return ResolvedReviewRequest(target=target, prompt=prompt, user_facing_hint=hint)


def review_prompt(
    target: ReviewTarget,
    cwd: str | Path,
    *,
    merge_base_with_head: MergeBaseResolver | None = None,
) -> str:
    if not isinstance(target, ReviewTarget):
        raise TypeError("target must be a ReviewTarget")
    cwd_path = Path(cwd)
    if target.type == "uncommittedChanges":
        return UNCOMMITTED_PROMPT
    if target.type == "baseBranch":
        branch = _required_target_string(target.branch, "branch")
        merge_base = merge_base_with_head(cwd_path, branch) if merge_base_with_head is not None else None
        if merge_base is not None:
            if not isinstance(merge_base, str):
                raise TypeError("merge_base_with_head must return a string or None")
            return render_review_prompt(
                BASE_BRANCH_PROMPT,
                {"base_branch": branch, "merge_base_sha": merge_base},
            )
        return render_review_prompt(BASE_BRANCH_PROMPT_BACKUP, {"branch": branch})
    if target.type == "commit":
        sha = _required_target_string(target.sha, "sha")
        if target.title is not None:
            if not isinstance(target.title, str):
                raise TypeError("title must be a string or None")
            return render_review_prompt(COMMIT_PROMPT_WITH_TITLE, {"sha": sha, "title": target.title})
        return render_review_prompt(COMMIT_PROMPT, {"sha": sha})
    if target.type == "custom":
        instructions = _required_target_string(target.instructions, "instructions").strip()
        if not instructions:
            raise ValueError("Review prompt cannot be empty")
        return instructions
    raise ValueError(f"unknown review target type: {target.type}")


def render_review_prompt(template: str, variables: dict[str, str]) -> str:
    if not isinstance(template, str):
        raise TypeError("template must be a string")
    if not isinstance(variables, dict):
        raise TypeError("variables must be a dict")
    rendered = template
    for key, value in variables.items():
        if not isinstance(key, str):
            raise TypeError("template variable names must be strings")
        if not isinstance(value, str):
            raise TypeError("template variable values must be strings")
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def user_facing_hint(target: ReviewTarget) -> str:
    if not isinstance(target, ReviewTarget):
        raise TypeError("target must be a ReviewTarget")
    if target.type == "uncommittedChanges":
        return "current changes"
    if target.type == "baseBranch":
        branch = _required_target_string(target.branch, "branch")
        return f"changes against '{branch}'"
    if target.type == "commit":
        sha = _required_target_string(target.sha, "sha")
        short_sha = sha[:7]
        if target.title is not None:
            if not isinstance(target.title, str):
                raise TypeError("title must be a string or None")
            return f"commit {short_sha}: {target.title}"
        return f"commit {short_sha}"
    if target.type == "custom":
        return _required_target_string(target.instructions, "instructions").strip()
    raise ValueError(f"unknown review target type: {target.type}")


def _required_target_string(value: str | None, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


__all__ = [
    "BASE_BRANCH_PROMPT",
    "BASE_BRANCH_PROMPT_BACKUP",
    "COMMIT_PROMPT",
    "COMMIT_PROMPT_WITH_TITLE",
    "UNCOMMITTED_PROMPT",
    "MergeBaseResolver",
    "ResolvedReviewRequest",
    "render_review_prompt",
    "resolve_review_request",
    "review_prompt",
    "user_facing_hint",
]
