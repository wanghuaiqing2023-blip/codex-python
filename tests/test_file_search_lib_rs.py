"""Parity tests for Rust ``codex-file-search/src/lib.rs``.

These tests are intentionally not part of a full crate validation run until
``src/cli.rs`` and ``src/main.rs`` are ported.
"""

from pathlib import Path
from threading import Event

from pycodex.file_search import (
    FileSearchOptions,
    FileSearchSnapshot,
    MatchType,
    create_session,
    file_name_from_path,
    run,
    sort_matches,
)


def test_tie_breakers_sort_by_path_when_scores_equal() -> None:
    """Rust: tie_breakers_sort_by_path_when_scores_equal."""

    matches = [(100, "b_path"), (100, "a_path"), (90, "zzz")]
    sort_matches(matches)
    assert matches == [(100, "a_path"), (100, "b_path"), (90, "zzz")]


def test_file_name_from_path_uses_basename() -> None:
    """Rust: file_name_from_path_uses_basename."""

    assert file_name_from_path("foo/bar.txt") == "bar.txt"


def test_file_name_from_path_falls_back_to_full_path() -> None:
    """Rust: file_name_from_path_falls_back_to_full_path."""

    assert file_name_from_path("") == ""


def test_run_returns_matches_for_query(tmp_path: Path) -> None:
    """Rust: run_returns_matches_for_query."""

    for index in range(40):
        (tmp_path / f"file-{index:04}.txt").write_text(f"contents {index}", encoding="utf-8")

    results = run("file-000", [tmp_path], FileSearchOptions(limit=20, threads=2))

    assert results.matches
    assert results.total_match_count >= len(results.matches)
    assert any("file-0000.txt" in match.path.as_posix() for match in results.matches)


def test_run_returns_directory_matches_for_query(tmp_path: Path) -> None:
    """Rust: run_returns_directory_matches_for_query."""

    (tmp_path / "docs" / "guides").mkdir(parents=True)
    (tmp_path / "docs" / "guides" / "intro.md").write_text("intro", encoding="utf-8")
    (tmp_path / "docs" / "readme.md").write_text("readme", encoding="utf-8")

    results = run("guides", [tmp_path], FileSearchOptions(limit=20, threads=2))

    assert any(match.path == Path("docs/guides") and match.match_type is MatchType.DIRECTORY for match in results.matches)


def test_cancel_exits_run(tmp_path: Path) -> None:
    """Rust: cancel_exits_run."""

    for index in range(200):
        (tmp_path / f"file-{index:04}.txt").write_text(f"contents {index}", encoding="utf-8")
    cancel_flag = Event()
    cancel_flag.set()

    results = run("file-", [tmp_path], FileSearchOptions(), cancel_flag)

    assert results.matches == []
    assert results.total_match_count == 0


class RecordingReporter:
    def __init__(self) -> None:
        self.updates: list[FileSearchSnapshot] = []
        self.completed = False

    def on_update(self, snapshot: FileSearchSnapshot) -> None:
        self.updates.append(snapshot)

    def on_complete(self) -> None:
        self.completed = True


def test_session_accepts_query_updates_after_walk_complete(tmp_path: Path) -> None:
    """Rust: session_accepts_query_updates_after_walk_complete."""

    (tmp_path / "alpha.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "beta.txt").write_text("beta", encoding="utf-8")
    reporter = RecordingReporter()
    session = create_session([tmp_path], FileSearchOptions(), reporter)

    session.update_query("alpha")
    updates_before = len(reporter.updates)
    session.update_query("beta")

    assert len(reporter.updates) >= updates_before + 1
    assert any("beta.txt" in match.path.as_posix() for match in reporter.updates[-1].matches)


def test_gitignore_outside_repo_does_not_hide_repo_files(tmp_path: Path) -> None:
    """Rust: parent_gitignore_outside_repo_does_not_hide_repo_files."""

    parent = tmp_path / "home"
    repo = parent / "repo"
    (repo / ".vscode").mkdir(parents=True)
    (parent / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    (repo / ".gitignore").write_text(".vscode/*\n!.vscode/\n!.vscode/settings.json\n!package.json\n", encoding="utf-8")
    (repo / "package.json").write_text('{ "name": "demo" }\n', encoding="utf-8")
    (repo / ".vscode" / "settings.json").write_text('{ "editor": true }\n', encoding="utf-8")

    package_results = run("package", [repo], FileSearchOptions(respect_gitignore=True))
    settings_results = run("settings", [repo], FileSearchOptions(respect_gitignore=True))

    assert any(match.path == Path("package.json") for match in package_results.matches)
    assert any(match.path == Path(".vscode/settings.json") for match in settings_results.matches)


def test_git_repo_still_respects_local_gitignore_when_enabled(tmp_path: Path) -> None:
    """Rust: git_repo_still_respects_local_gitignore_when_enabled."""

    repo = tmp_path / "home" / "repo"
    (repo / ".vscode").mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / ".gitignore").write_text(".vscode/*\n!.vscode/\n!.vscode/settings.json\n!package.json\n", encoding="utf-8")
    (repo / "package.json").write_text('{ "name": "demo" }\n', encoding="utf-8")
    (repo / ".vscode" / "settings.json").write_text('{ "editor": true }\n', encoding="utf-8")
    (repo / ".vscode" / "extensions.json").write_text('{ "extensions": [] }\n', encoding="utf-8")

    package_results = run("package", [repo], FileSearchOptions(respect_gitignore=True))
    ignored_results = run("extensions.json", [repo], FileSearchOptions(respect_gitignore=True))
    whitelisted_results = run("settings.json", [repo], FileSearchOptions(respect_gitignore=True))

    assert any(match.path == Path("package.json") for match in package_results.matches)
    assert not any(match.path == Path(".vscode/extensions.json") for match in ignored_results.matches)
    assert any(match.path == Path(".vscode/settings.json") for match in whitelisted_results.matches)

