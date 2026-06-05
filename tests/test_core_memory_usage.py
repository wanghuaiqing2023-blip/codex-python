import json
import unittest
from pathlib import Path

from pycodex.core.memory_usage import (
    MEMORIES_USAGE_METRIC,
    MemoriesUsageKind,
    emit_metric_for_tool_read,
    memory_kind_for_path,
    memory_usage_kinds_from_command,
    shell_command_for_invocation,
)
from pycodex.core.shell import Shell, ShellType
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.registry import ToolCallSource, ToolInvocation
from pycodex.protocol import ToolName


class Telemetry:
    def __init__(self) -> None:
        self.calls = []

    def counter(self, metric, inc, tags):
        self.calls.append((metric, inc, tuple(tags)))


def invocation(name: str, arguments: dict) -> ToolInvocation:
    return ToolInvocation(
        call_id="call-1",
        tool_name=ToolName.plain(name),
        payload=ToolPayload.function(json.dumps(arguments)),
        source=ToolCallSource.direct(),
    )


class MemoryUsageTests(unittest.TestCase):
    def test_memory_kind_for_path_matches_rust_substrings(self) -> None:
        self.assertIs(
            memory_kind_for_path("/home/me/memories/MEMORY.md"),
            MemoriesUsageKind.MEMORY_MD,
        )
        self.assertIs(
            memory_kind_for_path("/home/me/memories/memory_summary.md"),
            MemoriesUsageKind.MEMORY_SUMMARY,
        )
        self.assertIs(
            memory_kind_for_path("/home/me/memories/raw_memories.md"),
            MemoriesUsageKind.RAW_MEMORIES,
        )
        self.assertIs(
            memory_kind_for_path("/home/me/memories/rollout_summaries/a.md"),
            MemoriesUsageKind.ROLLOUT_SUMMARIES,
        )
        self.assertIs(
            memory_kind_for_path("/home/me/memories/skills/python.md"),
            MemoriesUsageKind.SKILLS,
        )
        self.assertIsNone(memory_kind_for_path("/home/me/README.md"))

    def test_memory_usage_kinds_from_safe_read_command(self) -> None:
        self.assertEqual(
            memory_usage_kinds_from_command(("cat", "/home/me/memories/MEMORY.md")),
            (MemoriesUsageKind.MEMORY_MD,),
        )
        self.assertEqual(
            memory_usage_kinds_from_command(("python", "-c", "print('memories/MEMORY.md')")),
            (),
        )

    def test_memory_usage_kinds_unwraps_shell_command(self) -> None:
        self.assertEqual(
            memory_usage_kinds_from_command(("bash", "-lc", "cat /home/me/memories/raw_memories.md")),
            (MemoriesUsageKind.RAW_MEMORIES,),
        )

    def test_shell_command_for_invocation_extracts_shell_command(self) -> None:
        item = invocation(
            "shell_command",
            {"command": "cat /home/me/memories/MEMORY.md", "workdir": "/tmp/work"},
        )

        command = shell_command_for_invocation(
            item,
            session_shell=Shell(ShellType.BASH, "/bin/bash"),
            resolve_path=lambda value: Path(value or "/fallback"),
        )

        self.assertIsNotNone(command)
        self.assertEqual(command.command, ("/bin/bash", "-c", "cat /home/me/memories/MEMORY.md"))
        self.assertEqual(command.cwd, Path("/tmp/work"))

    def test_shell_command_login_disabled_yields_empty_command(self) -> None:
        item = invocation("shell_command", {"command": "cat memories/MEMORY.md", "login": True})

        command = shell_command_for_invocation(
            item,
            session_shell=Shell(ShellType.BASH, "/bin/bash"),
            allow_login_shell=False,
            resolve_path=lambda value: Path("/tmp/work"),
        )

        self.assertIsNotNone(command)
        self.assertEqual(command.command, ())
        self.assertEqual(memory_usage_kinds_from_command(command.command), ())

    def test_shell_command_for_invocation_extracts_exec_command(self) -> None:
        item = invocation("exec_command", {"cmd": "cat /home/me/memories/memory_summary.md"})

        command = shell_command_for_invocation(
            item,
            session_shell=Shell(ShellType.BASH, "/bin/bash"),
            resolve_path=lambda value: Path("/tmp/work"),
        )

        self.assertIsNotNone(command)
        self.assertEqual(command.command, ("/bin/bash", "-c", "cat /home/me/memories/memory_summary.md"))
        self.assertEqual(command.cwd, Path("/tmp/work"))

    def test_shell_command_for_invocation_ignores_other_tools(self) -> None:
        item = invocation("other_tool", {"command": "cat /home/me/memories/MEMORY.md"})

        self.assertIsNone(shell_command_for_invocation(item, session_shell=Shell(ShellType.BASH, "/bin/bash")))

    def test_emit_metric_for_tool_read_records_each_kind(self) -> None:
        telemetry = Telemetry()
        item = invocation(
            "shell_command",
            {"command": "cat /home/me/memories/MEMORY.md /home/me/memories/skills/python.md"},
        )

        kinds = emit_metric_for_tool_read(
            item,
            True,
            telemetry,
            session_shell=Shell(ShellType.BASH, "/bin/bash"),
        )

        self.assertEqual(kinds, (MemoriesUsageKind.MEMORY_MD, MemoriesUsageKind.SKILLS))
        self.assertEqual(
            telemetry.calls,
            [
                (
                    MEMORIES_USAGE_METRIC,
                    1,
                    (("kind", "memory_md"), ("tool", "shell_command"), ("success", "true")),
                ),
                (
                    MEMORIES_USAGE_METRIC,
                    1,
                    (("kind", "skills"), ("tool", "shell_command"), ("success", "true")),
                ),
            ],
        )

    def test_emit_metric_for_tool_read_ignores_non_memory_reads(self) -> None:
        telemetry = Telemetry()
        item = invocation("shell_command", {"command": "cat /tmp/README.md"})

        kinds = emit_metric_for_tool_read(
            item,
            False,
            telemetry,
            session_shell=Shell(ShellType.BASH, "/bin/bash"),
        )

        self.assertEqual(kinds, ())
        self.assertEqual(telemetry.calls, [])


if __name__ == "__main__":
    unittest.main()
