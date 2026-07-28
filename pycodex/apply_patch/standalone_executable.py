"""Standalone apply_patch process adapter owned by ``standalone_executable.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import apply_patch_action_to_disk
from .invocation import APPLY_PATCH_COMMANDS, maybe_parse_apply_patch, verify_apply_patch_args

@dataclass(frozen=True)
class StandaloneApplyPatchResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""

def run_main(
    args: tuple[object, ...] | list[object],
    stdin_text: str = "",
    cwd: Path | str | None = None,
) -> StandaloneApplyPatchResult:
    """Semantic mirror of ``codex-apply-patch/src/standalone_executable.rs::run_main``.

    The Rust entrypoint accepts exactly one UTF-8 patch argument or reads the
    patch body from stdin. This Python adapter returns process-shaped
    stdout/stderr/exit-code data without spawning a subprocess.
    """

    arg_values = tuple(args)
    if not arg_values:
        if stdin_text == "":
            return StandaloneApplyPatchResult(
                2,
                stderr="Usage: apply_patch 'PATCH'\n       echo 'PATCH' | apply_patch\n",
            )
        patch_arg = stdin_text
    else:
        first = arg_values[0]
        if not isinstance(first, str):
            return StandaloneApplyPatchResult(
                1,
                stderr="Error: apply_patch requires a UTF-8 PATCH argument.\n",
            )
        patch_arg = first

    if len(arg_values) > 1:
        return StandaloneApplyPatchResult(
            2,
            stderr="Error: apply_patch accepts exactly one argument.\n",
        )

    root = Path.cwd() if cwd is None else Path(cwd)
    parsed = maybe_parse_apply_patch((APPLY_PATCH_COMMANDS[0], patch_arg))
    if parsed.type == "patch_parse_error" and parsed.error is not None:
        return StandaloneApplyPatchResult(1, stderr=f"{parsed.error}\n")
    if parsed.type != "body" or parsed.body is None:
        return StandaloneApplyPatchResult(1, stderr="apply_patch handler received invalid patch input\n")
    verified = verify_apply_patch_args(parsed.body, root)
    if verified.type == "body" and verified.body is not None:
        try:
            return StandaloneApplyPatchResult(0, stdout=apply_patch_action_to_disk(verified.body))
        except Exception as exc:
            return StandaloneApplyPatchResult(1, stderr=f"{exc}\n")
    if verified.error is not None:
        return StandaloneApplyPatchResult(1, stderr=f"{verified.error}\n")
    return StandaloneApplyPatchResult(1, stderr="apply_patch handler received invalid patch input\n")

__all__ = ["StandaloneApplyPatchResult", "run_main"]
