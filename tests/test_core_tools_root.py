from __future__ import annotations

import unittest
from datetime import timedelta
from pathlib import Path

from pycodex.core.shell import Shell, ShellType
from pycodex.core.tools import (
    TELEMETRY_PREVIEW_MAX_BYTES,
    TELEMETRY_PREVIEW_MAX_LINES,
    TELEMETRY_PREVIEW_TRUNCATION_NOTICE,
    ToolRouter,
    ToolUserShellType,
    flat_tool_name,
    format_exec_output_for_model,
    format_exec_output_str,
    tool_user_shell_type,
)
from pycodex.core.tools.context import (
    TELEMETRY_PREVIEW_MAX_BYTES as CONTEXT_TELEMETRY_PREVIEW_MAX_BYTES,
    TELEMETRY_PREVIEW_MAX_LINES as CONTEXT_TELEMETRY_PREVIEW_MAX_LINES,
    TELEMETRY_PREVIEW_TRUNCATION_NOTICE as CONTEXT_TELEMETRY_PREVIEW_TRUNCATION_NOTICE,
)
from pycodex.core.tools.router import ToolRouter as RouterToolRouter
from pycodex.protocol import ExecToolCallOutput, StreamOutput, ToolName, TruncationPolicyConfig


class CoreToolsRootTests(unittest.TestCase):
    def test_root_reexports_telemetry_preview_constants_and_router(self) -> None:
        # Rust source: codex-rs/core/src/tools/mod.rs.
        self.assertEqual(TELEMETRY_PREVIEW_MAX_BYTES, CONTEXT_TELEMETRY_PREVIEW_MAX_BYTES)
        self.assertEqual(TELEMETRY_PREVIEW_MAX_LINES, CONTEXT_TELEMETRY_PREVIEW_MAX_LINES)
        self.assertEqual(
            TELEMETRY_PREVIEW_TRUNCATION_NOTICE,
            CONTEXT_TELEMETRY_PREVIEW_TRUNCATION_NOTICE,
        )
        self.assertIs(ToolRouter, RouterToolRouter)

    def test_flat_tool_name_is_available_at_tools_root(self) -> None:
        # Rust source: codex-rs/core/src/tools/mod.rs::flat_tool_name.
        self.assertEqual(flat_tool_name(ToolName.plain("echo")), "echo")
        self.assertEqual(
            flat_tool_name(ToolName.namespaced("functions.", "echo")),
            "functions.echo",
        )

    def test_tool_user_shell_type_maps_shell_types(self) -> None:
        # Rust source: codex-rs/core/src/tools/mod.rs::tool_user_shell_type.
        cases = [
            (ShellType.ZSH, ToolUserShellType.ZSH),
            (ShellType.BASH, ToolUserShellType.BASH),
            (ShellType.POWERSHELL, ToolUserShellType.POWERSHELL),
            (ShellType.SH, ToolUserShellType.SH),
            (ShellType.CMD, ToolUserShellType.CMD),
        ]
        for shell_type, expected in cases:
            with self.subTest(shell_type=shell_type):
                self.assertEqual(
                    tool_user_shell_type(Shell(shell_type, Path(shell_type.value))),
                    expected,
                )

        with self.assertRaises(TypeError):
            tool_user_shell_type(object())  # type: ignore[arg-type]

    def test_format_exec_output_helpers_are_available_at_tools_root(self) -> None:
        # Rust source: codex-rs/core/src/tools/mod.rs::format_exec_output_for_model.
        exec_output = ExecToolCallOutput(
            exit_code=124,
            aggregated_output=StreamOutput.new("partial output"),
            duration=timedelta(milliseconds=1250),
            timed_out=True,
        )

        self.assertEqual(
            format_exec_output_for_model(exec_output, TruncationPolicyConfig.bytes(1024)),
            "Exit code: 124\n"
            "Wall time: 1.3 seconds\n"
            "Output:\n"
            "command timed out after 1250 milliseconds\npartial output",
        )
        self.assertEqual(
            format_exec_output_str(exec_output, TruncationPolicyConfig.bytes(1024)),
            "command timed out after 1250 milliseconds\npartial output",
        )


if __name__ == "__main__":
    unittest.main()
