"""Python port surface for Rust ``codex-debug-client``."""

from __future__ import annotations

from .client import (
    AppServerClient,
    build_thread_resume_params,
    build_thread_start_params,
    send_jsonrpc_response,
    send_with_stdin,
)
from .commands import InputAction, ParseError, ParseErrorKind, UserCommand, parse_input
from .main import Cli, drain_events, handle_command, main, parse_approval_policy, parse_args, print_help, run
from .output import LabelColor, Output, PromptState
from .reader import (
    ACCEPT,
    COMMAND_APPROVAL_METHOD,
    DECLINE,
    FILE_CHANGE_APPROVAL_METHOD,
    ITEM_COMPLETED_METHOD,
    emit_filtered_item,
    handle_filtered_notification,
    handle_response,
    handle_server_request,
    process_server_line,
    read_server_lines,
    send_response,
    start_reader,
    write_multiline,
)
from .state import PendingRequest, ReaderEvent, State


__all__ = [
    "ACCEPT",
    "AppServerClient",
    "COMMAND_APPROVAL_METHOD",
    "Cli",
    "DECLINE",
    "FILE_CHANGE_APPROVAL_METHOD",
    "InputAction",
    "ITEM_COMPLETED_METHOD",
    "LabelColor",
    "Output",
    "PendingRequest",
    "ParseError",
    "ParseErrorKind",
    "PromptState",
    "ReaderEvent",
    "State",
    "UserCommand",
    "build_thread_resume_params",
    "build_thread_start_params",
    "drain_events",
    "emit_filtered_item",
    "handle_command",
    "handle_filtered_notification",
    "handle_response",
    "handle_server_request",
    "main",
    "parse_args",
    "parse_approval_policy",
    "parse_input",
    "print_help",
    "process_server_line",
    "read_server_lines",
    "run",
    "send_response",
    "send_jsonrpc_response",
    "send_with_stdin",
    "start_reader",
    "write_multiline",
]
