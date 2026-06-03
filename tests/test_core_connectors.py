import unittest
from types import SimpleNamespace

from pycodex.core import (
    CODEX_APPS_MCP_SERVER_NAME,
    AppConfig,
    AppInfo,
    AppRequirement,
    AppToolApproval,
    AppToolConfig,
    AppToolPolicy,
    AppToolRequirement,
    AppToolsConfig,
    AppToolsRequirements,
    AppsConfig,
    AppsDefaultConfig,
    AppsRequirements,
    ToolAnnotations,
    ToolInfo,
    accessible_connectors_from_mcp_tools,
    app_is_enabled,
    app_tool_policy,
    app_tool_policy_from_apps_config,
    apply_requirements_apps_constraints,
    connector_install_url,
    connector_name_slug,
    codex_app_tool_is_enabled,
    managed_app_tool_approval,
    merge_connectors,
    merge_plugin_connectors,
    merge_plugin_connectors_with_accessible,
    plugin_connector_to_app_info,
    sanitize_name,
    with_app_enabled_state,
    with_app_plugin_sources,
)
from pycodex.protocol import Tool


def mcp_tool(
    name: str,
    *,
    title: str | None = None,
    annotations=None,
) -> Tool:
    return Tool(name=name, input_schema={}, title=title, annotations=annotations)


def codex_app_tool(
    tool_name: str,
    connector_id: str,
    connector_name: str | None,
    plugin_display_names=(),
    namespace_description: str | None = None,
) -> ToolInfo:
    namespace = (
        f"mcp__{CODEX_APPS_MCP_SERVER_NAME}__{sanitize_name(connector_name)}"
        if connector_name is not None
        else CODEX_APPS_MCP_SERVER_NAME
    )
    return ToolInfo(
        server_name=CODEX_APPS_MCP_SERVER_NAME,
        callable_namespace=namespace,
        callable_name=tool_name,
        namespace_description=namespace_description,
        tool=mcp_tool(tool_name),
        connector_id=connector_id,
        connector_name=connector_name,
        plugin_display_names=tuple(plugin_display_names),
    )


def app_info(
    connector_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    is_accessible: bool = False,
    is_enabled: bool = True,
    install_url: str | None = None,
    plugin_display_names=(),
    logo_url: str | None = None,
    logo_url_dark: str | None = None,
    distribution_channel: str | None = None,
) -> AppInfo:
    return AppInfo(
        id=connector_id,
        name=name or connector_id,
        description=description,
        logo_url=logo_url,
        logo_url_dark=logo_url_dark,
        distribution_channel=distribution_channel,
        install_url=install_url,
        is_accessible=is_accessible,
        is_enabled=is_enabled,
        plugin_display_names=tuple(plugin_display_names),
    )


