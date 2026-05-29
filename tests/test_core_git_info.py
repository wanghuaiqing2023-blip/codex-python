import shutil
import subprocess
import unittest
import uuid
from pathlib import Path

from pycodex.core import (
    CommitLogEntry,
    GitDiffToRemote,
    canonicalize_git_remote_url,
    collect_git_info,
    current_branch_name,
    get_git_remote_urls,
    get_git_repo_root,
    get_has_changes,
    git_diff_to_remote,
    local_git_branches,
    parse_git_remote_urls,
    recent_commits,
    resolve_root_git_project_for_trust,
)
from pycodex.protocol import GitSha


def workspace_tempdir() -> Path:
    root = Path.cwd() / "tmp_tests_workspace"
    root.mkdir(exist_ok=True)
    path = root / f"git-info-{uuid.uuid4()}"
    path.mkdir()
    return path


def run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


class CoreGitInfoTests(unittest.TestCase):
    def make_repo(self) -> Path:
        root = workspace_tempdir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        repo = root / "repo"
        repo.mkdir()
        run_git(repo, "init")
        run_git(repo, "config", "user.name", "Test User")
        run_git(repo, "config", "user.email", "test@example.com")
        run_git(repo, "config", "core.autocrlf", "false")
        run_git(repo, "config", "protocol.file.allow", "always")
        (repo / "test.txt").write_text("test content\n", encoding="utf-8")
        run_git(repo, "add", "test.txt")
        run_git(repo, "commit", "-m", "Initial commit")
        return repo

    def make_repo_with_remote(self) -> tuple[Path, Path, str]:
        repo = self.make_repo()
        remote = repo.parent / "remote.git"
        run_git(repo.parent, "init", "--bare", str(remote))
        run_git(repo, "remote", "add", "origin", str(remote))
        branch = run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        run_git(repo, "update-ref", f"refs/remotes/origin/{branch}", "HEAD")
        return repo, remote, branch

    def test_canonicalize_git_remote_url_matches_upstream_cases(self):
        for remote in [
            "git@github.com:OpenAI/Codex.git",
            "ssh://git@github.com/openai/codex.git",
            "ssh://git@github.com:22/OpenAI/Codex.git",
            "https://github.com/openai/codex.git",
            "https://github.com:443/openai/codex.git",
            "https://token@github.com/openai/codex/",
            "github.com/OpenAI/Codex.git",
        ]:
            self.assertEqual(canonicalize_git_remote_url(remote), "github.com/openai/codex")

        self.assertEqual(
            canonicalize_git_remote_url("git@ghe.company.com:Org/Repo.git"),
            "ghe.company.com/Org/Repo",
        )
        self.assertEqual(
            canonicalize_git_remote_url("ssh://git@ghe.company.com:2222/Org/Repo.git"),
            "ghe.company.com:2222/Org/Repo",
        )
        self.assertIsNone(canonicalize_git_remote_url("file:///tmp/repo"))
        with self.assertRaisesRegex(TypeError, "url must be a string"):
            canonicalize_git_remote_url(123)  # type: ignore[arg-type]

    def test_parse_git_remote_urls_only_keeps_fetch_entries(self):
        self.assertEqual(
            parse_git_remote_urls(
                "origin\thttps://example.test/repo.git (fetch)\n"
                "origin\thttps://example.test/repo.git (push)\n"
                "upstream git@example.test:Org/Repo.git (fetch)\n"
            ),
            {"origin": "https://example.test/repo.git", "upstream": "git@example.test:Org/Repo.git"},
        )
        with self.assertRaisesRegex(TypeError, "stdout must be a string"):
            parse_git_remote_urls(b"origin\turl (fetch)")  # type: ignore[arg-type]

    def test_collect_git_info_for_repo_remote_and_detached_head(self):
        repo = self.make_repo()

        info = collect_git_info(repo)

        self.assertIsNotNone(info)
        self.assertIsNotNone(info.commit_hash)
        self.assertEqual(len(info.commit_hash.to_json()), 40)
        self.assertIn(info.branch, {"main", "master"})
        self.assertIsNone(info.repository_url)
        self.assertEqual(get_git_repo_root(repo / "subdir" / "file.txt"), repo)

        run_git(repo, "remote", "add", "origin", "https://github.com/example/repo.git")
        expected_remote = run_git(repo, "remote", "get-url", "origin").stdout.strip()
        self.assertEqual(collect_git_info(repo).repository_url, expected_remote)
        self.assertEqual(get_git_remote_urls(repo), {"origin": expected_remote})

        commit_hash = run_git(repo, "rev-parse", "HEAD").stdout.strip()
        run_git(repo, "checkout", commit_hash)
        detached = collect_git_info(repo)
        self.assertIsNotNone(detached.commit_hash)
        self.assertIsNone(detached.branch)

    def test_branch_helpers_and_recent_commits(self):
        repo = self.make_repo()
        run_git(repo, "checkout", "-b", "feature-branch")
        (repo / "file.txt").write_text("one\n", encoding="utf-8")
        run_git(repo, "add", "file.txt")
        run_git(repo, "commit", "-m", "first change")
        (repo / "file.txt").write_text("two\n", encoding="utf-8")
        run_git(repo, "add", "file.txt")
        run_git(repo, "commit", "-m", "second change")

        self.assertEqual(current_branch_name(repo), "feature-branch")
        self.assertIn("feature-branch", local_git_branches(repo))
        entries = recent_commits(repo, 2)
        self.assertEqual([entry.subject for entry in entries], ["second change", "first change"])
        self.assertTrue(all(entry.sha and entry.timestamp for entry in entries))
        with self.assertRaisesRegex(ValueError, "limit must be non-negative"):
            recent_commits(repo, -1)
        with self.assertRaisesRegex(TypeError, "limit must be an integer"):
            recent_commits(repo, True)  # type: ignore[arg-type]

    def test_get_has_changes(self):
        repo = self.make_repo()

        self.assertEqual(get_has_changes(repo), False)
        (repo / "test.txt").write_text("updated\n", encoding="utf-8")
        self.assertEqual(get_has_changes(repo), True)
        run_git(repo, "checkout", "--", "test.txt")
        (repo / "new_file.txt").write_text("untracked\n", encoding="utf-8")
        self.assertEqual(get_has_changes(repo), True)
        self.assertIsNone(get_has_changes(repo / "missing"))

    def test_git_diff_to_remote_includes_tracked_and_untracked_changes(self):
        repo, _remote, branch = self.make_repo_with_remote()
        remote_sha = run_git(repo, "rev-parse", f"origin/{branch}").stdout.strip()

        (repo / "test.txt").write_text("modified\n", encoding="utf-8")
        (repo / "untracked.txt").write_text("new\n", encoding="utf-8")

        state = git_diff_to_remote(repo)

        self.assertIsNotNone(state)
        self.assertEqual(state.sha.to_json(), remote_sha)
        self.assertIn("test.txt", state.diff)
        self.assertIn("untracked.txt", state.diff)

    def test_resolve_root_git_project_for_trust_handles_worktree_pointer(self):
        root = workspace_tempdir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        repo = root / "repo"
        worktree = root / "worktree"
        worktree_git_dir = repo / ".git" / "worktrees" / "feature-x"
        worktree_git_dir.mkdir(parents=True)
        worktree.mkdir()
        (worktree / ".git").write_text(f"gitdir: {worktree_git_dir}\n", encoding="utf-8")

        self.assertEqual(resolve_root_git_project_for_trust(worktree), repo)
        self.assertEqual(resolve_root_git_project_for_trust(repo), repo)

    def test_git_info_dataclasses_reject_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "timestamp must be an integer"):
            CommitLogEntry("abc", True, "subject")  # type: ignore[arg-type]

        with self.assertRaisesRegex(TypeError, "sha must be a GitSha"):
            GitDiffToRemote("abc", "diff")  # type: ignore[arg-type]

        self.assertEqual(GitDiffToRemote(GitSha.new("a" * 40), "diff").diff, "diff")


if __name__ == "__main__":
    unittest.main()
