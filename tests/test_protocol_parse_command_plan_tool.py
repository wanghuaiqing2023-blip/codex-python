import unittest
from pathlib import Path

import pycodex.protocol as protocol
from pycodex.protocol import (
    EventMsg,
    ExecCommandBeginEvent,
    ParsedCommand,
    PlanItemArg,
    StepStatus,
    UpdatePlanArgs,
)


class ProtocolParseCommandPlanToolTests(unittest.TestCase):
    def test_parsed_command_round_trips_tagged_shapes(self):
        read = ParsedCommand.read("cat src/app.py", "app.py", Path("src/app.py"))
        list_files = ParsedCommand.list_files("rg --files src", "src")
        search = ParsedCommand.search("rg TODO src", query="TODO", path="src")
        unknown = ParsedCommand.unknown("git status")

        self.assertEqual(ParsedCommand.from_mapping(read.to_mapping()), read)
        self.assertEqual(ParsedCommand.from_mapping(list_files.to_mapping()), list_files)
        self.assertEqual(ParsedCommand.from_mapping(search.to_mapping()), search)
        self.assertEqual(ParsedCommand.from_mapping(unknown.to_mapping()), unknown)
        self.assertEqual(read.to_mapping()["type"], "read")

    def test_parsed_command_matches_rust_option_field_serialization(self):
        # Rust parity: codex-protocol/src/parse_command.rs
        # ParsedCommand uses serde tagged enum variants with Option<String>
        # fields and no skip_serializing_if, so None serializes as JSON null.
        self.assertEqual(
            ParsedCommand.list_files("rg --files").to_mapping(),
            {"type": "list_files", "cmd": "rg --files", "path": None},
        )
        self.assertEqual(
            ParsedCommand.search("rg TODO").to_mapping(),
            {"type": "search", "cmd": "rg TODO", "query": None, "path": None},
        )
        self.assertEqual(
            ParsedCommand.from_mapping({"type": "list_files", "cmd": "rg --files", "path": None}),
            ParsedCommand.list_files("rg --files"),
        )
        self.assertEqual(
            ParsedCommand.from_mapping({"type": "search", "cmd": "rg TODO", "query": None, "path": None}),
            ParsedCommand.search("rg TODO"),
        )

    def test_parsed_command_rejects_non_rust_variant_shapes(self):
        with self.assertRaisesRegex(TypeError, "cmd must be a string"):
            ParsedCommand.unknown(123)

        with self.assertRaisesRegex(TypeError, "read command name must be a string"):
            ParsedCommand("read", cmd="cat file.txt", name=None, path="file.txt")

        with self.assertRaisesRegex(TypeError, "read command path must be a string or Path"):
            ParsedCommand("read", cmd="cat file.txt", name="file.txt", path=None)

        with self.assertRaisesRegex(ValueError, "read command cannot include query"):
            ParsedCommand("read", cmd="cat file.txt", name="file.txt", path="file.txt", query="needle")

        with self.assertRaisesRegex(ValueError, "list_files command cannot include name"):
            ParsedCommand("list_files", cmd="rg --files", name="files")

        with self.assertRaisesRegex(TypeError, "list_files command path must be a string or None"):
            ParsedCommand("list_files", cmd="rg --files", path=Path("src"))

        with self.assertRaisesRegex(ValueError, "search command cannot include name"):
            ParsedCommand("search", cmd="rg needle", name="needle", query="needle")

        with self.assertRaisesRegex(TypeError, "search command query must be a string or None"):
            ParsedCommand("search", cmd="rg needle", query=123)

        with self.assertRaisesRegex(ValueError, "unknown command cannot include name, path, or query"):
            ParsedCommand("unknown", cmd="git status", path=".")

        with self.assertRaisesRegex(ValueError, "unknown parsed command type"):
            ParsedCommand("execute", cmd="run")

    def test_plan_tool_args_round_trip(self):
        update = UpdatePlanArgs(
            explanation="working",
            plan=(
                PlanItemArg("inspect", StepStatus.COMPLETED),
                PlanItemArg("implement", StepStatus.IN_PROGRESS),
                PlanItemArg("verify", StepStatus.PENDING),
            ),
        )

        self.assertEqual(UpdatePlanArgs.from_mapping(update.to_mapping()), update)
        self.assertEqual(update.to_mapping()["plan"][1]["status"], "in_progress")
        self.assertEqual(UpdatePlanArgs.from_mapping({"plan": []}), UpdatePlanArgs(plan=()))
        self.assertEqual(UpdatePlanArgs(plan=()).to_mapping(), {"plan": []})
        with self.assertRaisesRegex(ValueError, "unknown field"):
            UpdatePlanArgs.from_mapping({"plan": [], "unexpected": True})

    def test_plan_tool_args_match_rust_serde_boundaries(self):
        # Rust: codex-protocol/src/plan_tool.rs
        self.assertEqual(
            [status.value for status in StepStatus],
            ["pending", "in_progress", "completed"],
        )
        self.assertIs(protocol.StepStatus, StepStatus)
        self.assertIs(protocol.PlanItemArg, PlanItemArg)
        self.assertIs(protocol.UpdatePlanArgs, UpdatePlanArgs)

        with self.assertRaisesRegex(ValueError, "unknown field"):
            PlanItemArg.from_mapping({"step": "inspect", "status": "pending", "extra": True})

        with self.assertRaisesRegex(TypeError, "plan must be a list"):
            UpdatePlanArgs.from_mapping({"plan": ()})

        with self.assertRaisesRegex(KeyError, "plan"):
            UpdatePlanArgs.from_mapping({"explanation": "missing plan"})

        with self.assertRaisesRegex(TypeError, "explanation must be a string"):
            UpdatePlanArgs.from_mapping({"explanation": 123, "plan": []})

    def test_plan_tool_args_reject_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "step must be a string"):
            PlanItemArg(123, StepStatus.PENDING)

        self.assertEqual(PlanItemArg("inspect", "pending").status, StepStatus.PENDING)

        with self.assertRaisesRegex(ValueError, "not a valid StepStatus"):
            PlanItemArg("inspect", "unknown")

        with self.assertRaisesRegex(TypeError, "plan must be a list or tuple"):
            UpdatePlanArgs("inspect")

        with self.assertRaisesRegex(TypeError, "plan entries must be PlanItemArg"):
            UpdatePlanArgs(({"step": "inspect", "status": "pending"},))

        with self.assertRaisesRegex(TypeError, "explanation must be a string or None"):
            UpdatePlanArgs((), explanation=123)

    def test_event_msg_parses_plan_update(self):
        msg = EventMsg.from_mapping(
            {
                "type": "plan_update",
                "explanation": "next",
                "plan": [{"step": "port", "status": "in_progress"}],
            }
        )

        self.assertEqual(msg.payload, UpdatePlanArgs((PlanItemArg("port", StepStatus.IN_PROGRESS),), "next"))
        self.assertEqual(msg.to_mapping()["plan"][0]["status"], "in_progress")

    def test_exec_event_parses_parsed_command_payload(self):
        msg = EventMsg.from_mapping(
            {
                "type": "exec_command_begin",
                "call_id": "call-1",
                "turn_id": "turn-1",
                "command": ["cat", "src/app.py"],
                "cwd": "/repo",
                "parsed_cmd": [
                    {"type": "read", "cmd": "cat src/app.py", "name": "app.py", "path": "src/app.py"}
                ],
            }
        )

        self.assertEqual(
            msg.payload,
            ExecCommandBeginEvent(
                "call-1",
                "turn-1",
                ("cat", "src/app.py"),
                Path("/repo"),
                parsed_cmd=(ParsedCommand.read("cat src/app.py", "app.py", Path("src/app.py")),),
            ),
        )
        self.assertEqual(msg.to_mapping()["parsed_cmd"][0]["type"], "read")


if __name__ == "__main__":
    unittest.main()
