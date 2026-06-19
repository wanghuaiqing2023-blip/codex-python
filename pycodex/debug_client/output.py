"""Output coordination for Rust ``codex-debug-client/src/output.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
import sys
from threading import RLock
from typing import TextIO


class LabelColor(str, Enum):
    ASSISTANT = "Assistant"
    TOOL = "Tool"
    TOOL_META = "ToolMeta"
    THREAD = "Thread"


@dataclass
class PromptState:
    thread_id: str | None = None
    visible: bool = False


class Output:
    def __init__(
        self,
        jsonl_file: TextIO | None = None,
        *,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
        color: bool | None = None,
    ) -> None:
        self._lock = RLock()
        self._prompt = PromptState()
        self._stdout = stdout if stdout is not None else sys.stdout
        self._stderr = stderr if stderr is not None else sys.stderr
        self._jsonl_file = jsonl_file
        if color is None:
            no_color = "NO_COLOR" in os.environ
            color = not no_color and bool(self._stdout.isatty()) and bool(self._stderr.isatty())
        self.color = bool(color)

    @classmethod
    def new(
        cls,
        jsonl_file: TextIO | None = None,
        *,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
        color: bool | None = None,
    ) -> "Output":
        return cls(jsonl_file, stdout=stdout, stderr=stderr, color=color)

    def server_json_line(self, line: str, filtered_output: bool) -> None:
        with self._lock:
            if self._jsonl_file is not None:
                self._jsonl_file.write(f"{line}\n")
                self._jsonl_file.flush()
            if self._jsonl_file is None and not filtered_output:
                self._clear_prompt_line_locked()
                self._stdout.write(f"{line}\n")
                self._stdout.flush()
                self._redraw_prompt_locked()

    def server_line(self, line: str) -> None:
        with self._lock:
            self._clear_prompt_line_locked()
            self._stdout.write(f"{line}\n")
            self._stdout.flush()
            self._redraw_prompt_locked()

    def client_line(self, line: str) -> None:
        with self._lock:
            self._clear_prompt_line_locked()
            self._stderr.write(f"{line}\n")
            self._stderr.flush()

    def prompt(self, thread_id: str) -> None:
        with self._lock:
            self._set_prompt_locked(thread_id)
            self._write_prompt_locked()

    def set_prompt(self, thread_id: str) -> None:
        with self._lock:
            self._set_prompt_locked(thread_id)

    def format_label(self, label: str, color: LabelColor) -> str:
        if not self.color:
            return str(label)
        code = {
            LabelColor.ASSISTANT: "32",
            LabelColor.TOOL: "36",
            LabelColor.TOOL_META: "33",
            LabelColor.THREAD: "34",
        }[LabelColor(color)]
        return f"\x1b[{code}m{label}\x1b[0m"

    @property
    def prompt_state(self) -> PromptState:
        return PromptState(self._prompt.thread_id, self._prompt.visible)

    def _clear_prompt_line_locked(self) -> None:
        if self._prompt.visible:
            self._stderr.write("\n")
            self._stderr.flush()
            self._prompt.visible = False

    def _redraw_prompt_locked(self) -> None:
        if self._prompt.thread_id is not None:
            self._write_prompt_locked()

    def _set_prompt_locked(self, thread_id: str) -> None:
        self._prompt.thread_id = str(thread_id)

    def _write_prompt_locked(self) -> None:
        if self._prompt.thread_id is None:
            return
        self._stderr.write(f"({self._prompt.thread_id})> ")
        self._stderr.flush()
        self._prompt.visible = True


__all__ = ["LabelColor", "Output", "PromptState"]
