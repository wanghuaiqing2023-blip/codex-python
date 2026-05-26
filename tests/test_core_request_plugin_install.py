import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.core import (
    CODEX_APPS_MCP_SERVER_NAME,
    LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME,
    MAX_LIST_AVAILABLE_PLUGINS_TO_INSTALL_DESCRIPTION_CHARS,
    REQUEST_PLUGIN_INSTALL_APPROVAL_KIND_VALUE,
    REQUEST_PLUGIN_INSTALL_PERSIST_ALWAYS_VALUE,
    REQUEST_PLUGIN_INSTALL_PERSIST_KEY,
    REQUEST_PLUGIN_INSTALL_TOOL_NAME,
    AppInfo,
    DiscoverablePluginInfo,
    DiscoverableTool,
    DiscoverableToolAction,
    DiscoverableToolType,
    ListAvailablePluginsToInstallHandler,
    PlannedTools,
    PluginInstallElicitationTelemetryMetadata,
    RequestPluginInstallArgs,
    RequestPluginInstallEntry,
    RequestPluginInstallHandler,
    RequestPluginInstallResult,
    ToolPayload,
    add_discoverable_install_tools,
    all_requested_connectors_picked_up,
    build_model_visible_specs_and_registry,
    build_request_plugin_install_elicitation_request,
    build_request_plugin_install_meta,
    collect_request_plugin_install_entries,
    create_list_available_plugins_to_install_tool,
    create_request_plugin_install_tool,
    disabled_install_request,
    maybe_persist_disabled_install_request,
    persist_disabled_install_request,
    plugin_install_elicitation_telemetry_metadata,
    read_toml_mapping,
    refresh_missing_requested_connectors,
    request_plugin_install_response_requests_persistent_disable,
    verified_connector_install_completed,
    verified_plugin_install_completed,
    verify_request_plugin_install_completed,
)
from pycodex.protocol import ElicitationRequest, ElicitationRequestEvent, EventMsg, ToolName


def calendar_connector() -> DiscoverableTool:
    return DiscoverableTool.connector(
        AppInfo(
            id="connector_2128aebfecb84f64a069897515042a44",
            name="Google Calendar",
            description="Plan events and schedules.",
            install_url="https://chatgpt.com/apps/google-calendar/connector_2128aebfecb84f64a069897515042a44",
            is_enabled=True,
        )
    )


def sample_plugin() -> DiscoverableTool:
    return DiscoverableTool.plugin(
        DiscoverablePluginInfo(
            id="sample@openai-curated",
            name="Sample Plugin",
            description="Includes skills, MCP servers, and apps.",
            has_skills=True,
            mcp_server_names=("sample-docs",),
            app_connector_ids=("connector_calendar",),
        )
    )


