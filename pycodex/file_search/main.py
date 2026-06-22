"""Executable entrypoint behavior for Rust ``codex-file-search/src/main.rs``."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Callable, Sequence, TextIO

from . import FileMatch, FileSearchOptions, FileSearchResults, run
from .cli import Cli

Runner = Callable[[str, Sequence[Path], FileSearchOptions, object | None], FileSearchResults]
ListDirectory = Callable[[Path, TextIO, TextIO], None]


class StdioReporter:
    def __init__(
        self,
        *,
        write_output_as_json: bool,
        show_indices: bool,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> None:
        self.write_output_as_json = bool(write_output_as_json)
        self.show_indices = bool(show_indices)
        self.stdout = stdout if stdout is not None else sys.stdout
        self.stderr = stderr if stderr is not None else sys.stderr

    def report_match(self, file_match: FileMatch) -> None:
        if self.write_output_as_json:
            print(json.dumps(file_match.to_json(), separators=(",", ":")), file=self.stdout)
            return
        if self.show_indices:
            indices = file_match.indices
            if indices is None:
                raise ValueError("--compute-indices was specified")
            self._print_match_with_indices(file_match, indices)
            return
        print(str(file_match.path), file=self.stdout)

    def warn_matches_truncated(self, total_match_count: int, shown_match_count: int) -> None:
        if self.write_output_as_json:
            print(json.dumps({"matches_truncated": True}, separators=(",", ":")), file=self.stdout)
            return
        print(
            "Warning: showing "
            f"{shown_match_count} out of {total_match_count} results. "
            "Provide a more specific pattern or increase the --limit.",
            file=self.stderr,
        )

    def warn_no_search_pattern(self, search_directory: Path) -> None:
        print(
            "No search pattern specified. Showing the contents of the current directory "
            f"({search_directory}):",
            file=self.stderr,
        )

    def _print_match_with_indices(self, file_match: FileMatch, indices: Sequence[int]) -> None:
        highlighted = set(int(index) for index in indices)
        for index, char in enumerate(str(file_match.path)):
            if index in highlighted:
                print(f"\x1b[1m{char}\x1b[0m", end="", file=self.stdout)
            else:
                print(char, end="", file=self.stdout)
        print(file=self.stdout)


def run_cli(
    cli: Cli,
    reporter: StdioReporter,
    *,
    runner: Runner = run,
    cwd_provider: Callable[[], Path] = Path.cwd,
    list_directory: ListDirectory | None = None,
) -> int:
    search_directory = Path(cli.cwd) if cli.cwd is not None else Path(cwd_provider())
    if cli.pattern is None:
        reporter.warn_no_search_pattern(search_directory)
        (list_directory or _list_directory)(search_directory, reporter.stdout, reporter.stderr)
        return 0

    results = runner(
        cli.pattern,
        [search_directory],
        FileSearchOptions(
            limit=cli.limit,
            exclude=list(cli.exclude),
            threads=cli.threads,
            compute_indices=cli.compute_indices,
            respect_gitignore=True,
        ),
        None,
    )
    shown_match_count = len(results.matches)
    for file_match in results.matches:
        reporter.report_match(file_match)
    if results.total_match_count > shown_match_count:
        reporter.warn_matches_truncated(results.total_match_count, shown_match_count)
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    runner: Runner = run,
    cwd_provider: Callable[[], Path] = Path.cwd,
    list_directory: ListDirectory | None = None,
) -> int:
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr
    cli = Cli.parse_args(argv)
    reporter = StdioReporter(
        write_output_as_json=cli.json,
        show_indices=cli.compute_indices and bool(stdout.isatty()),
        stdout=stdout,
        stderr=stderr,
    )
    return run_cli(cli, reporter, runner=runner, cwd_provider=cwd_provider, list_directory=list_directory)


def _list_directory(search_directory: Path, stdout: TextIO, stderr: TextIO) -> None:
    try:
        entries = sorted(os.scandir(search_directory), key=lambda entry: entry.name)
    except OSError as exc:
        print(str(exc), file=stderr)
        return
    for entry in entries:
        print(entry.name + ("/" if entry.is_dir(follow_symlinks=False) else ""), file=stdout)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["StdioReporter", "main", "run_cli"]
