"""Tool executor contract ported from ``codex-rs/tools/src/tool_executor.rs``."""

from __future__ import annotations

from typing import Any, Protocol, TypeVar, runtime_checkable

from pycodex.core.tools.registry import ToolExposure
from pycodex.protocol import ToolName

from .function_call_error import FunctionCallError
from .tool_output import ToolOutput

InvocationT = TypeVar("InvocationT")


@runtime_checkable
class ToolExecutor(Protocol[InvocationT]):
    def tool_name(self) -> ToolName:
        """Return the concrete tool name handled by this runtime instance."""

    def spec(self) -> Any:
        """Return the model-visible tool spec."""

    def exposure(self) -> ToolExposure:
        """Return where the tool is exposed to the model."""
        return ToolExposure.DIRECT

    def supports_parallel_tool_calls(self) -> bool:
        """Whether this executor can be called in parallel."""
        return False

    async def handle(self, invocation: InvocationT) -> ToolOutput:
        """Execute the tool invocation or raise ``FunctionCallError``."""
        raise FunctionCallError.fatal("ToolExecutor.handle() is not implemented")


__all__ = ["ToolExposure", "ToolExecutor"]