class ConnectorHelperTests(unittest.TestCase):
    def test_slug_and_install_url_match_upstream_shape(self) -> None:
        self.assertEqual(connector_name_slug("Google Calendar"), "google-calendar")
        self.assertEqual(connector_name_slug(" -- "), "app")
        self.assertEqual(sanitize_name("Google Calendar"), "google_calendar")
        self.assertEqual(
            connector_install_url("Google Calendar", "calendar"),
            "https://chatgpt.com/apps/google-calendar/calendar",
        )

    def test_accessible_connectors_from_mcp_tools_carries_plugin_display_names(self) -> None:
        tools = [
            codex_app_tool("calendar_list_events", "calendar", None, ("sample", "sample")),
            codex_app_tool(
                "calendar_create_event",
                "calendar",
                "Google Calendar",
                ("beta", "sample"),
            ),
            ToolInfo(
                server_name="sample",
                callable_name="echo",
                callable_namespace="sample",
                tool=mcp_tool("echo"),
                plugin_display_names=("ignored",),
            ),
        ]

        self.assertEqual(
            accessible_connectors_from_mcp_tools(tools),
            [
                app_info(
                    "calendar",
                    name="Google Calendar",
                    is_accessible=True,
                    install_url=connector_install_url("Google Calendar", "calendar"),
                    plugin_display_names=("beta", "sample"),
                )
            ],
        )

    def test_accessible_connectors_from_mcp_tools_preserves_description(self) -> None:
        tools = [
            codex_app_tool(
                "calendar_create_event",
                "calendar",
                "Calendar",
                namespace_description="Plan events",
            )
        ]

        self.assertEqual(
            accessible_connectors_from_mcp_tools(tools),
            [
                app_info(
                    "calendar",
                    name="Calendar",
                    description="Plan events",
                    is_accessible=True,
                    install_url=connector_install_url("Calendar", "calendar"),
                )
            ],
        )

    def test_merge_connectors_replaces_placeholder_fields_and_dedupes_plugins(self) -> None:
        placeholder = plugin_connector_to_app_info("calendar")
        placeholder = AppInfo.from_mapping(
            {
                **placeholder.to_mapping(),
                "plugin_display_names": ["sample", "alpha", "sample"],
            }
        )
        accessible = app_info(
            "calendar",
            name="Google Calendar",
            description="Plan events",
            is_accessible=True,
            logo_url="https://example.com/logo.png",
            logo_url_dark="https://example.com/logo-dark.png",
            distribution_channel="workspace",
            plugin_display_names=("beta", "alpha"),
        )

        self.assertEqual(
            merge_connectors([placeholder], [accessible]),
            [
                app_info(
                    "calendar",
                    name="Google Calendar",
                    description="Plan events",
                    is_accessible=True,
                    install_url=connector_install_url("calendar", "calendar"),
                    logo_url="https://example.com/logo.png",
                    logo_url_dark="https://example.com/logo-dark.png",
                    distribution_channel="workspace",
                    plugin_display_names=("alpha", "beta", "sample"),
                )
            ],
        )

    def test_merge_plugin_connectors_adds_missing_placeholders(self) -> None:
        merged = merge_plugin_connectors(
            [app_info("calendar", name="Calendar")],
            ["calendar", "gmail"],
        )

        self.assertEqual([connector.id for connector in merged], ["calendar", "gmail"])
        self.assertFalse(merged[1].is_accessible)
        self.assertEqual(
            merged[1].install_url,
            connector_install_url("gmail", "gmail"),
        )

    def test_merge_plugin_connectors_with_accessible_only_keeps_accessible_ids(self) -> None:
        merged = merge_plugin_connectors_with_accessible(
            ["calendar", "missing"],
            [app_info("calendar", name="Calendar", is_accessible=True)],
        )

        self.assertEqual([connector.id for connector in merged], ["calendar"])
        self.assertTrue(merged[0].is_accessible)

    def test_app_is_enabled_uses_default_and_per_app_override(self) -> None:
        config = AppsConfig(
            default=AppsDefaultConfig(enabled=False),
            apps={"calendar": AppConfig(enabled=True)},
        )

        self.assertTrue(app_is_enabled(config, "calendar"))
        self.assertFalse(app_is_enabled(config, "drive"))
        self.assertFalse(app_is_enabled(config, None))

    def test_app_tool_policy_uses_global_defaults_for_destructive_hints(self) -> None:
        config = AppsConfig(
            default=AppsDefaultConfig(
                enabled=True,
                destructive_enabled=False,
                open_world_enabled=True,
            )
        )

        self.assertEqual(
            app_tool_policy_from_apps_config(
                config,
                "calendar",
                "events/create",
                annotations=ToolAnnotations(destructive_hint=True),
            ),
            AppToolPolicy(enabled=False, approval=AppToolApproval.AUTO),
        )

    def test_app_tool_policy_defaults_missing_hints_to_true(self) -> None:
        destructive_config = AppsConfig(
            default=AppsDefaultConfig(destructive_enabled=False, open_world_enabled=True)
        )
        open_world_config = AppsConfig(
            default=AppsDefaultConfig(destructive_enabled=True, open_world_enabled=False)
        )

        self.assertEqual(
            app_tool_policy_from_apps_config(
                destructive_config,
                "calendar",
                "events/create",
                annotations=ToolAnnotations(open_world_hint=False),
            ),
            AppToolPolicy(enabled=False, approval=AppToolApproval.AUTO),
        )
        self.assertEqual(
            app_tool_policy_from_apps_config(
                open_world_config,
                "calendar",
                "events/create",
                annotations=ToolAnnotations(destructive_hint=False),
            ),
            AppToolPolicy(enabled=False, approval=AppToolApproval.AUTO),
        )

    def test_app_tool_policy_honors_default_app_enabled_false(self) -> None:
        config = AppsConfig(default=AppsDefaultConfig(enabled=False))

        self.assertEqual(
            app_tool_policy_from_apps_config(config, "calendar", "events/list"),
            AppToolPolicy(enabled=False, approval=AppToolApproval.AUTO),
        )

    def test_app_tool_policy_uses_managed_approval_without_apps_config(self) -> None:
        self.assertEqual(
            app_tool_policy_from_apps_config(
                None,
                "calendar",
                "events/list",
                managed_approval=AppToolApproval.APPROVE,
            ),
            AppToolPolicy(enabled=True, approval=AppToolApproval.APPROVE),
        )

    def test_managed_app_tool_approval_uses_raw_tool_name(self) -> None:
        requirements = AppsRequirements(
            apps={
                "connector_123123": AppRequirement(
                    tools=AppToolsRequirements(
                        {
                            "calendar/list_events": AppToolRequirement(
                                approval_mode=AppToolApproval.APPROVE
                            )
                        }
                    )
                )
            }
        )

        self.assertEqual(
            managed_app_tool_approval(
                requirements,
                "connector_123123",
                "calendar/list_events",
            ),
            AppToolApproval.APPROVE,
        )
        self.assertIsNone(
            managed_app_tool_approval(
                requirements,
                "connector_123123",
                "calendar/create_event",
            )
        )

    def test_requirements_tool_approval_overrides_user_app_config(self) -> None:
        config = AppsConfig(
            apps={
                "connector_123123": AppConfig(
                    tools=AppToolsConfig(
                        {
                            "calendar/list_events": AppToolConfig(
                                approval_mode=AppToolApproval.PROMPT
                            )
                        }
                    )
                )
            }
        )
        requirements = AppsRequirements(
            apps={
                "connector_123123": AppRequirement(
                    tools=AppToolsRequirements(
                        {
                            "calendar/list_events": AppToolRequirement(
                                approval_mode=AppToolApproval.APPROVE
                            )
                        }
                    )
                )
            }
        )

        self.assertEqual(
            app_tool_policy(
                config,
                requirements,
                "connector_123123",
                "calendar/list_events",
            ),
            AppToolPolicy(enabled=True, approval=AppToolApproval.APPROVE),
        )

    def test_requirements_tool_approval_does_not_match_tool_title(self) -> None:
        requirements = AppsRequirements(
            apps={
                "connector_123123": AppRequirement(
                    tools=AppToolsRequirements(
                        {
                            "calendar/list_events": AppToolRequirement(
                                approval_mode=AppToolApproval.APPROVE
                            )
                        }
                    )
                )
            }
        )

        self.assertEqual(
            app_tool_policy(
                None,
                requirements,
                "connector_123123",
                "calendar/create_event",
                tool_title="calendar/list_events",
            ),
            AppToolPolicy(enabled=True, approval=AppToolApproval.AUTO),
        )

    def test_app_tool_policy_matches_tool_title_for_user_tool_config(self) -> None:
        config = AppsConfig(
            apps={
                "calendar": AppConfig(
                    destructive_enabled=False,
                    open_world_enabled=False,
                    default_tools_approval_mode=AppToolApproval.AUTO,
                    default_tools_enabled=False,
                    tools=AppToolsConfig(
                        {
                            "events/create": AppToolConfig(
                                enabled=True,
                                approval_mode=AppToolApproval.APPROVE,
                            )
                        }
                    ),
                )
            }
        )

        self.assertEqual(
            app_tool_policy_from_apps_config(
                config,
                "calendar",
                "calendar_events/create",
                tool_title="events/create",
                annotations={"destructiveHint": True, "openWorldHint": True},
            ),
            AppToolPolicy(enabled=True, approval=AppToolApproval.APPROVE),
        )

    def test_app_tool_policy_default_tools_enabled_overrides_hints(self) -> None:
        config = AppsConfig(
            apps={
                "calendar": AppConfig(
                    destructive_enabled=True,
                    open_world_enabled=True,
                    default_tools_approval_mode=AppToolApproval.APPROVE,
                    default_tools_enabled=False,
                )
            }
        )

        self.assertEqual(
            app_tool_policy_from_apps_config(config, "calendar", "events/list"),
            AppToolPolicy(enabled=False, approval=AppToolApproval.APPROVE),
        )

    def test_app_tool_policy_uses_default_tools_approval_mode(self) -> None:
        config = AppsConfig(
            apps={
                "calendar": AppConfig(
                    default_tools_approval_mode=AppToolApproval.PROMPT,
                    tools=AppToolsConfig(),
                )
            }
        )

        self.assertEqual(
            app_tool_policy_from_apps_config(config, "calendar", "events/list"),
            AppToolPolicy(enabled=True, approval=AppToolApproval.PROMPT),
        )

    def test_app_tool_policy_from_mapping_accepts_upstream_names(self) -> None:
        config = {
            "_default": {"enabled": True},
            "apps": {
                "calendar": {
                    "default_tools_approval_mode": "prompt",
                    "tools": {"events/list": {"approval_mode": "approve"}},
                }
            },
        }

        self.assertEqual(
            app_tool_policy_from_apps_config(config, "calendar", "events/list"),
            AppToolPolicy(enabled=True, approval=AppToolApproval.APPROVE),
        )

    def test_codex_app_tool_is_enabled_only_filters_codex_app_tools(self) -> None:
        disabled_config = AppsConfig(default=AppsDefaultConfig(enabled=False))
        app_tool = codex_app_tool("events/list", "calendar", "Calendar")
        regular_tool = ToolInfo(
            server_name="sample",
            callable_name="echo",
            callable_namespace="sample",
            tool=mcp_tool("echo"),
        )

        self.assertFalse(codex_app_tool_is_enabled(app_tool, disabled_config))
        self.assertTrue(codex_app_tool_is_enabled(regular_tool, disabled_config))

    def test_requirements_disabled_connector_overrides_user_state(self) -> None:
        config = AppsConfig(apps={"connector_123123": AppConfig(enabled=True)})
        requirements = AppsRequirements(
            apps={"connector_123123": AppRequirement(enabled=False)}
        )

        constrained = apply_requirements_apps_constraints(config, requirements)

        self.assertFalse(constrained.apps["connector_123123"].enabled)

    def test_requirements_enabled_does_not_override_disabled_connector(self) -> None:
        config = AppsConfig(apps={"connector_123123": AppConfig(enabled=False)})
        requirements = AppsRequirements(
            apps={"connector_123123": AppRequirement(enabled=True)}
        )

        constrained = apply_requirements_apps_constraints(config, requirements)

        self.assertFalse(constrained.apps["connector_123123"].enabled)

    def test_with_app_enabled_state_preserves_unrelated_disabled_connector(self) -> None:
        slack = app_info("connector_slack", is_enabled=False)
        drive = app_info("connector_drive", is_enabled=False)
        requirements = AppsRequirements(
            apps={"connector_drive": AppRequirement(enabled=False)}
        )

        self.assertEqual(
            with_app_enabled_state(
                [slack, app_info("connector_drive")],
                requirements_apps_config=requirements,
            ),
            [slack, drive],
        )

    def test_with_app_enabled_state_applies_user_default(self) -> None:
        config = AppsConfig(default=AppsDefaultConfig(enabled=False))

        self.assertEqual(
            with_app_enabled_state([app_info("calendar")], user_apps_config=config),
            [app_info("calendar", is_enabled=False)],
        )

    def test_with_app_enabled_state_accepts_connector_objects(self) -> None:
        config = AppsConfig(default=AppsDefaultConfig(enabled=False))

        self.assertEqual(
            with_app_enabled_state(
                [SimpleNamespace(id="calendar", name="Calendar", is_enabled=True)],
                user_apps_config=config,
            ),
            [app_info("calendar", name="Calendar", is_enabled=False)],
        )

    def test_with_app_plugin_sources_replaces_display_names(self) -> None:
        self.assertEqual(
            with_app_plugin_sources(
                [app_info("calendar", plugin_display_names=("old",))],
                {"calendar": ["Sample", "Beta"]},
            ),
            [app_info("calendar", plugin_display_names=("Sample", "Beta"))],
        )


if __name__ == "__main__":
    unittest.main()
