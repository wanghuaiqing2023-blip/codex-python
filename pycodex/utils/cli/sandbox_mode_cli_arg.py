"""Sandbox CLI enum from Rust ``sandbox_mode_cli_arg.rs``."""

from enum import Enum


class SandboxModeCliArg(Enum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"

    def to_sandbox_mode(self) -> str:
        return self.value


__all__ = ["SandboxModeCliArg"]
