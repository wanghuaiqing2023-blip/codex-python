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
from pycodex.git_utils import (
    ApplyGitRequest,
    apply_git_patch,
    extract_paths_from_patch,
    merge_base_with_head,
    parse_git_apply_output,
)


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

    # Source: rust_test_migrated
    # Rust crate: codex-git-utils
    # Rust module: src/info.rs
    # Rust tests: tests::canonicalize_git_remote_url_normalizes_github_variants; tests::canonicalize_git_remote_url_handles_ghe_without_lowercasing_path; tests::canonicalize_git_remote_url_rejects_non_repository_values
    # Contract: git_utils.info.canonicalize_git_remote_url
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
        for remote in ["", "file:///tmp/repo", "github.com/openai", "/tmp/repo"]:
            with self.subTest(remote=remote):
                self.assertIsNone(canonicalize_git_remote_url(remote))
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

    # Source: rust_test_migrated
    # Rust crate: codex-git-utils
    # Rust module: src/branch.rs
    # Rust test: tests::merge_base_returns_shared_commit
    # Contract: git_utils.branch.merge_base_with_head
    def test_merge_base_returns_shared_commit(self):
        repo = self.make_repo()
        base_branch = current_branch_name(repo)
        self.assertIsNotNone(base_branch)

        run_git(repo, "checkout", "-b", "feature")
        (repo / "feature.txt").write_text("feature change\n", encoding="utf-8")
        run_git(repo, "add", "feature.txt")
        run_git(repo, "commit", "-m", "feature commit")

        run_git(repo, "checkout", base_branch)
        (repo / "main.txt").write_text("main change\n", encoding="utf-8")
        run_git(repo, "add", "main.txt")
        run_git(repo, "commit", "-m", "main commit")

        run_git(repo, "checkout", "feature")
        expected = run_git(repo, "merge-base", "HEAD", base_branch).stdout.strip()
        self.assertEqual(merge_base_with_head(repo, base_branch), expected)

    # Source: rust_test_migrated
    # Rust crate: codex-git-utils
    # Rust module: src/branch.rs
    # Rust test: tests::merge_base_prefers_upstream_when_remote_ahead
    # Contract: git_utils.branch.merge_base_with_head
    def test_merge_base_prefers_upstream_when_remote_ahead(self):
        repo = self.make_repo()
        remote = repo.parent / "remote.git"
        run_git(repo.parent, "init", "--bare", str(remote))
        base_branch = current_branch_name(repo)
        self.assertIsNotNone(base_branch)
        run_git(repo, "remote", "add", "origin", str(remote))
        run_git(repo, "push", "-u", "origin", base_branch)

        run_git(repo, "checkout", "-b", "feature")
        (repo / "feature.txt").write_text("feature change\n", encoding="utf-8")
        run_git(repo, "add", "feature.txt")
        run_git(repo, "commit", "-m", "feature commit")

        run_git(repo, "checkout", base_branch)
        (repo / "remote-ahead.txt").write_text("remote ahead\n", encoding="utf-8")
        run_git(repo, "add", "remote-ahead.txt")
        run_git(repo, "commit", "-m", "remote ahead commit")
        run_git(repo, "push", "origin", base_branch)

        run_git(repo, "reset", "--hard", f"origin/{base_branch}~1")
        run_git(repo, "branch", "--set-upstream-to", f"origin/{base_branch}", base_branch)
        run_git(repo, "checkout", "feature")
        run_git(repo, "fetch", "origin")

        expected = run_git(repo, "merge-base", "HEAD", f"origin/{base_branch}").stdout.strip()
        self.assertEqual(merge_base_with_head(repo, base_branch), expected)

    # Source: rust_test_migrated
    # Rust crate: codex-git-utils
    # Rust module: src/branch.rs
    # Rust test: tests::merge_base_returns_none_when_branch_missing
    # Contract: git_utils.branch.merge_base_with_head
    def test_merge_base_returns_none_when_branch_missing(self):
        repo = self.make_repo()
        self.assertIsNone(merge_base_with_head(repo, "missing-branch"))

    # Source: rust_test_migrated
    # Rust crate: codex-git-utils
    # Rust module: src/apply.rs
    # Rust tests: tests::extract_paths_handles_quoted_headers; tests::extract_paths_ignores_dev_null_header; tests::extract_paths_unescapes_c_style_in_quoted_headers
    # Contract: git_utils.apply.extract_paths_from_patch
    def test_extract_paths_from_patch_matches_rust_header_cases(self):
        cases = [
            (
                'diff --git "a/hello world.txt" "b/hello world.txt"\n'
                "new file mode 100644\n"
                "--- /dev/null\n"
                "+++ b/hello world.txt\n"
                "@@ -0,0 +1 @@\n"
                "+hi\n",
                ["hello world.txt"],
            ),
            (
                "diff --git a/dev/null b/ok.txt\n"
                "new file mode 100644\n"
                "--- /dev/null\n"
                "+++ b/ok.txt\n"
                "@@ -0,0 +1 @@\n"
                "+hi\n",
                ["ok.txt"],
            ),
            (
                'diff --git "a/hello\\tworld.txt" "b/hello\\tworld.txt"\n'
                "new file mode 100644\n"
                "--- /dev/null\n"
                "+++ b/hello\tworld.txt\n"
                "@@ -0,0 +1 @@\n"
                "+hi\n",
                ["hello\tworld.txt"],
            ),
        ]
        for diff, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(extract_paths_from_patch(diff), expected)

    # Source: rust_test_migrated
    # Rust crate: codex-git-utils
    # Rust module: src/apply.rs
    # Rust test: tests::parse_output_unescapes_quoted_paths
    # Contract: git_utils.apply.parse_git_apply_output
    def test_parse_git_apply_output_unescapes_quoted_paths(self):
        applied, skipped, conflicted = parse_git_apply_output(
            "",
            'error: patch failed: "hello\\tworld.txt":1\n',
        )
        self.assertEqual(applied, [])
        self.assertEqual(conflicted, [])
        self.assertEqual(skipped, ["hello\tworld.txt"])

    # Source: rust_test_migrated
    # Rust crate: codex-git-utils
    # Rust module: src/apply.rs
    # Rust test: tests::apply_add_success
    # Contract: git_utils.apply.apply_git_patch
    def test_apply_git_patch_add_success(self):
        repo = self.make_repo()
        diff = (
            "diff --git a/hello.txt b/hello.txt\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/hello.txt\n"
            "@@ -0,0 +1,2 @@\n"
            "+hello\n"
            "+world\n"
        )
        result = apply_git_patch(ApplyGitRequest(repo, diff, revert=False, preflight=False))
        self.assertEqual(result.exit_code, 0)
        self.assertTrue((repo / "hello.txt").exists())

    # Source: rust_test_migrated
    # Rust crate: codex-git-utils
    # Rust module: src/apply.rs
    # Rust tests: tests::apply_modify_conflict; tests::apply_modify_skipped_missing_index
    # Contract: git_utils.apply.apply_git_patch
    def test_apply_git_patch_reports_conflict_and_missing_index_failures(self):
        repo = self.make_repo()
        (repo / "file.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")
        run_git(repo, "add", "file.txt")
        run_git(repo, "commit", "-m", "seed")
        (repo / "file.txt").write_text("line1\nlocal2\nline3\n", encoding="utf-8")
        conflict_diff = (
            "diff --git a/file.txt b/file.txt\n"
            "--- a/file.txt\n"
            "+++ b/file.txt\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-line2\n"
            "+remote2\n"
            " line3\n"
        )
        conflict = apply_git_patch(ApplyGitRequest(repo, conflict_diff, revert=False, preflight=False))
        self.assertNotEqual(conflict.exit_code, 0)

        missing_diff = (
            "diff --git a/ghost.txt b/ghost.txt\n"
            "--- a/ghost.txt\n"
            "+++ b/ghost.txt\n"
            "@@ -1,1 +1,1 @@\n"
            "-old\n"
            "+new\n"
        )
        missing = apply_git_patch(ApplyGitRequest(repo, missing_diff, revert=False, preflight=False))
        self.assertNotEqual(missing.exit_code, 0)

    # Source: rust_test_migrated
    # Rust crate: codex-git-utils
    # Rust module: src/apply.rs
    # Rust tests: tests::apply_then_revert_success; tests::revert_preflight_does_not_stage_index
    # Contract: git_utils.apply.apply_git_patch
    def test_apply_git_patch_revert_and_revert_preflight(self):
        repo = self.make_repo()
        (repo / "file.txt").write_text("orig\n", encoding="utf-8")
        run_git(repo, "add", "file.txt")
        run_git(repo, "commit", "-m", "seed")
        diff = (
            "diff --git a/file.txt b/file.txt\n"
            "--- a/file.txt\n"
            "+++ b/file.txt\n"
            "@@ -1,1 +1,1 @@\n"
            "-orig\n"
            "+ORIG\n"
        )
        applied = apply_git_patch(ApplyGitRequest(repo, diff, revert=False, preflight=False))
        self.assertEqual(applied.exit_code, 0)
        self.assertEqual((repo / "file.txt").read_text(encoding="utf-8").replace("\r\n", "\n"), "ORIG\n")

        run_git(repo, "add", "file.txt")
        run_git(repo, "commit", "-m", "apply change")
        staged_before = run_git(repo, "diff", "--cached", "--name-only").stdout.strip()
        preflight = apply_git_patch(ApplyGitRequest(repo, diff, revert=True, preflight=True))
        self.assertEqual(preflight.exit_code, 0)
        staged_after = run_git(repo, "diff", "--cached", "--name-only").stdout.strip()
        self.assertEqual(staged_after, staged_before)
        self.assertEqual((repo / "file.txt").read_text(encoding="utf-8").replace("\r\n", "\n"), "ORIG\n")

        reverted = apply_git_patch(ApplyGitRequest(repo, diff, revert=True, preflight=False))
        self.assertEqual(reverted.exit_code, 0)
        self.assertEqual((repo / "file.txt").read_text(encoding="utf-8").replace("\r\n", "\n"), "orig\n")

    # Source: rust_test_migrated
    # Rust crate: codex-git-utils
    # Rust module: src/apply.rs
    # Rust test: tests::preflight_blocks_partial_changes
    # Contract: git_utils.apply.apply_git_patch
    def test_apply_git_patch_preflight_blocks_partial_changes(self):
        repo = self.make_repo()
        diff = (
            "diff --git a/ok.txt b/ok.txt\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/ok.txt\n"
            "@@ -0,0 +1,2 @@\n"
            "+alpha\n"
            "+beta\n"
            "\n"
            "diff --git a/ghost.txt b/ghost.txt\n"
            "--- a/ghost.txt\n"
            "+++ b/ghost.txt\n"
            "@@ -1,1 +1,1 @@\n"
            "-old\n"
            "+new\n"
        )
        preflight = apply_git_patch(ApplyGitRequest(repo, diff, revert=False, preflight=True))
        self.assertNotEqual(preflight.exit_code, 0)
        self.assertFalse((repo / "ok.txt").exists())
        self.assertIn("--check", preflight.cmd_for_log)

        direct = apply_git_patch(ApplyGitRequest(repo, diff, revert=False, preflight=False))
        self.assertNotEqual(direct.exit_code, 0)
        self.assertNotIn("--check", direct.cmd_for_log)

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
