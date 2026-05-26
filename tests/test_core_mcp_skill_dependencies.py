from __future__ import annotations

import unittest

from pycodex.core import (
    DEFAULT_MCP_SERVER_ENVIRONMENT_ID,
    McpServerConfig,
    McpServerTransportConfig,
    SkillDependencies,
    SkillMetadata,
    SkillToolDependency,
    canonical_mcp_dependency_key,
    canonical_mcp_key,
    canonical_mcp_server_key,
    collect_missing_mcp_dependencies,
    filter_prompted_mcp_dependencies,
    format_missing_mcp_dependencies,
    mcp_dependency_to_server_config,
)


class McpSkillDependenciesTests(unittest.TestCase):
    def test_canonical_mcp_key_trims_identifier_and_falls_back(self) -> None:
        self.assertEqual(
            canonical_mcp_key("streamable_http", " https://example.test/mcp ", "server"),
            "mcp__streamable_http__https://example.test/mcp",
        )
        self.assertEqual(canonical_mcp_key("stdio", "   ", "server"), "server")

    def test_canonical_server_key_uses_transport_identifier(self) -> None:
        http = McpServerConfig(McpServerTransportConfig.streamable_http("https://example.test/mcp"))
        stdio = McpServerConfig(McpServerTransportConfig.stdio("node"))

        self.assertEqual(canonical_mcp_server_key("http", http), "mcp__streamable_http__https://example.test/mcp")
        self.assertEqual(canonical_mcp_server_key("stdio", stdio), "mcp__stdio__node")

    def test_dependency_key_defaults_to_streamable_http(self) -> None:
        dependency = SkillToolDependency(
            type="mcp",
            value="docs",
            url="https://example.test/mcp",
        )

        self.assertEqual(canonical_mcp_dependency_key(dependency), "mcp__streamable_http__https://example.test/mcp")

    def test_dependency_key_supports_stdio_case_insensitively(self) -> None:
        dependency = SkillToolDependency(type="mcp", value="runner", transport="STDIO", command="uvx")

        self.assertEqual(canonical_mcp_dependency_key(dependency), "mcp__stdio__uvx")

    def test_dependency_key_rejects_missing_or_unsupported_transport(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing url"):
            canonical_mcp_dependency_key(SkillToolDependency(type="mcp", value="docs"))
        with self.assertRaisesRegex(ValueError, "missing command"):
            canonical_mcp_dependency_key(SkillToolDependency(type="mcp", value="runner", transport="stdio"))
        with self.assertRaisesRegex(ValueError, "unsupported transport websocket"):
            canonical_mcp_dependency_key(SkillToolDependency(type="mcp", value="x", transport="websocket"))

    def test_dependency_to_server_config_uses_upstream_defaults(self) -> None:
        http = mcp_dependency_to_server_config(
            SkillToolDependency(type="mcp", value="docs", url="https://example.test/mcp")
        )
        stdio = mcp_dependency_to_server_config(
            SkillToolDependency(type="mcp", value="runner", transport="stdio", command="uvx")
        )

        self.assertEqual(http.environment_id, DEFAULT_MCP_SERVER_ENVIRONMENT_ID)
        self.assertTrue(http.enabled)
        self.assertFalse(http.required)
        self.assertFalse(http.supports_parallel_tool_calls)
        self.assertEqual(http.transport.kind, "streamable_http")
        self.assertEqual(http.transport.url, "https://example.test/mcp")
        self.assertEqual(stdio.transport.kind, "stdio")
        self.assertEqual(stdio.transport.command, "uvx")
        self.assertEqual(stdio.transport.args, ())

    def test_collect_missing_mcp_dependencies_skips_installed_duplicates_and_non_mcp(self) -> None:
        installed = {
            "docs": McpServerConfig(McpServerTransportConfig.streamable_http("https://installed.test/mcp")),
        }
        mentioned = [
            SkillMetadata(
                name="skill-a",
                dependencies=SkillDependencies(
                    (
                        SkillToolDependency(type="mcp", value="docs", url="https://installed.test/mcp"),
                        SkillToolDependency(type="MCP", value="runner", transport="stdio", command="uvx"),
                        SkillToolDependency(type="mcp", value="runner-duplicate", transport="stdio", command="uvx"),
                        SkillToolDependency(type="web", value="not-mcp", url="https://example.test"),
                    )
                ),
            )
        ]

        missing = collect_missing_mcp_dependencies(mentioned, installed)

        self.assertEqual(list(missing), ["runner"])
        self.assertEqual(missing["runner"].transport.command, "uvx")

    def test_collect_missing_mcp_dependencies_ignores_invalid_entries(self) -> None:
        mentioned = [
            SkillMetadata(
                name="skill-a",
                dependencies=SkillDependencies(
                    (
                        SkillToolDependency(type="mcp", value="bad-http"),
                        SkillToolDependency(type="mcp", value="bad-transport", transport="websocket", url="x"),
                        SkillToolDependency(type="mcp", value="good", url="https://example.test/mcp"),
                    )
                ),
            )
        ]

        missing = collect_missing_mcp_dependencies(mentioned, {})

        self.assertEqual(list(missing), ["good"])

    def test_filter_prompted_mcp_dependencies_uses_canonical_server_keys(self) -> None:
        missing = {
            "docs": McpServerConfig(McpServerTransportConfig.streamable_http("https://example.test/mcp")),
            "runner": McpServerConfig(McpServerTransportConfig.stdio("uvx")),
        }
        prompted = {"mcp__streamable_http__https://example.test/mcp"}

        filtered = filter_prompted_mcp_dependencies(missing, prompted)

        self.assertEqual(list(filtered), ["runner"])

    def test_format_missing_mcp_dependencies_sorts_names(self) -> None:
        missing = {
            "zeta": McpServerConfig(McpServerTransportConfig.stdio("z")),
            "alpha": McpServerConfig(McpServerTransportConfig.stdio("a")),
        }

        self.assertEqual(format_missing_mcp_dependencies(missing), "alpha, zeta")


if __name__ == "__main__":
    unittest.main()
