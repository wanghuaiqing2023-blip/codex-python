"""Git patch application owned by ``apply.rs``."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .errors import GitToolingError
from .operations import resolve_repository_root


@dataclass(frozen=True)
class ApplyGitRequest:
    cwd: Path
    diff: str
    revert: bool = False
    preflight: bool = False

    def __post_init__(self) -> None:
        _ensure_pathlike(self.cwd, "cwd")
        _ensure_str(self.diff, "diff")
        if not isinstance(self.revert, bool):
            raise TypeError("revert must be a bool")
        if not isinstance(self.preflight, bool):
            raise TypeError("preflight must be a bool")


@dataclass(frozen=True)
class ApplyGitResult:
    exit_code: int
    applied_paths: list[str]
    skipped_paths: list[str]
    conflicted_paths: list[str]
    stdout: str
    stderr: str
    cmd_for_log: str

    def __post_init__(self) -> None:
        _ensure_i64(self.exit_code, "exit_code")
        _ensure_str_list(self.applied_paths, "applied_paths")
        _ensure_str_list(self.skipped_paths, "skipped_paths")
        _ensure_str_list(self.conflicted_paths, "conflicted_paths")
        _ensure_str(self.stdout, "stdout")
        _ensure_str(self.stderr, "stderr")
        _ensure_str(self.cmd_for_log, "cmd_for_log")


def extract_paths_from_patch(diff_text: str) -> list[str]:
    """Collect paths referenced by ``diff --git`` headers."""

    _ensure_str(diff_text, "diff_text")
    paths: set[str] = set()
    for raw_line in diff_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("diff --git "):
            continue
        parsed = _parse_diff_git_paths(line.removeprefix("diff --git "))
        if parsed is None:
            continue
        left, right = parsed
        left_path = _normalize_diff_path(left, "a/")
        right_path = _normalize_diff_path(right, "b/")
        if left_path is not None:
            paths.add(left_path)
        if right_path is not None:
            paths.add(right_path)
    return sorted(paths)


def stage_paths(git_root: Path | str, diff: str) -> None:
    """Best-effort stage of existing paths referenced by a patch."""

    _ensure_pathlike(git_root, "git_root")
    _ensure_str(diff, "diff")
    root = Path(git_root)
    existing = [path for path in extract_paths_from_patch(diff) if (root / path).exists() or (root / path).is_symlink()]
    if not existing:
        return
    try:
        subprocess.run(
            ["git", "add", "--", *existing],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        return


def parse_git_apply_output(stdout: str, stderr: str) -> tuple[list[str], list[str], list[str]]:
    """Parse ``git apply`` output into applied, skipped, and conflicted paths."""

    _ensure_str(stdout, "stdout")
    _ensure_str(stderr, "stderr")
    combined = "\n".join(part for part in (stdout, stderr) if part)
    applied: set[str] = set()
    skipped: set[str] = set()
    conflicted: set[str] = set()
    last_seen_path: str | None = None

    clean_patterns = [
        r"^Applied patch(?: to)?\s+(.+?)\s+cleanly\.?$",
    ]
    conflict_patterns = [
        r"^Applied patch(?: to)?\s+(.+?)\s+with conflicts\.?$",
        r"^Applying patch\s+(.+?)\s+with\s+\d+\s+rejects?\.{0,3}$",
        r"^U\s+(.+)$",
        r"^warning:\s*Cannot merge binary files:\s+(.+?)\s+\(ours\s+vs\.\s+theirs\)",
    ]
    early_skip_patterns = [
        r"^error:\s+patch failed:\s+(.+?)(?::\d+)?(?:\s|$)",
        r"^error:\s+(.+?):\s+patch does not apply$",
    ]
    skip_patterns = [
        r"^error:\s+(.+?):\s+does not match index\b",
        r"^error:\s+(.+?):\s+does not exist in index\b",
        r"^error:\s+(.+?)\s+already exists in (?:the )?working directory\b",
        r"^error:\s+patch failed:\s+(.+?)\s+File exists",
        r"^error:\s+path\s+(.+?)\s+has been renamed/deleted",
        r"^error:\s+cannot apply binary patch to\s+['\"]?(.+?)['\"]?\s+without full index line$",
        r"^error:\s+binary patch does not apply to\s+['\"]?(.+?)['\"]?$",
        r"^error:\s+binary patch to\s+['\"]?(.+?)['\"]?\s+creates incorrect result\b",
        r"^error:\s+cannot read the current contents of\s+['\"]?(.+?)['\"]?$",
        r"^Skipped patch\s+['\"]?(.+?)['\"]\.$",
    ]

    for raw_line in combined.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        checking = re.match(r"^Checking patch\s+(.+?)\.\.\.$", line, flags=re.IGNORECASE)
        if checking is not None:
            last_seen_path = checking.group(1)
            continue
        matched = _match_apply_path(clean_patterns, line)
        if matched is not None:
            path = _add_apply_path(applied, matched)
            if path is not None:
                conflicted.discard(path)
                skipped.discard(path)
                last_seen_path = path
            continue
        matched = _match_apply_path(conflict_patterns, line)
        if matched is not None:
            path = _add_apply_path(conflicted, matched)
            if path is not None:
                applied.discard(path)
                skipped.discard(path)
                last_seen_path = path
            continue
        matched = _match_apply_path(early_skip_patterns, line)
        if matched is not None:
            path = _add_apply_path(skipped, matched)
            if path is not None:
                last_seen_path = path
            continue
        if re.match(r"^(?:Performing three-way merge|Falling back to three-way merge)\.\.\.$", line, flags=re.IGNORECASE):
            continue
        if re.match(r"^Falling back to direct application\.\.\.$", line, flags=re.IGNORECASE):
            continue
        if re.match(r"^Failed to perform three-way merge\.\.\.$", line, flags=re.IGNORECASE) or re.match(
            r"^(?:error: )?repository lacks the necessary blob to (?:perform|fall back on) 3-?way merge\.?$",
            line,
            flags=re.IGNORECASE,
        ):
            if last_seen_path is not None:
                path = _add_apply_path(skipped, last_seen_path)
                if path is not None:
                    applied.discard(path)
                    conflicted.discard(path)
            continue
        matched = _match_apply_path(skip_patterns, line)
        if matched is not None:
            path = _add_apply_path(skipped, matched)
            if path is not None:
                applied.discard(path)
                conflicted.discard(path)
                last_seen_path = path

    for path in conflicted:
        applied.discard(path)
        skipped.discard(path)
    for path in applied:
        skipped.discard(path)
    return sorted(applied), sorted(skipped), sorted(conflicted)


def apply_git_patch(request: ApplyGitRequest) -> ApplyGitResult:
    """Apply a unified diff to a git repository using ``git apply``."""

    if not isinstance(request, ApplyGitRequest):
        raise TypeError("request must be an ApplyGitRequest")
    git_root = resolve_repository_root(request.cwd)
    with tempfile.TemporaryDirectory() as tmpdir:
        patch_path = Path(tmpdir) / "patch.diff"
        patch_path.write_text(request.diff, encoding="utf-8")
        if request.revert and not request.preflight:
            stage_paths(git_root, request.diff)

        git_cfg = _apply_git_cfg_parts()
        if request.preflight:
            args = ["apply", "--check"]
            if request.revert:
                args.append("-R")
            args.append(str(patch_path))
            cmd_for_log = _render_command_for_log(git_root, git_cfg, args)
            exit_code, stdout, stderr = _run_git_apply_command(git_root, git_cfg, args)
        else:
            args = ["apply", "--3way"]
            if request.revert:
                args.append("-R")
            args.append(str(patch_path))
            cmd_for_log = _render_command_for_log(git_root, git_cfg, args)
            exit_code, stdout, stderr = _run_git_apply_command(git_root, git_cfg, args)

    applied, skipped, conflicted = parse_git_apply_output(stdout, stderr)
    return ApplyGitResult(
        exit_code=exit_code,
        applied_paths=applied,
        skipped_paths=skipped,
        conflicted_paths=conflicted,
        stdout=stdout,
        stderr=stderr,
        cmd_for_log=cmd_for_log,
    )


def _apply_git_cfg_parts() -> list[str]:
    parts: list[str] = []
    for pair in os.environ.get("CODEX_APPLY_GIT_CFG", "").split(","):
        value = pair.strip()
        if not value or "=" not in value:
            continue
        parts.extend(["-c", value])
    return parts


def _run_git_apply_command(cwd: Path, git_cfg: list[str], args: list[str]) -> tuple[int, str, str]:
    try:
        output = subprocess.run(
            ["git", *git_cfg, *args],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise GitToolingError(str(exc)) from exc
    return (
        output.returncode if output.returncode is not None else -1,
        output.stdout.decode("utf-8", errors="replace"),
        output.stderr.decode("utf-8", errors="replace"),
    )


def _quote_shell(value: str) -> str:
    simple = all(char.isascii() and (char.isalnum() or char in "-_.:/@%+") for char in value)
    if simple:
        return value
    return "'" + value.replace("'", "'\\''") + "'"


def _render_command_for_log(cwd: Path, git_cfg: list[str], args: list[str]) -> str:
    parts = ["git", *(_quote_shell(arg) for arg in git_cfg), *(_quote_shell(arg) for arg in args)]
    return f"(cd {_quote_shell(str(cwd))} && {' '.join(parts)})"


def _match_apply_path(patterns: Iterable[str], line: str) -> str | None:
    for pattern in patterns:
        match = re.match(pattern, line, flags=re.IGNORECASE)
        if match is not None:
            return match.group(1)
    return None


def _add_apply_path(paths: set[str], raw: str) -> str | None:
    trimmed = raw.strip()
    if not trimmed:
        return None
    first = trimmed[0]
    last = trimmed[-1]
    if first in {"'", '"'} and last == first and len(trimmed) >= 2:
        value = _unescape_c_string(trimmed[1:-1])
    else:
        value = trimmed
    if not value:
        return None
    paths.add(value)
    return value


def _parse_diff_git_paths(line: str) -> tuple[str, str] | None:
    tokens: list[str] = []
    index = 0
    while len(tokens) < 2:
        token, index = _read_diff_git_token(line, index)
        if token is None:
            return None
        tokens.append(token)
    return tokens[0], tokens[1]


def _read_diff_git_token(line: str, index: int) -> tuple[str | None, int]:
    length = len(line)
    while index < length and line[index].isspace():
        index += 1
    if index >= length:
        return None, index
    quote = line[index] if line[index] in {"'", '"'} else None
    if quote is not None:
        index += 1
    output: list[str] = []
    while index < length:
        char = line[index]
        index += 1
        if quote is not None:
            if char == quote:
                break
            if char == "\\" and index < length:
                output.append(char)
                output.append(line[index])
                index += 1
                continue
        elif char.isspace():
            break
        output.append(char)
    if not output and quote is None:
        return None, index
    token = "".join(output)
    return (_unescape_c_string(token) if quote is not None else token), index


def _normalize_diff_path(raw: str, prefix: str) -> str | None:
    trimmed = raw.strip()
    if not trimmed or trimmed == "/dev/null" or trimmed == f"{prefix}dev/null":
        return None
    if trimmed.startswith(prefix):
        trimmed = trimmed[len(prefix) :]
    return trimmed or None


def _unescape_c_string(input_text: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(input_text):
        char = input_text[index]
        index += 1
        if char != "\\":
            output.append(char)
            continue
        if index >= len(input_text):
            output.append("\\")
            break
        escaped = input_text[index]
        index += 1
        mapping = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "a": "\a", "v": "\v", "\\": "\\", '"': '"', "'": "'"}
        if escaped in mapping:
            output.append(mapping[escaped])
        elif escaped in "01234567":
            digits = [escaped]
            for _ in range(2):
                if index < len(input_text) and input_text[index] in "01234567":
                    digits.append(input_text[index])
                    index += 1
                else:
                    break
            output.append(chr(int("".join(digits), 8)))
        else:
            output.append(escaped)
    return "".join(output)


def _ensure_pathlike(value: object, name: str) -> None:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{name} must be a path-like value")


def _ensure_str(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")


def _ensure_str_list(value: object, name: str) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{name} must be a list of strings")


def _ensure_i64(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError(f"{name} must fit in a signed 64-bit integer")


def _ensure_usize(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


__all__ = ['ApplyGitRequest', 'ApplyGitResult', 'apply_git_patch', 'extract_paths_from_patch', 'parse_git_apply_output', 'stage_paths']
