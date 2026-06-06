import unittest
from pathlib import Path

from pycodex.core.context import (
    EnvironmentContext,
    EnvironmentContextEnvironment,
    NetworkContext,
)


class EnvironmentContextTests(unittest.TestCase):
    # Rust source:
    # - codex/codex-rs/core/src/context/environment_context.rs
    # - codex/codex-rs/core/src/context/environment_context_tests.rs

    def test_serializes_single_environment_with_date_and_timezone(self) -> None:
        cwd = Path("/repo")
        context = EnvironmentContext.new(
            (EnvironmentContextEnvironment("local", cwd, "bash"),),
            current_date="2026-02-26",
            timezone="America/Los_Angeles",
        )

        self.assertEqual(
            context.render(),
            "<environment_context>\n"
            f"  <cwd>{cwd}</cwd>\n"
            "  <shell>bash</shell>\n"
            "  <current_date>2026-02-26</current_date>\n"
            "  <timezone>America/Los_Angeles</timezone>\n"
            "</environment_context>",
        )

    def test_serializes_environment_context_with_network_domains(self) -> None:
        cwd = Path("/repo")
        network = NetworkContext(
            ("api.example.com", "*.openai.com"),
            ("blocked.example.com",),
        )
        context = EnvironmentContext.new(
            (EnvironmentContextEnvironment("local", cwd, "bash"),),
            current_date="2026-02-26",
            timezone="America/Los_Angeles",
            network=network,
        )

        self.assertEqual(
            context.render(),
            "<environment_context>\n"
            f"  <cwd>{cwd}</cwd>\n"
            "  <shell>bash</shell>\n"
            "  <current_date>2026-02-26</current_date>\n"
            "  <timezone>America/Los_Angeles</timezone>\n"
            '  <network enabled="true"><allowed>api.example.com,*.openai.com</allowed>'
            "<denied>blocked.example.com</denied></network>\n"
            "</environment_context>",
        )

    def test_serializes_read_only_environment_context_without_environment_entries(self) -> None:
        context = EnvironmentContext.new(
            (),
            current_date="2026-02-26",
            timezone="America/Los_Angeles",
        )

        self.assertEqual(
            context.render(),
            "<environment_context>\n"
            "  <current_date>2026-02-26</current_date>\n"
            "  <timezone>America/Los_Angeles</timezone>\n"
            "</environment_context>",
        )

    def test_serializes_multiple_environments_in_order(self) -> None:
        local_cwd = Path("/repo/local")
        remote_cwd = Path("/repo/remote")
        context = EnvironmentContext.new(
            (
                EnvironmentContextEnvironment("local", local_cwd, "bash"),
                EnvironmentContextEnvironment("remote", remote_cwd, "cmd"),
            ),
            current_date="2026-02-26",
            timezone="America/Los_Angeles",
        )

        self.assertEqual(
            context.render(),
            "<environment_context>\n"
            "  <environments>\n"
            '    <environment id="local">\n'
            f"      <cwd>{local_cwd}</cwd>\n"
            "      <shell>bash</shell>\n"
            "    </environment>\n"
            '    <environment id="remote">\n'
            f"      <cwd>{remote_cwd}</cwd>\n"
            "      <shell>cmd</shell>\n"
            "    </environment>\n"
            "  </environments>\n"
            "  <current_date>2026-02-26</current_date>\n"
            "  <timezone>America/Los_Angeles</timezone>\n"
            "</environment_context>",
        )

    def test_subagents_are_rendered_as_indented_block(self) -> None:
        cwd = Path("/repo")
        context = EnvironmentContext.new(
            (EnvironmentContextEnvironment("local", cwd, "bash"),),
            current_date="2026-02-26",
            timezone="America/Los_Angeles",
            subagents="- agent-1: atlas\n- agent-2",
        )

        self.assertEqual(
            context.render(),
            "<environment_context>\n"
            f"  <cwd>{cwd}</cwd>\n"
            "  <shell>bash</shell>\n"
            "  <current_date>2026-02-26</current_date>\n"
            "  <timezone>America/Los_Angeles</timezone>\n"
            "  <subagents>\n"
            "    - agent-1: atlas\n"
            "    - agent-2\n"
            "  </subagents>\n"
            "</environment_context>",
        )

    def test_equals_except_shell_ignores_single_environment_shell_and_id(self) -> None:
        first = EnvironmentContext.new((EnvironmentContextEnvironment("local", Path("/repo"), "bash"),))
        second = EnvironmentContext.new((EnvironmentContextEnvironment("other", Path("/repo"), "zsh"),))
        different = EnvironmentContext.new((EnvironmentContextEnvironment("local", Path("/other"), "bash"),))

        self.assertTrue(first.equals_except_shell(second))
        self.assertFalse(first.equals_except_shell(different))

    def test_with_subagents_keeps_existing_value_when_new_value_is_empty(self) -> None:
        context = EnvironmentContext.new(
            (EnvironmentContextEnvironment("local", Path("/repo"), "bash"),),
            subagents="- agent-1",
        )

        self.assertEqual(context.with_subagents("").subagents, "- agent-1")
        self.assertEqual(context.with_subagents("- agent-2").subagents, "- agent-2")


if __name__ == "__main__":
    unittest.main()
