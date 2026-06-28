"""Reusable automation helpers for Python TUI parity tests."""

from .assertions import assert_no_duplicate
from .assertions import assert_status_ready
from .assertions import assert_status_working
from .assertions import assert_text_present
from .events import agent_delta
from .events import item_completed_command
from .events import item_started_command
from .events import mcp_server_status_updated
from .events import reasoning_raw_delta
from .events import reasoning_summary_delta
from .events import reasoning_summary_part_added
from .events import thread_closed
from .events import thread_token_usage_updated
from .events import turn_completed
from .events import turn_failed
from .events import turn_started
from .native_compare import DEFAULT_NATIVE_CODEX_EXE
from .native_compare import NATIVE_CODEX_EXE_ENV
from .native_compare import RUN_EXPERIMENTAL_CONPTY_ENV
from .native_compare import RUN_NATIVE_COMPARISON_ENV
from .native_compare import RUN_VERIFIED_CONPTY_ENV
from .native_compare import InteractiveTuiComparisonCapability
from .native_compare import NativeComparisonLayer
from .native_compare import TuiComparisonCommand
from .native_compare import TuiProcessTranscript
from .native_compare import build_inline_tui_command
from .native_compare import build_rust_python_inline_pair
from .native_compare import interactive_tui_comparison_capability
from .native_compare import native_codex_exe_from_env
from .native_compare import native_comparison_enabled
from .native_compare import normalize_tui_text
from .native_compare import run_piped_tui_command
from .native_compare import run_windows_conpty_tui_command
from .runtime import ManualActiveThreadRuntime
from .textual_scenarios import TextualScenario
from .textual_scenarios import start_textual_scenario
from .terminal import TerminalCapture
from .terminal import TtyInput
from .terminal import strip_ansi

__all__ = [
    "ManualActiveThreadRuntime",
    "DEFAULT_NATIVE_CODEX_EXE",
    "NATIVE_CODEX_EXE_ENV",
    "RUN_EXPERIMENTAL_CONPTY_ENV",
    "RUN_NATIVE_COMPARISON_ENV",
    "RUN_VERIFIED_CONPTY_ENV",
    "InteractiveTuiComparisonCapability",
    "NativeComparisonLayer",
    "TerminalCapture",
    "TextualScenario",
    "TuiComparisonCommand",
    "TuiProcessTranscript",
    "TtyInput",
    "agent_delta",
    "assert_no_duplicate",
    "assert_status_ready",
    "assert_status_working",
    "assert_text_present",
    "build_inline_tui_command",
    "build_rust_python_inline_pair",
    "interactive_tui_comparison_capability",
    "item_completed_command",
    "item_started_command",
    "mcp_server_status_updated",
    "native_codex_exe_from_env",
    "native_comparison_enabled",
    "normalize_tui_text",
    "reasoning_raw_delta",
    "reasoning_summary_delta",
    "reasoning_summary_part_added",
    "run_piped_tui_command",
    "run_windows_conpty_tui_command",
    "start_textual_scenario",
    "strip_ansi",
    "thread_closed",
    "thread_token_usage_updated",
    "turn_completed",
    "turn_failed",
    "turn_started",
]
