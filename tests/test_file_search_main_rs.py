"""Parity tests for Rust ``codex-file-search/src/main.rs``."""

from __future__ import annotations

import io
import json
from pathlib import Path

from pycodex.file_search import FileMatch, FileSearchOptions, FileSearchResults, MatchType
from pycodex.file_search.cli import Cli
from pycodex.file_search.main import StdioReporter, main, run_cli


class TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_stdio_reporter_json_matches_rust_json_lines(tmp_path: Path) -> None:
    # Rust source: StdioReporter::report_match serializes FileMatch as JSON.
    stdout = io.StringIO()
    reporter = StdioReporter(write_output_as_json=True, show_indices=False, stdout=stdout, stderr=io.StringIO())

    reporter.report_match(
        FileMatch(
            score=42,
            path=Path("src/main.rs"),
            match_type=MatchType.FILE,
            root=tmp_path,
            indices=[0, 4],
        )
    )
    reporter.warn_matches_truncated(3, 1)

    lines = stdout.getvalue().splitlines()
    assert json.loads(lines[0]) == {
        "score": 42,
        "path": "src\\main.rs" if "\\" in str(Path("src/main.rs")) else "src/main.rs",
        "match_type": "file",
        "root": str(tmp_path),
        "indices": [0, 4],
    }
    assert json.loads(lines[1]) == {"matches_truncated": True}


def test_stdio_reporter_bolds_indices_only_when_requested(tmp_path: Path) -> None:
    # Rust source: StdioReporter walks sorted indices once and wraps matches in ANSI bold.
    stdout = io.StringIO()
    reporter = StdioReporter(write_output_as_json=False, show_indices=True, stdout=stdout, stderr=io.StringIO())

    reporter.report_match(FileMatch(1, Path("abcd"), MatchType.FILE, tmp_path, indices=[1, 3]))

    assert stdout.getvalue() == "a\x1b[1mb\x1b[0mc\x1b[1md\x1b[0m\n"


def test_run_cli_uses_real_library_options_and_warns_truncated(tmp_path: Path) -> None:
    # Rust source: run_main maps Cli into FileSearchOptions, reports matches, then warns on truncation.
    stdout = io.StringIO()
    stderr = io.StringIO()
    observed: dict[str, object] = {}

    def runner(
        pattern: str,
        roots: list[Path],
        options: FileSearchOptions,
        cancel_flag: object | None,
    ) -> FileSearchResults:
        observed.update(pattern=pattern, roots=roots, options=options, cancel_flag=cancel_flag)
        return FileSearchResults(
            matches=[FileMatch(7, Path("src/lib.rs"), MatchType.FILE, tmp_path)],
            total_match_count=2,
        )

    cli = Cli(
        pattern="lib",
        cwd=tmp_path,
        limit=1,
        exclude=["target"],
        threads=4,
        compute_indices=True,
    )

    assert run_cli(cli, StdioReporter(write_output_as_json=False, show_indices=False, stdout=stdout, stderr=stderr), runner=runner) == 0

    assert observed["pattern"] == "lib"
    assert observed["roots"] == [tmp_path]
    assert observed["cancel_flag"] is None
    options = observed["options"]
    assert isinstance(options, FileSearchOptions)
    assert options.limit == 1
    assert options.exclude == ["target"]
    assert options.threads == 4
    assert options.compute_indices is True
    assert options.respect_gitignore is True
    assert stdout.getvalue().strip().endswith(str(Path("src/lib.rs")))
    assert "Warning: showing 1 out of 2 results." in stderr.getvalue()


def test_main_no_pattern_warns_and_lists_without_running_search(tmp_path: Path) -> None:
    # Rust source: run_main warns and delegates to a directory listing when no pattern is provided.
    stdout = io.StringIO()
    stderr = io.StringIO()
    listed: list[Path] = []

    def runner(*_args: object) -> FileSearchResults:
        raise AssertionError("search should not run without a pattern")

    def list_directory(path: Path, out: io.StringIO, _err: io.StringIO) -> None:
        listed.append(path)
        print("listed", file=out)

    assert main(["--cwd", str(tmp_path)], stdout=stdout, stderr=stderr, runner=runner, list_directory=list_directory) == 0

    assert listed == [tmp_path]
    assert "No search pattern specified." in stderr.getvalue()
    assert stdout.getvalue() == "listed\n"


def test_main_compute_indices_is_gated_by_terminal_stdout(tmp_path: Path) -> None:
    # Rust source: show_indices is cli.compute_indices && stdout().is_terminal().
    stdout = TtyStringIO()
    stderr = io.StringIO()

    def runner(
        _pattern: str,
        _roots: list[Path],
        options: FileSearchOptions,
        _cancel_flag: object | None,
    ) -> FileSearchResults:
        assert options.compute_indices is True
        return FileSearchResults(
            matches=[FileMatch(9, Path("abcd"), MatchType.FILE, tmp_path, indices=[0, 2])],
            total_match_count=1,
        )

    assert main(["--compute-indices", "--cwd", str(tmp_path), "ac"], stdout=stdout, stderr=stderr, runner=runner) == 0

    assert stdout.getvalue() == "\x1b[1ma\x1b[0mb\x1b[1mc\x1b[0md\n"
