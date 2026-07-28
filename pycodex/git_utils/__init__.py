"""Rust-aligned public surface for ``codex-git-utils``."""

from pycodex.protocol import GitSha

from .apply import (
    ApplyGitRequest, ApplyGitResult, apply_git_patch, extract_paths_from_patch,
    parse_git_apply_output, stage_paths,
)
from .baseline import (
    GitBaselineChange, GitBaselineChangeStatus, GitBaselineDiff,
    diff_since_latest_init, ensure_git_baseline_repository, reset_git_repository,
)
from .branch import merge_base_with_head
from .errors import GitToolingError
from .info import (
    CommitLogEntry, GitDiffToRemote, GitInfo, canonicalize_git_remote_url,
    collect_git_info, current_branch_name, default_branch_name,
    get_git_remote_urls, get_git_remote_urls_assume_git_repo, get_git_repo_root,
    get_git_repo_root_with_fs, get_has_changes, get_head_commit_hash,
    git_diff_to_remote, local_git_branches, recent_commits,
    resolve_root_git_project_for_trust,
)
from .platform import create_symlink

__all__ = [
    "ApplyGitRequest", "ApplyGitResult", "CommitLogEntry",
    "GitBaselineChange", "GitBaselineChangeStatus", "GitBaselineDiff",
    "GitDiffToRemote", "GitInfo", "GitSha", "GitToolingError",
    "apply_git_patch", "canonicalize_git_remote_url", "collect_git_info",
    "create_symlink", "current_branch_name", "default_branch_name",
    "diff_since_latest_init", "ensure_git_baseline_repository",
    "extract_paths_from_patch", "get_git_remote_urls",
    "get_git_remote_urls_assume_git_repo", "get_git_repo_root",
    "get_git_repo_root_with_fs", "get_has_changes", "get_head_commit_hash",
    "git_diff_to_remote", "local_git_branches", "merge_base_with_head",
    "parse_git_apply_output", "recent_commits", "reset_git_repository",
    "resolve_root_git_project_for_trust", "stage_paths",
]
