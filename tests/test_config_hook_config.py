import json
import os
import unittest
from pathlib import Path

from pycodex.config import (
    HookEventsToml,
    HookHandlerConfig,
    HookStateToml,
    HooksFile,
    HooksToml,
    ManagedHooksRequirementsToml,
    MatcherGroup,
)
from pycodex.protocol import HookEventName


class ConfigHookConfigTests(unittest.TestCase):
    def test_hooks_file_deserializes_existing_json_shape(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/hook_config.rs
        # Rust test: hooks_file_deserializes_existing_json_shape
        parsed = HooksFile.from_mapping(
            json.loads(
                """{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "^Bash$",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /tmp/pre.py",
            "timeout": 10,
            "statusMessage": "checking"
          }
        ]
      }
    ]
  }
}"""
            )
        )

        self.assertEqual(
            parsed,
            HooksFile(
                hooks=HookEventsToml(
                    pre_tool_use=(
                        MatcherGroup(
                            matcher="^Bash$",
                            hooks=(
                                HookHandlerConfig.command_handler(
                                    "python3 /tmp/pre.py",
                                    timeout_sec=10,
                                    status_message="checking",
                                ),
                            ),
                        ),
                    )
                )
            ),
        )

    def test_hook_events_deserialize_from_toml_arrays_of_tables(self) -> None:
        # Rust test: hook_events_deserialize_from_toml_arrays_of_tables
        parsed = HookEventsToml.from_toml(
            """
[[PreToolUse]]
matcher = "^Bash$"

[[PreToolUse.hooks]]
type = "command"
command = "python3 /tmp/pre.py"
timeout = 10
statusMessage = "checking"
"""
        )

        self.assertEqual(
            parsed.pre_tool_use,
            (
                MatcherGroup(
                    matcher="^Bash$",
                    hooks=(
                        HookHandlerConfig.command_handler(
                            "python3 /tmp/pre.py",
                            timeout_sec=10,
                            status_message="checking",
                        ),
                    ),
                ),
            ),
        )

    def test_hooks_toml_deserializes_inline_events_and_state_map(self) -> None:
        # Rust test: hooks_toml_deserializes_inline_events_and_state_map
        parsed = HooksToml.from_toml(
            """
[state."/tmp/hooks.json:pre_tool_use:0:0"]
enabled = false
trusted_hash = "sha256:abc123"

[[PreToolUse]]
matcher = "^Bash$"

[[PreToolUse.hooks]]
type = "command"
command = "python3 /tmp/pre.py"
"""
        )

        self.assertEqual(parsed.events.pre_tool_use[0].matcher, "^Bash$")
        self.assertEqual(
            parsed.state,
            {
                "/tmp/hooks.json:pre_tool_use:0:0": HookStateToml(
                    enabled=False,
                    trusted_hash="sha256:abc123",
                )
            },
        )

    def test_managed_hooks_requirements_flatten_hook_events(self) -> None:
        # Rust test: managed_hooks_requirements_flatten_hook_events
        parsed = ManagedHooksRequirementsToml.from_toml(
            """
managed_dir = "/enterprise/place"

[[PreToolUse]]
matcher = "^Bash$"

[[PreToolUse.hooks]]
type = "command"
command = "python3 /enterprise/place/pre.py"
"""
        )

        self.assertEqual(parsed.managed_dir, Path("/enterprise/place"))
        self.assertIsNone(parsed.windows_managed_dir)
        self.assertEqual(parsed.handler_count(), 1)
        self.assertEqual(parsed.hooks.pre_tool_use[0].hooks[0].command, "python3 /enterprise/place/pre.py")

    def test_hook_events_deserialize_windows_override_from_toml(self) -> None:
        # Rust test: hook_events_deserialize_windows_override_from_toml
        parsed = HookEventsToml.from_toml(
            r"""
[[PreToolUse]]
matcher = "^Bash$"

[[PreToolUse.hooks]]
type = "command"
command = "bash /enterprise/hooks/pre.sh"
command_windows = "powershell -File C:\\enterprise\\hooks\\pre.ps1"
"""
        )

        self.assertEqual(
            parsed.pre_tool_use[0].hooks[0].command_windows,
            r"powershell -File C:\enterprise\hooks\pre.ps1",
        )

    def test_hook_events_deserialize_camel_case_windows_override_from_toml(self) -> None:
        # Rust test: hook_events_deserialize_camel_case_windows_override_from_toml
        parsed = HookEventsToml.from_toml(
            r"""
[[PreToolUse]]
matcher = "^Bash$"

[[PreToolUse.hooks]]
type = "command"
command = "bash /enterprise/hooks/pre.sh"
commandWindows = "powershell -File C:\\enterprise\\hooks\\pre.ps1"
"""
        )

        self.assertEqual(
            parsed.pre_tool_use[0].hooks[0].command_windows,
            r"powershell -File C:\enterprise\hooks\pre.ps1",
        )

    def test_hook_events_helpers_count_empty_and_preserve_event_order(self) -> None:
        events = HookEventsToml(
            pre_tool_use=(
                MatcherGroup(hooks=(HookHandlerConfig.prompt(), HookHandlerConfig.agent())),
            ),
            stop=(MatcherGroup(hooks=(HookHandlerConfig.command_handler("echo done"),)),),
        )

        self.assertFalse(events.is_empty())
        self.assertEqual(events.handler_count(), 3)
        self.assertEqual(
            [event for event, _groups in events.into_matcher_groups()],
            [
                HookEventName.PRE_TOOL_USE,
                HookEventName.PERMISSION_REQUEST,
                HookEventName.POST_TOOL_USE,
                HookEventName.PRE_COMPACT,
                HookEventName.POST_COMPACT,
                HookEventName.SESSION_START,
                HookEventName.USER_PROMPT_SUBMIT,
                HookEventName.SUBAGENT_START,
                HookEventName.SUBAGENT_STOP,
                HookEventName.STOP,
            ],
        )

    def test_managed_hooks_empty_and_platform_dir(self) -> None:
        empty = ManagedHooksRequirementsToml()
        self.assertTrue(empty.is_empty())
        self.assertEqual(empty.handler_count(), 0)

        configured = ManagedHooksRequirementsToml(
            managed_dir=Path("/enterprise/hooks"),
            windows_managed_dir=Path(r"C:\enterprise\hooks"),
        )
        expected = configured.windows_managed_dir if os.name == "nt" else configured.managed_dir
        self.assertEqual(configured.managed_dir_for_current_platform(), expected)


if __name__ == "__main__":
    unittest.main()
