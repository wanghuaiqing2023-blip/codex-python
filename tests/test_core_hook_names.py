import unittest

from pycodex.core import HookToolName


class HookToolNameTests(unittest.TestCase):
    def test_new_has_no_matcher_aliases(self) -> None:
        tool_name = HookToolName.new("tool_search")

        self.assertEqual(tool_name.name, "tool_search")
        self.assertEqual(tool_name.matcher_aliases, ())
        self.assertEqual(tool_name.matcher_inputs(), ("tool_search",))

    def test_apply_patch_uses_codex_name_and_edit_aliases(self) -> None:
        tool_name = HookToolName.apply_patch()

        self.assertEqual(tool_name.name, "apply_patch")
        self.assertEqual(tool_name.matcher_aliases, ("Write", "Edit"))
        self.assertEqual(tool_name.matcher_inputs(), ("apply_patch", "Write", "Edit"))

    def test_spawn_agent_uses_agent_alias(self) -> None:
        tool_name = HookToolName.spawn_agent()

        self.assertEqual(tool_name.name, "spawn_agent")
        self.assertEqual(tool_name.matcher_aliases, ("Agent",))
        self.assertEqual(tool_name.matcher_inputs(), ("spawn_agent", "Agent"))

    def test_bash_uses_historical_hook_name(self) -> None:
        tool_name = HookToolName.bash()

        self.assertEqual(tool_name.name, "Bash")
        self.assertEqual(tool_name.matcher_aliases, ())


if __name__ == "__main__":
    unittest.main()
