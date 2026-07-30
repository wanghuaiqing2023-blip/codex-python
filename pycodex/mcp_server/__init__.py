"""Standalone Codex MCP server ported from ``codex-mcp-server``."""

from __future__ import annotations

import asyncio
import json
from typing import Any, BinaryIO, TextIO

from .codex_tool_config import CodexToolCallParam, CodexToolCallReplyParam
from .exec_approval import ExecApprovalElicitRequestParams, ExecApprovalResponse
from .patch_approval import PatchApprovalElicitRequestParams, PatchApprovalResponse


CHANNEL_CAPACITY = 128
DEFAULT_ANALYTICS_ENABLED = True
OTEL_SERVICE_NAME = "codex_mcp_server"


async def run_main(
    *,
    stdin: TextIO | BinaryIO,
    stdout: TextIO,
    stderr: TextIO,
    strict_config: bool = False,
    processor: Any | None = None,
) -> None:
    from .message_processor import MessageProcessor
    from .outgoing_message import OutgoingMessageSender

    outgoing = OutgoingMessageSender()
    processor = processor or MessageProcessor(outgoing)

    async def write_messages() -> None:
        while True:
            message = await outgoing.receive()
            if message is _STOP:
                outgoing.task_done()
                return
            stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
            stdout.flush()
            outgoing.task_done()

    writer = asyncio.create_task(write_messages())
    try:
        while True:
            line = await asyncio.to_thread(stdin.readline)
            if line in {"", b""}:
                break
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"Failed to deserialize JSON-RPC message: {exc}", file=stderr)
                continue
            if not isinstance(message, dict):
                print("Failed to deserialize JSON-RPC message: expected object", file=stderr)
                continue
            await processor.process_message(message)
        await processor.wait_pending()
    finally:
        await processor.shutdown()
        await outgoing._queue.put(_STOP)
        await writer


_STOP = object()

__all__ = [
    "CodexToolCallParam",
    "CodexToolCallReplyParam",
    "ExecApprovalElicitRequestParams",
    "ExecApprovalResponse",
    "PatchApprovalElicitRequestParams",
    "PatchApprovalResponse",
    "run_main",
]
