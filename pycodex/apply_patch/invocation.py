"""Invocation recognition and verification owned by ``invocation.rs``."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

from . import (
    ApplyPatchAction, ApplyPatchArgs, ApplyPatchError, ApplyPatchFileChange,
    MaybeApplyPatchVerified, _ensure_absent, _ensure_str,
    unified_diff_from_chunks,
)
from .parser import ApplyPatchParseError, parse_patch

APPLY_PATCH_COMMANDS = ("apply_patch", "applypatch")

@dataclass(frozen=True)
class MaybeApplyPatch:
    type: str
    body: ApplyPatchArgs | None = None
    error: ApplyPatchParseError | str | None = None

    def __post_init__(self) -> None:
        if self.type not in {"body", "patch_parse_error", "shell_parse_error", "not_apply_patch"}:
            raise ValueError("unknown maybe apply_patch type")
        if self.type == "body":
            if not isinstance(self.body, ApplyPatchArgs):
                raise TypeError("body must be an ApplyPatchArgs")
            _ensure_absent(self.error, "error")
            return
        _ensure_absent(self.body, "body")
        if self.type == "patch_parse_error" and not isinstance(self.error, ApplyPatchParseError):
            raise TypeError("error must be an ApplyPatchParseError")
        if self.type == "shell_parse_error":
            _ensure_str(self.error, "error")
        if self.type == "not_apply_patch":
            _ensure_absent(self.error, "error")

    @classmethod
    def body_result(cls, body: ApplyPatchArgs) -> "MaybeApplyPatch":
        return cls(type="body", body=body)

    @classmethod
    def patch_parse_error(cls, error: ApplyPatchParseError) -> "MaybeApplyPatch":
        return cls(type="patch_parse_error", error=error)

    @classmethod
    def shell_parse_error(cls, error: str) -> "MaybeApplyPatch":
        return cls(type="shell_parse_error", error=error)

    @classmethod
    def not_apply_patch(cls) -> "MaybeApplyPatch":
        return cls(type="not_apply_patch")

def maybe_parse_apply_patch(argv: list[str] | tuple[str, ...]) -> MaybeApplyPatch:
    if len(argv) == 2 and argv[0] in APPLY_PATCH_COMMANDS:
        try:
            return MaybeApplyPatch.body_result(parse_patch(argv[1]))
        except ApplyPatchParseError as error:
            return MaybeApplyPatch.patch_parse_error(error)

    shell_script = _parse_shell_script(argv)
    if shell_script is None:
        return MaybeApplyPatch.not_apply_patch()
    _shell_kind, script = shell_script
    extracted = _extract_apply_patch_from_shell(script)
    if extracted is None:
        return MaybeApplyPatch.not_apply_patch()
    body, workdir = extracted
    try:
        source = parse_patch(body)
    except ApplyPatchParseError as error:
        return MaybeApplyPatch.patch_parse_error(error)
    return MaybeApplyPatch.body_result(
        ApplyPatchArgs(
            patch=source.patch,
            hunks=source.hunks,
            workdir=workdir,
            environment_id=source.environment_id,
        )
    )

def maybe_parse_apply_patch_verified(
    argv: list[str] | tuple[str, ...],
    cwd: str | Path,
) -> MaybeApplyPatchVerified:
    if len(argv) == 1:
        try:
            parse_patch(argv[0])
        except ApplyPatchParseError:
            pass
        else:
            return MaybeApplyPatchVerified.correctness_error(
                ApplyPatchError.implicit_invocation()
            )

    shell_script = _parse_shell_script(argv)
    if shell_script is not None:
        _shell_kind, script = shell_script
        try:
            parse_patch(script)
        except ApplyPatchParseError:
            pass
        else:
            return MaybeApplyPatchVerified.correctness_error(
                ApplyPatchError.implicit_invocation()
            )

    parsed = maybe_parse_apply_patch(argv)
    if parsed.type == "body":
        assert parsed.body is not None
        return verify_apply_patch_args(parsed.body, cwd)
    if parsed.type == "shell_parse_error":
        return MaybeApplyPatchVerified.shell_parse_error(str(parsed.error))
    if parsed.type == "patch_parse_error":
        assert isinstance(parsed.error, ApplyPatchParseError)
        return MaybeApplyPatchVerified.correctness_error(
            ApplyPatchError.parse_error(parsed.error)
        )
    return MaybeApplyPatchVerified.not_apply_patch()

def verify_apply_patch_args(
    args: ApplyPatchArgs,
    cwd: str | Path,
) -> MaybeApplyPatchVerified:
    cwd_path = Path(cwd)
    if not cwd_path.is_absolute():
        raise ValueError("cwd must be an absolute path")

    effective_cwd = cwd_path / args.workdir if args.workdir is not None else cwd_path
    workspace_root = _workspace_root_for_cwd(cwd_path)
    if not args.hunks:
        return MaybeApplyPatchVerified.correctness_error(
            ApplyPatchError.compute_replacements("patch must contain at least one hunk")
        )
    changes: dict[Path, ApplyPatchFileChange] = {}
    for hunk in args.hunks:
        path = hunk.resolve_path(effective_cwd)
        path_escape_error = _apply_patch_path_escape_error(path, workspace_root)
        if path_escape_error is not None:
            return MaybeApplyPatchVerified.correctness_error(path_escape_error)
        if hunk.type == "add":
            overwritten_content = _read_optional_text(path)
            changes[path] = ApplyPatchFileChange.add(
                hunk.contents or "",
                overwritten_content=overwritten_content,
            )
            continue

        if hunk.type == "delete":
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as error:
                return MaybeApplyPatchVerified.correctness_error(
                    ApplyPatchError.io_error(f"Failed to read {path}", error)
                )
            changes[path] = ApplyPatchFileChange.delete(content)
            continue

        if hunk.type == "update":
            try:
                original_content = path.read_text(encoding="utf-8")
            except OSError as error:
                return MaybeApplyPatchVerified.correctness_error(
                    ApplyPatchError.io_error(
                        f"Failed to read file to update {path}",
                        error,
                    )
                )
            try:
                update = unified_diff_from_chunks(
                    path,
                    hunk.chunks,
                    original_content,
                )
            except ApplyPatchError as error:
                return MaybeApplyPatchVerified.correctness_error(error)
            move_path = effective_cwd / hunk.move_path if hunk.move_path is not None else None
            move_path_escape_error = _apply_patch_path_escape_error(move_path, workspace_root)
            if move_path_escape_error is not None:
                return MaybeApplyPatchVerified.correctness_error(move_path_escape_error)
            changes[path] = ApplyPatchFileChange.update(
                update.unified_diff,
                move_path=move_path,
                new_content=update.content,
                old_content=original_content,
                overwritten_move_content=_read_optional_text(move_path) if move_path is not None else None,
            )
            continue

        return MaybeApplyPatchVerified.correctness_error(
            ApplyPatchError.compute_replacements(
                f"unknown apply_patch hunk type: {hunk.type}"
            )
        )

    return MaybeApplyPatchVerified.body_result(
        ApplyPatchAction(changes=changes, cwd=effective_cwd, patch=args.patch)
    )

def _parse_shell_script(argv: list[str] | tuple[str, ...]) -> tuple[str, str] | None:
    if len(argv) == 3:
        shell, flag, script = argv
        shell_kind = _classify_shell(shell, flag)
        return (shell_kind, script) if shell_kind is not None else None
    if len(argv) == 4 and _can_skip_shell_flag(argv[0], argv[1]):
        shell_kind = _classify_shell(argv[0], argv[2])
        return (shell_kind, argv[3]) if shell_kind is not None else None
    return None

def _classify_shell(shell: str, flag: str) -> str | None:
    name = _classify_shell_name(shell)
    flag_lc = flag.lower()
    if name in {"bash", "zsh", "sh"} and flag in {"-lc", "-c"}:
        return "unix"
    if name in {"pwsh", "powershell"} and flag_lc == "-command":
        return "powershell"
    if name == "cmd" and flag_lc == "/c":
        return "cmd"
    return None

def _classify_shell_name(shell: str) -> str:
    return Path(shell.replace("\\", "/")).stem.lower()

def _can_skip_shell_flag(shell: str, flag: str) -> bool:
    return _classify_shell_name(shell) in {"pwsh", "powershell"} and flag.lower() == "-noprofile"

def _extract_apply_patch_from_shell(script: str) -> tuple[str, str | None] | None:
    first_line, separator, rest = script.partition("\n")
    if separator == "":
        return None
    redirect_index = first_line.find("<<")
    if redirect_index < 0 or first_line.find("<<<") >= 0:
        return None
    if first_line.find("<<", redirect_index + 2) >= 0:
        return None

    command_text = first_line[:redirect_index].strip()
    heredoc_start = first_line[redirect_index + 2 :].strip()
    delimiter = _parse_single_shell_word(heredoc_start)
    if delimiter is None:
        return None

    command_parts = _parse_apply_patch_heredoc_command(command_text)
    if command_parts is None:
        return None
    workdir = None if command_parts == _NO_WORKDIR else command_parts

    lines = rest.splitlines()
    terminator_index = next((index for index, line in enumerate(lines) if line == delimiter), None)
    if terminator_index is None:
        return None
    if any(line.strip() for line in lines[terminator_index + 1 :]):
        return None
    return "\n".join(lines[:terminator_index]), workdir

def _parse_single_shell_word(value: str) -> str | None:
    try:
        words = shlex.split(value, posix=True)
    except ValueError:
        return None
    if len(words) != 1 or words[0] == "":
        return None
    return words[0]

def _parse_apply_patch_heredoc_command(command_text: str) -> str | None:
    try:
        words = shlex.split(command_text, posix=True)
    except ValueError:
        return None
    if words in (["apply_patch"], ["applypatch"]):
        return _NO_WORKDIR
    if len(words) == 4 and words[0] == "cd" and words[2] == "&&" and words[3] in APPLY_PATCH_COMMANDS:
        return words[1]
    return None

_NO_WORKDIR = "__pycodex_no_workdir__"

def _read_optional_text(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

def _workspace_root_for_cwd(cwd: Path) -> Path:
    resolved = cwd.resolve()
    current = resolved
    home = Path.home().resolve()
    while True:
        if current == home:
            return resolved
        if (current / ".git").exists():
            return current
        if current.parent == current:
            return resolved
        current = current.parent

def _apply_patch_path_escape_error(path: Path | None, workspace_root: Path) -> ApplyPatchError | None:
    if path is None:
        return None
    try:
        resolved_path = path.resolve(strict=False)
        resolved_root = workspace_root.resolve(strict=False)
    except OSError as error:
        return ApplyPatchError.io_error(f"Failed to resolve {path}", error)
    if resolved_path == resolved_root or resolved_path.is_relative_to(resolved_root):
        return None
    return ApplyPatchError.compute_replacements(
        f"apply_patch path escapes workspace root {resolved_root}: {path}"
    )

__all__ = ["MaybeApplyPatch", "maybe_parse_apply_patch", "maybe_parse_apply_patch_verified", "verify_apply_patch_args"]
