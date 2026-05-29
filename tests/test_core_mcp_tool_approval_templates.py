import unittest

from pycodex.core.mcp_tool_approval_templates import (
    ConsequentialToolMessageTemplate,
    ConsequentialToolTemplateParam,
    RenderedMcpToolApprovalParam,
    RenderedMcpToolApprovalTemplate,
    load_consequential_tool_message_templates,
    render_mcp_tool_approval_template_from_templates,
)


class McpToolApprovalTemplatesTests(unittest.TestCase):
    def test_renders_exact_match_with_readable_param_labels(self) -> None:
        templates = (
            ConsequentialToolMessageTemplate(
                connector_id="calendar",
                server_name="codex_apps",
                tool_title="create_event",
                template="Allow {connector_name} to create an event?",
                template_params=(
                    ConsequentialToolTemplateParam(name="calendar_id", label="Calendar"),
                    ConsequentialToolTemplateParam(name="title", label="Title"),
                ),
            ),
        )

        rendered = render_mcp_tool_approval_template_from_templates(
            templates,
            "codex_apps",
            "calendar",
            "Calendar",
            "create_event",
            {
                "title": "Roadmap review",
                "calendar_id": "primary",
                "timezone": "UTC",
            },
        )

        self.assertEqual(
            rendered,
            RenderedMcpToolApprovalTemplate(
                question="Allow Calendar to create an event?",
                elicitation_message="Allow Calendar to create an event?",
                tool_params={
                    "title": "Roadmap review",
                    "calendar_id": "primary",
                    "timezone": "UTC",
                },
                tool_params_display=(
                    RenderedMcpToolApprovalParam(name="calendar_id", value="primary", display_name="Calendar"),
                    RenderedMcpToolApprovalParam(name="title", value="Roadmap review", display_name="Title"),
                    RenderedMcpToolApprovalParam(name="timezone", value="UTC", display_name="timezone"),
                ),
            ),
        )

    def test_returns_none_when_no_exact_match_exists(self) -> None:
        templates = (
            ConsequentialToolMessageTemplate(
                connector_id="calendar",
                server_name="codex_apps",
                tool_title="create_event",
                template="Allow {connector_name} to create an event?",
            ),
        )

        self.assertIsNone(
            render_mcp_tool_approval_template_from_templates(
                templates,
                "codex_apps",
                "calendar",
                "Calendar",
                "delete_event",
                {},
            )
        )

    def test_returns_none_when_relabeling_would_collide(self) -> None:
        templates = (
            ConsequentialToolMessageTemplate(
                connector_id="calendar",
                server_name="codex_apps",
                tool_title="create_event",
                template="Allow {connector_name} to create an event?",
                template_params=(ConsequentialToolTemplateParam(name="calendar_id", label="timezone"),),
            ),
        )

        self.assertIsNone(
            render_mcp_tool_approval_template_from_templates(
                templates,
                "codex_apps",
                "calendar",
                "Calendar",
                "create_event",
                {"calendar_id": "primary", "timezone": "UTC"},
            )
        )

    def test_renders_literal_template_without_connector_substitution(self) -> None:
        templates = (
            ConsequentialToolMessageTemplate(
                connector_id="github",
                server_name="codex_apps",
                tool_title="add_comment",
                template="Allow GitHub to add a comment to a pull request?",
            ),
        )

        rendered = render_mcp_tool_approval_template_from_templates(
            templates,
            "codex_apps",
            "github",
            None,
            "add_comment",
            {},
        )

        self.assertEqual(
            rendered,
            RenderedMcpToolApprovalTemplate(
                question="Allow GitHub to add a comment to a pull request?",
                elicitation_message="Allow GitHub to add a comment to a pull request?",
                tool_params={},
                tool_params_display=(),
            ),
        )

    def test_returns_none_when_connector_placeholder_has_no_value(self) -> None:
        templates = (
            ConsequentialToolMessageTemplate(
                connector_id="calendar",
                server_name="codex_apps",
                tool_title="create_event",
                template="Allow {connector_name} to create an event?",
            ),
        )

        self.assertIsNone(
            render_mcp_tool_approval_template_from_templates(
                templates,
                "codex_apps",
                "calendar",
                None,
                "create_event",
                {},
            )
        )

    def test_bundled_templates_load(self) -> None:
        self.assertIsNotNone(load_consequential_tool_message_templates())


if __name__ == "__main__":
    unittest.main()
