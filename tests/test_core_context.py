import unittest
from pathlib import Path

from pycodex.core import (
    EnvironmentContext,
    EnvironmentContextEnvironment,
    NetworkContext,
    matches_marked_text,
)
from pycodex.protocol import (
    ENVIRONMENT_CONTEXT_CLOSE_TAG,
    ENVIRONMENT_CONTEXT_OPEN_TAG,
    AskForApproval,
    ContentItem,
    ResponseItem,
    SandboxPolicy,
    TurnContextItem,
    TurnContextNetworkItem,
)


class CoreContextTests(unittest.TestCase):
    def test_serialize_workspace_environment_context(self):
        cwd = Path("/repo")
        context = EnvironmentContext.new(
            (EnvironmentContextEnvironment("local", cwd, "bash"),),
            current_date="2026-02-26",
            timezone="America/Los_Angeles",
        )

        self.assertEqual(
            context.render(),
            f"""<environment_context>
  <cwd>{cwd}</cwd>
  <shell>bash</shell>
  <current_date>2026-02-26</current_date>
  <timezone>America/Los_Angeles</timezone>
</environment_context>""",
        )

    def test_serialize_environment_context_with_network_and_subagents(self):
        cwd = Path("/repo")
        context = EnvironmentContext.new(
            (EnvironmentContextEnvironment("local", cwd, "bash"),),
            current_date="2026-02-26",
            timezone="America/Los_Angeles",
            network=NetworkContext(("api.example.com", "*.openai.com"), ("blocked.example.com",)),
            subagents="- agent-1: atlas\n- agent-2",
        )

        self.assertEqual(
            context.render(),
            f"""<environment_context>
  <cwd>{cwd}</cwd>
  <shell>bash</shell>
  <current_date>2026-02-26</current_date>
  <timezone>America/Los_Angeles</timezone>
  <network enabled="true"><allowed>api.example.com,*.openai.com</allowed><denied>blocked.example.com</denied></network>
  <subagents>
    - agent-1: atlas
    - agent-2
  </subagents>
</environment_context>""",
        )

    def test_serialize_read_only_and_multiple_environments(self):
        read_only = EnvironmentContext.new(
            (),
            current_date="2026-02-26",
            timezone="America/Los_Angeles",
        )
        self.assertEqual(
            read_only.render(),
            """<environment_context>
  <current_date>2026-02-26</current_date>
  <timezone>America/Los_Angeles</timezone>
</environment_context>""",
        )

        local_cwd = Path("/repo/local")
        remote_cwd = Path("/repo/remote")
        multiple = EnvironmentContext.new(
            (
                EnvironmentContextEnvironment("local", local_cwd, "powershell"),
                EnvironmentContextEnvironment("remote", remote_cwd, "cmd"),
            )
        )
        self.assertEqual(
            multiple.render(),
            f"""<environment_context>
  <environments>
    <environment id="local">
      <cwd>{local_cwd}</cwd>
      <shell>powershell</shell>
    </environment>
    <environment id="remote">
      <cwd>{remote_cwd}</cwd>
      <shell>cmd</shell>
    </environment>
  </environments>
</environment_context>""",
        )

    def test_equals_except_shell_matches_upstream_rules(self):
        left = EnvironmentContext.new((EnvironmentContextEnvironment("local", Path("/repo"), "bash"),))
        same_cwd_other_shell = EnvironmentContext.new((EnvironmentContextEnvironment("other", Path("/repo"), "zsh"),))
        other_cwd = EnvironmentContext.new((EnvironmentContextEnvironment("local", Path("/repo2"), "bash"),))

        self.assertTrue(left.equals_except_shell(same_cwd_other_shell))
        self.assertFalse(left.equals_except_shell(other_cwd))

        multiple_left = EnvironmentContext.new(
            (
                EnvironmentContextEnvironment("local", Path("/repo"), "bash"),
                EnvironmentContextEnvironment("remote", Path("/remote"), "bash"),
            )
        )
        multiple_changed_id = EnvironmentContext.new(
            (
                EnvironmentContextEnvironment("local", Path("/repo"), "zsh"),
                EnvironmentContextEnvironment("other", Path("/remote"), "bash"),
            )
        )
        self.assertFalse(multiple_left.equals_except_shell(multiple_changed_id))

    def test_markers_and_response_item_conversion(self):
        context = EnvironmentContext.new((EnvironmentContextEnvironment("local", Path("/repo"), "bash"),))
        rendered = f"  {context.render()}  "

        self.assertTrue(EnvironmentContext.matches_text(rendered.upper()))
        self.assertTrue(matches_marked_text(ENVIRONMENT_CONTEXT_OPEN_TAG, ENVIRONMENT_CONTEXT_CLOSE_TAG, rendered))
        self.assertFalse(matches_marked_text("", ENVIRONMENT_CONTEXT_CLOSE_TAG, rendered))
        self.assertEqual(
            context.into_response_item(),
            ResponseItem.message("user", (ContentItem.input_text(context.render()),)),
        )

    def test_from_turn_context_item_and_diff(self):
        before = TurnContextItem(
            cwd=Path("/repo"),
            approval_policy=AskForApproval.ON_REQUEST,
            sandbox_policy=SandboxPolicy.read_only(),
            model="gpt-5",
            current_date="2026-02-26",
            timezone="America/Los_Angeles",
            network=TurnContextNetworkItem(("api.openai.com",), ("example.invalid",)),
        )
        after = EnvironmentContext.new(
            (EnvironmentContextEnvironment("local", Path("/other"), "bash"),),
            current_date="2026-02-27",
            timezone="UTC",
            network=NetworkContext(("api.openai.com",), ("blocked.invalid",)),
        )

        from_item = EnvironmentContext.from_turn_context_item(before, "bash")
        self.assertEqual(from_item.network, NetworkContext(("api.openai.com",), ("example.invalid",)))
        self.assertIn(f"<cwd>{Path('/repo')}</cwd>", from_item.render())

        diff = EnvironmentContext.diff_from_turn_context_item(before, after)
        self.assertIn(f"<cwd>{Path('/other')}</cwd>", diff.render())
        self.assertIn("<denied>blocked.invalid</denied>", diff.render())
        self.assertIsNone(diff.subagents)

    def test_with_subagents_preserves_existing_subagents_when_empty(self):
        # Rust source: codex-rs/core/src/context/environment_context.rs
        # EnvironmentContext::with_subagents only updates when the new value is non-empty.
        context = EnvironmentContext.new(
            (EnvironmentContextEnvironment("local", Path("/repo"), "bash"),),
            subagents="- agent-1",
        )

        self.assertEqual(context.with_subagents("").subagents, "- agent-1")
        self.assertEqual(context.with_subagents("- agent-2").subagents, "- agent-2")

    def test_diff_from_turn_context_item_keeps_unchanged_network_like_rust(self):
        # Rust source: codex-rs/core/src/context/environment_context.rs
        # diff_from_turn_context_item returns before_network when before and after match.
        before = TurnContextItem(
            cwd=Path("/repo"),
            approval_policy=AskForApproval.ON_REQUEST,
            sandbox_policy=SandboxPolicy.read_only(),
            model="gpt-5",
            current_date=None,
            timezone=None,
            network=TurnContextNetworkItem(("api.openai.com",), ("blocked.invalid",)),
        )
        after = EnvironmentContext.new(
            (EnvironmentContextEnvironment("local", Path("/repo"), "zsh"),),
            network=NetworkContext(("api.openai.com",), ("blocked.invalid",)),
        )

        diff = EnvironmentContext.diff_from_turn_context_item(before, after)

        self.assertIn(
            '<network enabled="true"><allowed>api.openai.com</allowed><denied>blocked.invalid</denied></network>',
            diff.render(),
        )


if __name__ == "__main__":
    unittest.main()
