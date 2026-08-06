"""Python port of Rust ``codex-file-search/src/lib.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
import re
from threading import Event
from typing import Any, Iterable, Protocol, Sequence

from .cli import Cli


class MatchType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"


@dataclass(frozen=True)
class FileMatch:
    score: int
    path: Path
    match_type: MatchType
    root: Path
    indices: list[int] | None = None

    def full_path(self) -> Path:
        return self.root / self.path

    def to_json(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "score": self.score,
            "path": str(self.path),
            "match_type": self.match_type.value,
            "root": str(self.root),
        }
        if self.indices is not None:
            value["indices"] = list(self.indices)
        return value


def file_name_from_path(path: str) -> str:
    name = Path(path).name
    return name if name else path


@dataclass(frozen=True)
class FileSearchResults:
    matches: list[FileMatch]
    total_match_count: int


@dataclass(frozen=True)
class FileSearchSnapshot:
    query: str = ""
    matches: list[FileMatch] = field(default_factory=list)
    total_match_count: int = 0
    scanned_file_count: int = 0
    walk_complete: bool = False


@dataclass(frozen=True)
class FileSearchOptions:
    limit: int = 20
    exclude: list[str] = field(default_factory=list)
    threads: int = 2
    compute_indices: bool = False
    respect_gitignore: bool = True

    def __post_init__(self) -> None:
        if int(self.limit) <= 0:
            raise ValueError("limit must be non-zero")
        if int(self.threads) <= 0:
            raise ValueError("threads must be non-zero")
        object.__setattr__(self, "limit", int(self.limit))
        object.__setattr__(self, "threads", int(self.threads))


class SessionReporter(Protocol):
    def on_update(self, snapshot: FileSearchSnapshot) -> None: ...

    def on_complete(self) -> None: ...


class Reporter(Protocol):
    def report_match(self, file_match: FileMatch) -> None: ...

    def warn_matches_truncated(self, total_match_count: int, shown_match_count: int) -> None: ...

    def warn_no_search_pattern(self, search_directory: Path) -> None: ...


class FileSearchSession:
    def __init__(
        self,
        search_directories: Sequence[Path | str],
        options: FileSearchOptions,
        reporter: SessionReporter,
        cancel_flag: Any | None = None,
    ) -> None:
        if not search_directories:
            raise ValueError("at least one search directory is required")
        self.search_directories = [Path(path) for path in search_directories]
        self.options = options
        self.reporter = reporter
        self.cancel_flag = cancel_flag
        self._closed = False
        self._entries = _walk_entries(
            self.search_directories,
            exclude=options.exclude,
            respect_gitignore=options.respect_gitignore,
            cancel_flag=cancel_flag,
        )

    def update_query(self, pattern_text: str) -> None:
        if self._closed:
            return
        snapshot = _snapshot_for_query(
            str(pattern_text),
            self.search_directories,
            self._entries,
            self.options,
            walk_complete=True,
        )
        self.reporter.on_update(snapshot)
        self.reporter.on_complete()

    def close(self) -> None:
        self._closed = True
        self.reporter.on_complete()

    def __enter__(self) -> "FileSearchSession":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def create_session(
    search_directories: Sequence[Path | str],
    options: FileSearchOptions | None,
    reporter: SessionReporter,
    cancel_flag: Any | None = None,
) -> FileSearchSession:
    return FileSearchSession(search_directories, options or FileSearchOptions(), reporter, cancel_flag)


def run(
    pattern_text: str,
    roots: Sequence[Path | str],
    options: FileSearchOptions | None = None,
    cancel_flag: Any | None = None,
) -> FileSearchResults:
    reporter = _RunReporter()
    session = create_session(roots, options or FileSearchOptions(), reporter, cancel_flag)
    session.update_query(pattern_text)
    snapshot = reporter.snapshot
    return FileSearchResults(matches=snapshot.matches, total_match_count=snapshot.total_match_count)


def cmp_by_score_desc_then_path_asc(item: FileMatch | tuple[int, str]) -> tuple[int, str]:
    if isinstance(item, FileMatch):
        return (-int(item.score), str(item.path))
    return (-int(item[0]), str(item[1]))


def sort_matches(matches: list[tuple[int, str]]) -> None:
    matches.sort(key=cmp_by_score_desc_then_path_asc)


@dataclass
class _RunReporter:
    snapshot: FileSearchSnapshot = field(default_factory=FileSearchSnapshot)
    completed: Event = field(default_factory=Event)

    def on_update(self, snapshot: FileSearchSnapshot) -> None:
        self.snapshot = snapshot

    def on_complete(self) -> None:
        self.completed.set()


def _snapshot_for_query(
    query: str,
    roots: Sequence[Path],
    entries: Sequence[tuple[Path, Path, MatchType]],
    options: FileSearchOptions,
    *,
    walk_complete: bool,
) -> FileSearchSnapshot:
    ranked_matches: list[tuple[FileMatch, int]] = []
    for entry_index, (root, relative, match_type) in enumerate(entries):
        score_indices = _fuzzy_score(str(relative), query)
        if score_indices is None:
            continue
        score, indices = score_indices
        match = FileMatch(
            score=score,
            path=relative,
            match_type=match_type,
            root=root,
            indices=indices if options.compute_indices else None,
        )
        ranked_matches.append((match, entry_index))
    # Rust's production path is ``Nucleo::snapshot().matches()``, whose
    # ordering is score descending, matcher-column length ascending, then
    # injector order.  ``cmp_by_score_desc_then_path_asc`` is a separate Rust
    # helper used only by its unit test and must not be used here.
    ranked_matches.sort(key=lambda item: (-item[0].score, len(str(item[0].path)), item[1]))
    ordered_matches = [match for match, _entry_index in ranked_matches]
    total = len(ranked_matches)
    return FileSearchSnapshot(
        query=query,
        matches=ordered_matches[: options.limit],
        total_match_count=total,
        scanned_file_count=len(entries),
        walk_complete=walk_complete,
    )


def _walk_entries(
    roots: Sequence[Path],
    *,
    exclude: Sequence[str],
    respect_gitignore: bool,
    cancel_flag: Any | None,
) -> list[tuple[Path, Path, MatchType]]:
    entries: list[tuple[Path, Path, MatchType]] = []
    for root in roots:
        root = root.resolve()
        git_context = _find_git_context(root) if respect_gitignore else None
        ancestor_rules = _load_ancestor_ignore_rules(root, git_context) if respect_gitignore else []
        root_rules = list(ancestor_rules)
        if respect_gitignore:
            root_rules.extend(_load_ignore_rules(root, git_context is not None))
        stack: list[tuple[Path, Path, list[_IgnoreRule]]] = []
        visited_directories: set[Path] = set()

        def push_children(directory: Path, relative_directory: Path, rules: list[_IgnoreRule]) -> None:
            try:
                children = sorted(os.scandir(directory), key=lambda child: child.name.casefold())
            except OSError:
                return
            for child in children:
                relative = relative_directory / child.name if str(relative_directory) != "." else Path(child.name)
                stack.append((Path(child.path), relative, rules))

        push_children(root, Path("."), root_rules)
        while stack:
            if _cancelled(cancel_flag):
                return []
            full_path, relative, parent_rules = stack.pop()
            try:
                is_directory = full_path.is_dir()
            except OSError:
                continue
            if _excluded(relative, exclude) or _ignored_by_rules(full_path, is_directory, parent_rules):
                continue
            match_type = MatchType.DIRECTORY if is_directory else MatchType.FILE
            entries.append((root, relative, match_type))
            if not is_directory:
                continue
            try:
                resolved = full_path.resolve()
            except OSError:
                resolved = full_path.absolute()
            if resolved in visited_directories:
                continue
            visited_directories.add(resolved)
            child_rules = list(parent_rules)
            if respect_gitignore:
                child_rules.extend(_load_ignore_rules(full_path, git_context is not None))
            push_children(full_path, relative, child_rules)
    return entries


def _relative_path(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def _excluded(path: Path, patterns: Sequence[str]) -> bool:
    text = path.as_posix()
    return any(path.match(pattern) or text == pattern or text.startswith(pattern.rstrip("/") + "/") for pattern in patterns)


def _fuzzy_score(haystack: str, query: str) -> tuple[int, list[int]] | None:
    if not query:
        return (0, [])
    normalized_haystack = [_normalize_char(char) for char in haystack]
    normalized_query = [_normalize_char(char) for char in query]
    if len(normalized_query) > len(normalized_haystack):
        return None

    bonuses = _nucleo_path_bonuses(haystack)
    # Each state is ``(score, consecutive_bonus, indices)`` and represents a
    # match of the current needle character at a specific haystack column.
    previous: dict[int, tuple[int, int, tuple[int, ...]]] = {}
    for needle_index, needle_char in enumerate(normalized_query):
        current: dict[int, tuple[int, int, tuple[int, ...]]] = {}
        for column, haystack_char in enumerate(normalized_haystack):
            if haystack_char != needle_char:
                continue
            bonus = bonuses[column]
            if needle_index == 0:
                current[column] = (16 + bonus * 2, bonus, (column,))
                continue
            best: tuple[int, int, tuple[int, ...]] | None = None
            for previous_column, (previous_score, previous_consecutive, previous_indices) in previous.items():
                if previous_column >= column:
                    continue
                gap = column - previous_column - 1
                if gap == 0:
                    consecutive = max(previous_consecutive, 4)
                    if bonus >= 8 and bonus > consecutive:
                        consecutive = bonus
                    score = previous_score + 16 + max(consecutive, bonus)
                else:
                    consecutive = bonus
                    score = max(0, previous_score - 3 - max(0, gap - 1)) + 16 + bonus
                candidate = (score, consecutive, previous_indices + (column,))
                # Nucleo chooses the later matrix cell on equal scores.
                if best is None or candidate[0] >= best[0]:
                    best = candidate
            if best is not None:
                current[column] = best
        if not current:
            return None
        previous = current

    best: tuple[int, int, tuple[int, ...]] | None = None
    for state in previous.values():
        if best is None or state[0] >= best[0]:
            best = state
    assert best is not None
    return (best[0], list(best[2]))


def _cancelled(flag: Any | None) -> bool:
    if flag is None:
        return False
    if hasattr(flag, "is_set"):
        return bool(flag.is_set())
    if hasattr(flag, "load"):
        return bool(flag.load())
    return bool(flag)


def _normalize_char(char: str) -> str:
    return char.casefold()


def _char_class(char: str) -> int:
    if char.isspace():
        return 0  # Whitespace
    if char in "/\\":
        return 2  # Delimiter (Config::DEFAULT.match_paths)
    if "a" <= char <= "z" or char.islower():
        return 3  # Lower
    if "A" <= char <= "Z" or char.isupper():
        return 4  # Upper
    if char.isalpha():
        return 5  # Letter
    if char.isnumeric():
        return 6  # Number
    return 1  # NonWord


def _nucleo_path_bonuses(haystack: str) -> list[int]:
    bonuses: list[int] = []
    previous_class = 2  # match_paths initial_char_class = Delimiter
    for char in haystack:
        current_class = _char_class(char)
        if current_class > 2 and previous_class == 0:
            bonus = 8
        elif current_class > 2 and previous_class == 2:
            bonus = 9
        elif current_class > 2 and previous_class == 1:
            bonus = 8
        elif (previous_class == 3 and current_class == 4) or (previous_class != 6 and current_class == 6):
            bonus = 5
        elif current_class == 0:
            bonus = 8
        elif current_class == 1:
            bonus = 8
        else:
            bonus = 0
        bonuses.append(bonus)
        previous_class = current_class
    return bonuses


@dataclass(frozen=True)
class _IgnoreRule:
    base: Path
    base_text: str
    base_key: str
    pattern: str
    negated: bool
    directory_only: bool
    anchored: bool
    regex: re.Pattern[str]


def _find_git_context(root: Path) -> Path | None:
    for candidate in (root, *root.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _load_ancestor_ignore_rules(root: Path, git_context: Path | None) -> list[_IgnoreRule]:
    if git_context is None:
        return []
    rules: list[_IgnoreRule] = []
    chain = [parent for parent in root.parents if parent == git_context or git_context in parent.parents]
    for directory in reversed(chain):
        rules.extend(_read_ignore_file(directory / ".gitignore", directory))
    rules.extend(_read_ignore_file(git_context / ".git" / "info" / "exclude", git_context))
    return rules


def _load_ignore_rules(directory: Path, has_git_context: bool) -> list[_IgnoreRule]:
    rules = _read_ignore_file(directory / ".ignore", directory)
    if has_git_context:
        rules.extend(_read_ignore_file(directory / ".gitignore", directory))
    return rules


def _read_ignore_file(path: Path, base: Path) -> list[_IgnoreRule]:
    if not path.is_file():
        return []
    rules: list[_IgnoreRule] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(r"\#") or line.startswith(r"\!"):
            line = line[1:]
        negated = line.startswith("!")
        if negated:
            line = line[1:]
        directory_only = line.endswith("/")
        line = line.rstrip("/")
        anchored = line.startswith("/") or "/" in line
        line = line.lstrip("/")
        if line:
            rules.append(
                _IgnoreRule(
                    base,
                    os.path.abspath(base),
                    os.path.normcase(os.path.abspath(base)),
                    line,
                    negated,
                    directory_only,
                    anchored,
                    re.compile(_gitignore_regex(line)),
                )
            )
    return rules


def _ignored_by_rules(path: Path, is_dir: bool, rules: Sequence[_IgnoreRule]) -> bool:
    ignored = False
    path_text = os.path.abspath(path)
    path_key = os.path.normcase(path_text)
    for rule in rules:
        prefix = rule.base_key + os.sep
        if not path_key.startswith(prefix):
            continue
        relative = path_text[len(rule.base_text) + 1 :].replace(os.sep, "/")
        if _ignore_rule_matches(relative, is_dir, rule):
            ignored = not rule.negated
    return ignored


def _ignore_rule_matches(relative: str, is_dir: bool, rule: _IgnoreRule) -> bool:
    components = relative.split("/")
    if rule.anchored:
        if rule.directory_only:
            return is_dir and rule.regex.fullmatch(relative) is not None
        return rule.regex.fullmatch(relative) is not None
    if rule.directory_only:
        return is_dir and rule.regex.fullmatch(components[-1]) is not None
    return any(rule.regex.fullmatch(component) for component in components)


def _gitignore_regex(pattern: str) -> str:
    output = ""
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                index += 1
                if index + 1 < len(pattern) and pattern[index + 1] == "/":
                    index += 1
                    output += "(?:.*/)?"
                else:
                    output += ".*"
            else:
                output += "[^/]*"
        elif char == "?":
            output += "[^/]"
        elif char == "[":
            end = pattern.find("]", index + 1)
            if end >= 0:
                output += pattern[index : end + 1]
                index = end
            else:
                output += r"\["
        else:
            output += re.escape(char)
        index += 1
    return output


__all__ = [
    "Cli",
    "FileMatch",
    "FileSearchOptions",
    "FileSearchResults",
    "FileSearchSession",
    "FileSearchSnapshot",
    "MatchType",
    "Reporter",
    "SessionReporter",
    "cmp_by_score_desc_then_path_asc",
    "create_session",
    "file_name_from_path",
    "run",
    "sort_matches",
]
