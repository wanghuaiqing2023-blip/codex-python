import unittest
from pathlib import Path

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
        self.assertNotIn("path", ParsedCommand.list_files("rg --files").to_mapping())

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
        with self.assertRaisesRegex(ValueError, "unknown field"):
            UpdatePlanArgs.from_mapping({"plan": [], "unexpected": True})

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
