"""Error surface owned by ``core::unified_exec::errors``."""

from __future__ import annotations

from pycodex.protocol import ExecToolCallOutput


class UnifiedExecError(Exception):
    CREATE_PROCESS = "CreateProcess"
    PROCESS_FAILED = "ProcessFailed"
    UNKNOWN_PROCESS_ID = "UnknownProcessId"
    WRITE_TO_STDIN = "WriteToStdin"
    STDIN_CLOSED = "StdinClosed"
    MISSING_COMMAND_LINE = "MissingCommandLine"
    SANDBOX_DENIED = "SandboxDenied"

    def __init__(
        self,
        kind: str,
        *,
        message: str | None = None,
        process_id: int | None = None,
        output: ExecToolCallOutput | None = None,
    ) -> None:
        self.kind = kind
        self.message = message
        self.process_id = process_id
        self.output = output
        super().__init__(self._render_message())

    @classmethod
    def create_process(cls, message: str) -> "UnifiedExecError":
        return cls(cls.CREATE_PROCESS, message=message)

    @classmethod
    def process_failed(cls, message: str) -> "UnifiedExecError":
        return cls(cls.PROCESS_FAILED, message=message)

    @classmethod
    def unknown_process_id(cls, process_id: int) -> "UnifiedExecError":
        return cls(cls.UNKNOWN_PROCESS_ID, process_id=process_id)

    @classmethod
    def write_to_stdin(cls) -> "UnifiedExecError":
        return cls(cls.WRITE_TO_STDIN)

    @classmethod
    def stdin_closed(cls) -> "UnifiedExecError":
        return cls(cls.STDIN_CLOSED)

    @classmethod
    def missing_command_line(cls) -> "UnifiedExecError":
        return cls(cls.MISSING_COMMAND_LINE)

    @classmethod
    def sandbox_denied(
        cls,
        message: str,
        output: ExecToolCallOutput,
    ) -> "UnifiedExecError":
        return cls(cls.SANDBOX_DENIED, message=message, output=output)

    def _render_message(self) -> str:
        if self.kind == self.CREATE_PROCESS:
            return f"Failed to create unified exec process: {self.message or ''}"
        if self.kind == self.PROCESS_FAILED:
            return f"Unified exec process failed: {self.message or ''}"
        if self.kind == self.UNKNOWN_PROCESS_ID:
            return f"Unknown process id {self.process_id}"
        if self.kind == self.WRITE_TO_STDIN:
            return "failed to write to stdin"
        if self.kind == self.STDIN_CLOSED:
            return (
                "stdin is closed for this session; rerun exec_command with tty=true "
                "to keep stdin open"
            )
        if self.kind == self.MISSING_COMMAND_LINE:
            return "missing command line for unified exec request"
        if self.kind == self.SANDBOX_DENIED:
            return f"Command denied by sandbox: {self.message or ''}"
        return self.kind


__all__ = ["UnifiedExecError"]