class RequestPluginInstallDataTests(unittest.TestCase):
    def test_build_elicitation_request_uses_expected_connector_shape(self) -> None:
        args = RequestPluginInstallArgs(
            tool_type=DiscoverableToolType.CONNECTOR,
            action_type=DiscoverableToolAction.INSTALL,
            tool_id="connector_2128aebfecb84f64a069897515042a44",
            suggest_reason="Plan and reference events from your calendar",
        )

        request = build_request_plugin_install_elicitation_request(
            CODEX_APPS_MCP_SERVER_NAME,
            "thread-1",
            "turn-1",
            args,
            "Plan and reference events from your calendar",
            calendar_connector(),
        )

        self.assertEqual(
            request.to_mapping(),
            {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "serverName": "codex-apps",
                "mode": "form",
                "_meta": {
                    "codex_approval_kind": "tool_suggestion",
                    "persist": "always",
                    "tool_type": "connector",
                    "suggest_type": "install",
                    "suggest_reason": "Plan and reference events from your calendar",
                    "tool_id": "connector_2128aebfecb84f64a069897515042a44",
                    "tool_name": "Google Calendar",
                    "install_url": "https://chatgpt.com/apps/google-calendar/connector_2128aebfecb84f64a069897515042a44",
                },
                "message": "Plan and reference events from your calendar",
                "requestedSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        )

    def test_build_elicitation_request_for_plugin_omits_install_url(self) -> None:
        args = RequestPluginInstallArgs(
            tool_type="plugin",
            action_type="install",
            tool_id="sample@openai-curated",
            suggest_reason="Use the sample plugin's skills and MCP server",
        )

        request = build_request_plugin_install_elicitation_request(
            "codex-apps",
            "thread-1",
            "turn-1",
            args,
            "Use the sample plugin's skills and MCP server",
            sample_plugin(),
        )

        self.assertNotIn("install_url", request.to_mapping()["_meta"])

    def test_build_request_plugin_install_meta_uses_expected_shape(self) -> None:
        meta = build_request_plugin_install_meta(
            DiscoverableToolType.CONNECTOR,
            DiscoverableToolAction.INSTALL,
            "Find and reference emails from your inbox",
            "connector_68df038e0ba48191908c8434991bbac2",
            "Gmail",
            "https://chatgpt.com/apps/gmail/connector_68df038e0ba48191908c8434991bbac2",
        )

        self.assertEqual(
            meta.to_mapping(),
            {
                "codex_approval_kind": REQUEST_PLUGIN_INSTALL_APPROVAL_KIND_VALUE,
                "persist": REQUEST_PLUGIN_INSTALL_PERSIST_ALWAYS_VALUE,
                "tool_type": "connector",
                "suggest_type": "install",
                "suggest_reason": "Find and reference emails from your inbox",
                "tool_id": "connector_68df038e0ba48191908c8434991bbac2",
                "tool_name": "Gmail",
                "install_url": "https://chatgpt.com/apps/gmail/connector_68df038e0ba48191908c8434991bbac2",
            },
        )

    def test_plugin_install_elicitation_telemetry_metadata_requires_install_tool_suggestion(self) -> None:
        event = EventMsg.with_payload(
            "elicitation_request",
            ElicitationRequestEvent(
                "codex_apps",
                "request-1",
                ElicitationRequest.form(
                    "Install Slack?",
                    {"type": "object", "properties": {}},
                    meta={
                        "codex_approval_kind": "tool_suggestion",
                        "suggest_type": "install",
                        "tool_type": "plugin",
                        "tool_id": "slack@openai-curated",
                        "tool_name": "Slack",
                    },
                ),
                turn_id="turn-1",
            ),
        )

        self.assertEqual(
            plugin_install_elicitation_telemetry_metadata(event),
            PluginInstallElicitationTelemetryMetadata(
                tool_type="plugin",
                tool_id="slack@openai-curated",
                tool_name="Slack",
            ),
        )

        enable_event = EventMsg.with_payload(
            "elicitation_request",
            ElicitationRequestEvent(
                "codex_apps",
                "request-2",
                ElicitationRequest.form(
                    "Enable Slack?",
                    {"type": "object", "properties": {}},
                    meta={
                        "codex_approval_kind": "tool_suggestion",
                        "suggest_type": "enable",
                        "tool_type": "plugin",
                        "tool_id": "slack@openai-curated",
                        "tool_name": "Slack",
                    },
                ),
                turn_id="turn-1",
            ),
        )

        self.assertIsNone(plugin_install_elicitation_telemetry_metadata(enable_event))

    def test_plugin_install_elicitation_telemetry_metadata_accepts_mapping_and_requires_fields(self) -> None:
        payload = {
            "type": "elicitation_request",
            "turn_id": "turn-1",
            "server_name": "codex_apps",
            "id": "request-1",
            "request": {
                "mode": "form",
                "message": "Install Slack?",
                "requested_schema": {"type": "object", "properties": {}},
                "_meta": {
                    "codex_approval_kind": "tool_suggestion",
                    "suggest_type": "install",
                    "tool_type": " plugin ",
                    "tool_id": " slack@openai-curated ",
                    "tool_name": " Slack ",
                },
            },
        }

        self.assertEqual(
            plugin_install_elicitation_telemetry_metadata(payload),
            PluginInstallElicitationTelemetryMetadata(
                tool_type="plugin",
                tool_id="slack@openai-curated",
                tool_name="Slack",
            ),
        )
        missing_tool_id = dict(payload)
        missing_tool_id["request"] = {
            **payload["request"],
            "_meta": {
                "codex_approval_kind": "tool_suggestion",
                "suggest_type": "install",
                "tool_type": "plugin",
                "tool_name": "Slack",
            },
        }
        self.assertIsNone(
            plugin_install_elicitation_telemetry_metadata(missing_tool_id)
        )
        self.assertIsNone(
            plugin_install_elicitation_telemetry_metadata(
                EventMsg.with_payload("warning", {"message": "nope"})
            )
        )

    def test_connector_completion_helpers_require_accessibility(self) -> None:
        accessible = [
            AppInfo(id="calendar", name="Google Calendar", is_accessible=True),
            AppInfo(id="gmail", name="Gmail", is_accessible=False),
        ]

        self.assertTrue(verified_connector_install_completed("calendar", accessible))
        self.assertFalse(verified_connector_install_completed("gmail", accessible))
        self.assertTrue(all_requested_connectors_picked_up(["calendar"], accessible))
        self.assertFalse(
            all_requested_connectors_picked_up(["calendar", "gmail"], accessible)
        )

    def test_plugin_completion_helper_requires_installed_plugin(self) -> None:
        marketplaces = [
            {
                "name": "openai-curated",
                "plugins": [
                    {"id": "sample@openai-curated", "installed": False},
                    {"id": "slack@openai-curated", "installed": True},
                ],
            },
            SimpleNamespace(
                plugins=(
                    SimpleNamespace(id="calendar@openai-curated", installed=True),
                )
            ),
        ]

        self.assertTrue(
            verified_plugin_install_completed(
                "slack@openai-curated", marketplaces
            )
        )
        self.assertTrue(
            verified_plugin_install_completed(
                "calendar@openai-curated", marketplaces
            )
        )
        self.assertFalse(
            verified_plugin_install_completed(
                "sample@openai-curated", marketplaces
            )
        )
        self.assertFalse(
            verified_plugin_install_completed(
                "missing@openai-curated",
                [{"id": "missing@openai-curated", "installed": False}],
            )
        )

    def test_refresh_missing_requested_connectors_uses_current_or_refreshed_tools(self) -> None:
        accessible = [AppInfo(id="calendar", name="Calendar", is_accessible=True)]

        self.assertEqual(
            refresh_missing_requested_connectors([], accessible),
            (),
        )
        self.assertEqual(
            refresh_missing_requested_connectors(["calendar"], accessible),
            tuple(accessible),
        )
        self.assertIsNone(
            refresh_missing_requested_connectors(["gmail"], accessible)
        )
        self.assertEqual(
            refresh_missing_requested_connectors(
                ["gmail"],
                accessible,
                lambda: [AppInfo(id="gmail", name="Gmail", is_accessible=True)],
            ),
            (AppInfo(id="gmail", name="Gmail", is_accessible=True),),
        )

        def refresh_fails():
            raise RuntimeError("refresh failed")

        self.assertIsNone(
            refresh_missing_requested_connectors(
                ["gmail"],
                accessible,
                refresh_fails,
            )
        )

    def test_verify_request_plugin_install_completed_checks_connector_or_plugin(self) -> None:
        self.assertFalse(
            verify_request_plugin_install_completed(
                calendar_connector(),
                accessible_connectors=(),
            )
        )
        self.assertTrue(
            verify_request_plugin_install_completed(
                calendar_connector(),
                connector_refresh_callback=lambda: [
                    AppInfo(
                        id="connector_2128aebfecb84f64a069897515042a44",
                        name="Google Calendar",
                        is_accessible=True,
                    )
                ],
            )
        )

        refreshed = []

        def refresh_plugin_connectors():
            refreshed.append("called")
            return [AppInfo(id="connector_calendar", name="Calendar", is_accessible=True)]

        self.assertTrue(
            verify_request_plugin_install_completed(
                sample_plugin(),
                plugin_marketplaces_or_plugins=[
                    {
                        "plugins": [
                            {
                                "id": "sample@openai-curated",
                                "installed": True,
                            }
                        ]
                    }
                ],
                connector_refresh_callback=refresh_plugin_connectors,
            )
        )
        self.assertEqual(refreshed, ["called"])
        self.assertFalse(
            verify_request_plugin_install_completed(
                sample_plugin(),
                plugin_marketplaces_or_plugins=[
                    {"id": "sample@openai-curated", "installed": False}
                ],
            )
        )

    def test_persistent_disable_helper_requires_decline_always(self) -> None:
        self.assertTrue(
            request_plugin_install_response_requests_persistent_disable(
                {
                    "action": "decline",
                    "meta": {REQUEST_PLUGIN_INSTALL_PERSIST_KEY: "always"},
                }
            )
        )
        self.assertFalse(
            request_plugin_install_response_requests_persistent_disable(
                {
                    "action": "accept",
                    "meta": {REQUEST_PLUGIN_INSTALL_PERSIST_KEY: "always"},
                }
            )
        )
        self.assertFalse(
            request_plugin_install_response_requests_persistent_disable(
                {
                    "action": "decline",
                    "meta": {REQUEST_PLUGIN_INSTALL_PERSIST_KEY: "session"},
                }
            )
        )

    def test_disabled_install_request_maps_connector_and_plugin_tools(self) -> None:
        self.assertEqual(
            disabled_install_request(calendar_connector()).to_mapping(),
            {
                "type": "connector",
                "id": "connector_2128aebfecb84f64a069897515042a44",
            },
        )
        self.assertEqual(
            disabled_install_request(sample_plugin().to_mapping()).to_mapping(),
            {"type": "plugin", "id": "sample@openai-curated"},
        )

    def test_persist_disabled_install_request_writes_connector_config(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            self.assertTrue(
                persist_disabled_install_request(home, calendar_connector())
            )

            self.assertEqual(
                read_toml_mapping(Path(home) / "config.toml"),
                {
                    "tool_suggest": {
                        "disabled_tools": [
                            {
                                "type": "connector",
                                "id": "connector_2128aebfecb84f64a069897515042a44",
                            }
                        ]
                    }
                },
            )

    def test_persist_disabled_install_request_writes_plugin_config(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            self.assertTrue(persist_disabled_install_request(home, sample_plugin()))

            self.assertEqual(
                read_toml_mapping(Path(home) / "config.toml"),
                {
                    "tool_suggest": {
                        "disabled_tools": [
                            {"type": "plugin", "id": "sample@openai-curated"}
                        ]
                    }
                },
            )

    def test_persist_disabled_install_request_dedupes_existing_disabled_tools(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            Path(home, "config.toml").write_text(
                """
[tool_suggest]
discoverables = [
  { type = "plugin", id = "sample@openai-curated" },
]

[[tool_suggest.disabled_tools]]
type = "connector"
id = " connector_2128aebfecb84f64a069897515042a44 "

[[tool_suggest.disabled_tools]]
type = "connector"
id = "connector_2128aebfecb84f64a069897515042a44"

[[tool_suggest.disabled_tools]]
type = "connector"
id = "   "

[[tool_suggest.disabled_tools]]
type = "plugin"
id = "slack@openai-curated"
""",
                encoding="utf-8",
            )

            self.assertTrue(
                persist_disabled_install_request(home, calendar_connector())
            )
            parsed = read_toml_mapping(Path(home) / "config.toml")

            self.assertEqual(
                parsed["tool_suggest"],
                {
                    "discoverables": [
                        {"type": "plugin", "id": "sample@openai-curated"}
                    ],
                    "disabled_tools": [
                        {
                            "type": "connector",
                            "id": "connector_2128aebfecb84f64a069897515042a44",
                        },
                        {"type": "plugin", "id": "slack@openai-curated"},
                    ],
                },
            )

    def test_maybe_persist_disabled_install_request_respects_response_mode(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            self.assertFalse(
                maybe_persist_disabled_install_request(
                    home,
                    calendar_connector(),
                    {
                        "action": "accept",
                        "meta": {REQUEST_PLUGIN_INSTALL_PERSIST_KEY: "always"},
                    },
                )
            )
            self.assertFalse((Path(home) / "config.toml").exists())

            self.assertTrue(
                maybe_persist_disabled_install_request(
                    home,
                    calendar_connector(),
                    {
                        "action": "decline",
                        "meta": {
                            REQUEST_PLUGIN_INSTALL_PERSIST_KEY: (
                                REQUEST_PLUGIN_INSTALL_PERSIST_ALWAYS_VALUE
                            )
                        },
                    },
                )
            )
            self.assertTrue((Path(home) / "config.toml").exists())


class RequestPluginInstallSpecAndHandlerTests(unittest.TestCase):
    def test_list_available_tool_spec_matches_upstream_contract(self) -> None:
        spec = create_list_available_plugins_to_install_tool()

        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME)
        self.assertIn(
            "Returns known plugins and connectors that can be passed to `request_plugin_install`.",
            spec["description"],
        )
        self.assertEqual(
            spec["parameters"],
            {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        )

    def test_request_plugin_install_tool_spec_matches_upstream_contract(self) -> None:
        spec = create_request_plugin_install_tool()

        self.assertEqual(spec["name"], REQUEST_PLUGIN_INSTALL_TOOL_NAME)
        self.assertIn(
            "Use this tool only after `list_available_plugins_to_install` returns a plugin or connector",
            spec["description"],
        )
        self.assertIn("tool_type", spec["parameters"]["required"])
        self.assertEqual(
            spec["parameters"]["properties"]["action_type"]["description"],
            'Suggested action for the tool. Use "install".',
        )

    def test_list_available_handler_sorts_truncates_and_serializes(self) -> None:
        handler = ListAvailablePluginsToInstallHandler.new(
            [
                RequestPluginInstallEntry(
                    id="sample@openai-curated",
                    name="Sample Plugin",
                    description="x"
                    * (MAX_LIST_AVAILABLE_PLUGINS_TO_INSTALL_DESCRIPTION_CHARS + 1),
                    tool_type=DiscoverableToolType.PLUGIN,
                    has_skills=True,
                    mcp_server_names=("sample-mcp",),
                    app_connector_ids=("connector-sample",),
                ),
                RequestPluginInstallEntry(
                    id="calendar@openai-curated",
                    name="Calendar",
                    description="calendar",
                    tool_type=DiscoverableToolType.PLUGIN,
                    has_skills=False,
                ),
            ]
        )

        output = handler.handle(ToolPayload.function("{}"))
        payload = json.loads(output.into_text())

        self.assertFalse(handler.supports_parallel_tool_calls())
        self.assertEqual(
            [tool["id"] for tool in payload["tools"]],
            ["calendar@openai-curated", "sample@openai-curated"],
        )
        self.assertEqual(
            len(payload["tools"][1]["description"]),
            MAX_LIST_AVAILABLE_PLUGINS_TO_INSTALL_DESCRIPTION_CHARS,
        )

    def test_request_plugin_install_handler_builds_request_and_serializes_result(self) -> None:
        captured = {}

        def callback(args, tool, params):
            captured["args"] = args
            captured["tool"] = tool
            captured["params"] = params
            return RequestPluginInstallResult(
                completed=True,
                user_confirmed=True,
                tool_type=args.tool_type,
                action_type=args.action_type,
                tool_id=tool.id(),
                tool_name=tool.name(),
                suggest_reason=args.suggest_reason.strip(),
            )

        handler = RequestPluginInstallHandler(
            discoverable_tools=(calendar_connector(),),
            request_callback=callback,
            thread_id="thread-1",
            turn_id="turn-1",
        )
        output = handler.handle(
            ToolPayload.function(
                json.dumps(
                    {
                        "tool_type": "connector",
                        "action_type": "install",
                        "tool_id": "connector_2128aebfecb84f64a069897515042a44",
                        "suggest_reason": "  Plan with calendar  ",
                    }
                )
            )
        )

        self.assertTrue(handler.supports_parallel_tool_calls())
        self.assertEqual(captured["tool"].name(), "Google Calendar")
        self.assertEqual(captured["params"].thread_id, "thread-1")
        self.assertEqual(
            json.loads(output.into_text()),
            {
                "completed": True,
                "user_confirmed": True,
                "tool_type": "connector",
                "action_type": "install",
                "tool_id": "connector_2128aebfecb84f64a069897515042a44",
                "tool_name": "Google Calendar",
                "suggest_reason": "Plan with calendar",
            },
        )

    def test_request_plugin_install_handler_validates_model_arguments(self) -> None:
        handler = RequestPluginInstallHandler(discoverable_tools=(sample_plugin(),))

        with self.assertRaisesRegex(ValueError, "suggest_reason must not be empty"):
            handler.handle(
                ToolPayload.function(
                    json.dumps(
                        {
                            "tool_type": "plugin",
                            "action_type": "install",
                            "tool_id": "sample@openai-curated",
                            "suggest_reason": " ",
                        }
                    )
                )
            )

        tui_handler = RequestPluginInstallHandler(
            discoverable_tools=(sample_plugin(),),
            app_server_client_name="codex-tui",
        )
        with self.assertRaisesRegex(ValueError, "not available in codex-tui"):
            tui_handler.handle(
                ToolPayload.function(
                    json.dumps(
                        {
                            "tool_type": "plugin",
                            "action_type": "install",
                            "tool_id": "sample@openai-curated",
                            "suggest_reason": "Use sample plugin",
                        }
                    )
                )
            )

        with self.assertRaisesRegex(ValueError, "tool_id must match"):
            handler.handle(
                ToolPayload.function(
                    json.dumps(
                        {
                            "tool_type": "plugin",
                            "action_type": "install",
                            "tool_id": "missing@openai-curated",
                            "suggest_reason": "Use sample plugin",
                        }
                    )
                )
            )

    def test_spec_plan_adds_install_tools_only_when_discovery_is_enabled(self) -> None:
        planned = PlannedTools()

        add_discoverable_install_tools(
            planned,
            [calendar_connector(), sample_plugin()],
            request_callback=lambda args, tool, params: RequestPluginInstallResult(
                completed=False,
                user_confirmed=False,
                tool_type=args.tool_type,
                action_type=args.action_type,
                tool_id=tool.id(),
                tool_name=tool.name(),
                suggest_reason=args.suggest_reason.strip(),
            ),
        )
        specs, registry = build_model_visible_specs_and_registry(planned)

        self.assertEqual(
            [spec["name"] for spec in specs],
            [
                LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME,
                REQUEST_PLUGIN_INSTALL_TOOL_NAME,
            ],
        )
        self.assertEqual(
            registry.tool_names(),
            (
                ToolName.plain(LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME),
                ToolName.plain(REQUEST_PLUGIN_INSTALL_TOOL_NAME),
            ),
        )

        disabled = PlannedTools()
        add_discoverable_install_tools(
            disabled,
            [calendar_connector()],
            tool_suggest_enabled=False,
        )
        disabled_specs, _ = build_model_visible_specs_and_registry(disabled)
        self.assertEqual(disabled_specs, ())

    def test_collect_entries_feeds_list_handler(self) -> None:
        entries = collect_request_plugin_install_entries(
            [calendar_connector(), sample_plugin()]
        )

        self.assertEqual(
            ListAvailablePluginsToInstallHandler.new(entries).tool_name(),
            ToolName.plain(LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME),
        )


if __name__ == "__main__":
    unittest.main()
