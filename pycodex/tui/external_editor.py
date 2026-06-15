"""External editor integration for Rust ``codex-tui::external_editor``."""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="external_editor",
    source="codex/codex-rs/tui/src/external_editor.rs",
    status="complete",
)


class EditorError(Enum):
    MISSING_EDITOR = "neither VISUAL nor EDITOR is set"
    PARSE_FAILED = "failed to parse editor command"
    EMPTY_COMMAND = "editor command is empty"


class ExternalEditorError(RuntimeError):
    pass


def resolve_windows_program(program: str) -> Path:
    """Resolve a Windows executable respecting PATHEXT when possible."""

    resolved = shutil.which(program)
    return Path(resolved) if resolved else Path(program)


def resolve_editor_command(env: Optional[Dict[str, str]] = None) -> List[str]:
    """Resolve editor command from ``VISUAL`` first, then ``EDITOR``."""

    source = os.environ if env is None else env
    raw = source.get("VISUAL")
    if raw is None:
        raw = source.get("EDITOR")
    if raw is None:
        raise ExternalEditorError(EditorError.MISSING_EDITOR.value)

    try:
        parts = shlex.split(raw, posix=(os.name != "nt"))
    except ValueError as exc:
        raise ExternalEditorError(EditorError.PARSE_FAILED.value) from exc

    if not parts:
        raise ExternalEditorError(EditorError.EMPTY_COMMAND.value)
    return parts


async def run_editor(seed: str, editor_cmd: Sequence[str]) -> str:
    """Write seed to a temp ``.md`` file, run editor, return updated content."""

    if not editor_cmd:
        raise ExternalEditorError("editor command is empty")

    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
            tmp_path = handle.name
            handle.write(seed)

        program = os.fspath(resolve_windows_program(editor_cmd[0])) if os.name == "nt" else editor_cmd[0]
        cmd = [program, *editor_cmd[1:], tmp_path]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=None,
            stdout=None,
            stderr=None,
        )
        status = await process.wait()
        if status != 0:
            raise ExternalEditorError(f"editor exited with status {status}")

        return Path(tmp_path).read_text(encoding="utf-8")
    finally:
        if tmp_path is not None:
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass


@dataclass
class EnvGuard:
    visual: Optional[str]
    editor: Optional[str]

    @classmethod
    def new(cls) -> "EnvGuard":
        return cls(visual=os.environ.get("VISUAL"), editor=os.environ.get("EDITOR"))

    def restore(self) -> None:
        restore_env("VISUAL", self.visual)
        restore_env("EDITOR", self.editor)


def drop(value: Any) -> None:
    if isinstance(value, EnvGuard):
        value.restore()


def restore_env(key: str, value: Optional[str]) -> None:
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value


__all__ = [
    "EditorError",
    "EnvGuard",
    "ExternalEditorError",
    "RUST_MODULE",
    "drop",
    "resolve_editor_command",
    "resolve_windows_program",
    "restore_env",
    "run_editor",
]
