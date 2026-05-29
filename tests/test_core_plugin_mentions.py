import unittest

from pycodex.core.context import PluginCapabilitySummary
from pycodex.core.plugin_mentions import (
    PLUGIN_PATH_PREFIX,
    SKILL_PATH_PREFIX,
    ToolMentionKind,
    app_id_from_path,
    build_connector_slug_counts,
    collect_explicit_app_ids,
    collect_explicit_plugin_mentions,
    collect_tool_mentions_from_messages,
    collect_tool_mentions_from_messages_with_sigil,
    extract_tool_mentions,
    is_skill_filename,
    normalize_skill_path,
    plugin_config_name_from_path,
    tool_kind_for_path,
)
from pycodex.core.tool_discovery import AppInfo
from pycodex.protocol import UserInput


def text_input(text: str) -> UserInput:
    return UserInput.text_input(text)


def plugin(config_name: str, display_name: str) -> PluginCapabilitySummary:
    return PluginCapabilitySummary(
        config_name=config_name,
        display_name=display_name,
        description=None,
        has_skills=True,
        mcp_server_names=(),
        app_connector_ids=(),
    )


class PluginMentionsTests(unittest.TestCase):
    def assert_mentions(self, text: str, names: set[str], paths: set[str], plain_names: set[str] | None = None) -> None:
        mentions = extract_tool_mentions(text)
        self.assertEqual(mentions.names, frozenset(names))
        self.assertEqual(mentions.paths, frozenset(paths))
        self.assertEqual(mentions.plain_names, frozenset(names if plain_names is None else plain_names))

    def test_extract_tool_mentions_handles_plain_and_linked_mentions(self) -> None:
        self.assert_mentions("use $alpha and [$beta](/tmp/beta)", {"alpha", "beta"}, {"/tmp/beta"}, {"alpha"})

    def test_extract_tool_mentions_skips_common_env_vars(self) -> None:
        self.assert_mentions("use $PATH and $alpha", {"alpha"}, set())
        self.assert_mentions("use [$HOME](/tmp/skill)", set(), set())
        self.assert_mentions("use $XDG_CONFIG_HOME and $beta", {"beta"}, set())

    def test_extract_tool_mentions_requires_link_syntax(self) -> None:
        self.assert_mentions("[beta](/tmp/beta)", set(), set())
        self.assert_mentions("[$beta] /tmp/beta", {"beta"}, set())
        self.assert_mentions("[$beta]()", {"beta"}, set())

    def test_extract_tool_mentions_trims_linked_paths_and_allows_spacing(self) -> None:
        self.assert_mentions("use [$beta]   ( /tmp/beta )", {"beta"}, {"/tmp/beta"}, set())

    def test_extract_tool_mentions_stops_at_non_name_chars(self) -> None:
        self.assert_mentions("use $alpha.skill and $beta_extra", {"alpha", "beta_extra"}, set())

    def test_extract_tool_mentions_keeps_plugin_skill_namespaces(self) -> None:
        self.assert_mentions("use $slack:search and $alpha", {"alpha", "slack:search"}, set())

    def test_linked_app_mcp_and_plugin_paths_do_not_add_fallback_names(self) -> None:
        mentions = extract_tool_mentions(
            "use [$calendar](app://calendar), [$docs](mcp://docs), and [$sample](plugin://sample@test)"
        )

        self.assertEqual(mentions.names, frozenset())
        self.assertEqual(
            mentions.paths,
            frozenset({"app://calendar", "mcp://docs", "plugin://sample@test"}),
        )

    def test_tool_kind_for_path_matches_upstream_prefixes(self) -> None:
        self.assertIs(tool_kind_for_path("app://calendar"), ToolMentionKind.APP)
        self.assertIs(tool_kind_for_path("mcp://server"), ToolMentionKind.MCP)
        self.assertIs(tool_kind_for_path(f"{PLUGIN_PATH_PREFIX}sample@test"), ToolMentionKind.PLUGIN)
        self.assertIs(tool_kind_for_path(f"{SKILL_PATH_PREFIX}/tmp/SKILL.md"), ToolMentionKind.SKILL)
        self.assertIs(tool_kind_for_path("/tmp/team/SKILL.md"), ToolMentionKind.SKILL)
        self.assertIs(tool_kind_for_path("/tmp/file.txt"), ToolMentionKind.OTHER)
        self.assertTrue(is_skill_filename(r"C:\repo\Skill.md"))
        self.assertEqual(normalize_skill_path("skill:///tmp/SKILL.md"), "/tmp/SKILL.md")
        with self.assertRaisesRegex(TypeError, "path must be a string"):
            tool_kind_for_path(123)  # type: ignore[arg-type]

    def test_path_extractors_return_non_empty_prefixed_values(self) -> None:
        self.assertEqual(app_id_from_path("app://calendar"), "calendar")
        self.assertIsNone(app_id_from_path("app://"))
        self.assertEqual(plugin_config_name_from_path("plugin://sample@test"), "sample@test")
        self.assertIsNone(plugin_config_name_from_path("plugin://"))

    def test_collect_tool_mentions_from_messages_uses_plain_names_and_paths(self) -> None:
        collected = collect_tool_mentions_from_messages(
            ["use $alpha and [$beta](/tmp/beta)", "also $alpha and [$calendar](app://calendar)"]
        )

        self.assertEqual(collected.plain_names, frozenset({"alpha"}))
        self.assertEqual(collected.paths, frozenset({"/tmp/beta", "app://calendar"}))

    def test_collect_tool_mentions_with_plugin_sigil(self) -> None:
        collected = collect_tool_mentions_from_messages_with_sigil(
            ["use @sample and [@plugin](plugin://sample@test)"],
            "@",
        )

        self.assertEqual(collected.plain_names, frozenset({"sample"}))
        self.assertEqual(collected.paths, frozenset({"plugin://sample@test"}))
        with self.assertRaisesRegex(TypeError, "message must be a string"):
            collect_tool_mentions_from_messages([object()])  # type: ignore[list-item]
        with self.assertRaisesRegex(TypeError, "sigil must be a string"):
            collect_tool_mentions_from_messages_with_sigil(["use @sample"], 1)  # type: ignore[arg-type]

    def test_collect_explicit_app_ids_from_linked_text_mentions(self) -> None:
        app_ids = collect_explicit_app_ids([text_input("use [$calendar](app://calendar)")])

        self.assertEqual(app_ids, {"calendar"})

    def test_collect_explicit_app_ids_dedupes_structured_and_linked_mentions(self) -> None:
        app_ids = collect_explicit_app_ids(
            [
                text_input("use [$calendar](app://calendar)"),
                UserInput.mention("calendar", "app://calendar"),
            ]
        )

        self.assertEqual(app_ids, {"calendar"})

    def test_collect_explicit_app_ids_ignores_non_app_paths(self) -> None:
        app_ids = collect_explicit_app_ids(
            [
                text_input("use [$docs](mcp://docs) and [$skill](skill://team/skill) and [$file](/tmp/file.txt)"),
                UserInput.mention("docs", "mcp://docs"),
                UserInput.mention("skill", "skill://team/skill"),
                UserInput.mention("file", "/tmp/file.txt"),
            ]
        )

        self.assertEqual(app_ids, set())

    def test_collect_explicit_plugin_mentions_from_structured_paths(self) -> None:
        plugins = [plugin("sample@test", "sample"), plugin("other@test", "other")]

        mentioned = collect_explicit_plugin_mentions(
            [UserInput.mention("sample", "plugin://sample@test")],
            plugins,
        )

        self.assertEqual(mentioned, [plugin("sample@test", "sample")])

    def test_collect_explicit_plugin_mentions_from_linked_text_mentions(self) -> None:
        plugins = [plugin("sample@test", "sample"), plugin("other@test", "other")]

        mentioned = collect_explicit_plugin_mentions(
            [text_input("use [@sample](plugin://sample@test)")],
            plugins,
        )

        self.assertEqual(mentioned, [plugin("sample@test", "sample")])

    def test_collect_explicit_plugin_mentions_dedupes_structured_and_linked_mentions(self) -> None:
        plugins = [plugin("sample@test", "sample"), plugin("other@test", "other")]

        mentioned = collect_explicit_plugin_mentions(
            [
                text_input("use [@sample](plugin://sample@test)"),
                UserInput.mention("sample", "plugin://sample@test"),
            ],
            plugins,
        )

        self.assertEqual(mentioned, [plugin("sample@test", "sample")])

    def test_collect_explicit_plugin_mentions_preserves_plugin_order(self) -> None:
        plugins = [plugin("other@test", "other"), plugin("sample@test", "sample")]

        mentioned = collect_explicit_plugin_mentions(
            [
                text_input("use [@sample](plugin://sample@test)"),
                UserInput.mention("other", "plugin://other@test"),
            ],
            plugins,
        )

        self.assertEqual(mentioned, plugins)

    def test_collect_explicit_plugin_mentions_ignores_non_plugin_paths(self) -> None:
        plugins = [plugin("sample@test", "sample")]

        mentioned = collect_explicit_plugin_mentions(
            [text_input("use [$app](app://calendar) and [$skill](skill://team/skill) and [$file](/tmp/file.txt)")],
            plugins,
        )

        self.assertEqual(mentioned, [])

    def test_collect_explicit_plugin_mentions_ignores_dollar_linked_plugin_mentions(self) -> None:
        plugins = [plugin("sample@test", "sample")]

        mentioned = collect_explicit_plugin_mentions(
            [text_input("use [$sample](plugin://sample@test)")],
            plugins,
        )

        self.assertEqual(mentioned, [])

    def test_collectors_accept_mapping_inputs(self) -> None:
        mentioned = collect_explicit_plugin_mentions(
            [
                {"type": "text", "text": "use [@sample](plugin://sample@test)"},
                {"type": "mention", "name": "calendar", "path": "app://calendar"},
            ],
            [{"configName": "sample@test", "displayName": "sample", "hasSkills": True}],
        )

        self.assertEqual(collect_explicit_app_ids([{"type": "mention", "path": "app://calendar"}]), {"calendar"})
        self.assertEqual(mentioned, [plugin("sample@test", "sample")])
        with self.assertRaisesRegex(TypeError, "text must be a string"):
            collect_explicit_app_ids([{"type": "text", "text": object()}])
        with self.assertRaisesRegex(TypeError, "path must be a string"):
            collect_explicit_app_ids([{"type": "mention", "path": object()}])

    def test_build_connector_slug_counts_uses_display_label_slug(self) -> None:
        counts = build_connector_slug_counts(
            [
                AppInfo(id="calendar", name="Google Calendar"),
                {"id": "calendar2", "name": "Google Calendar"},
                AppInfo(id="blank", name=" -- "),
            ]
        )

        self.assertEqual(counts, {"google-calendar": 2, "app": 1})
        with self.assertRaisesRegex(TypeError, "connector name must be a string"):
            build_connector_slug_counts([{"name": 123}])


if __name__ == "__main__":
    unittest.main()
