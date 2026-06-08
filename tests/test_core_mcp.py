import unittest

from pycodex.core.mcp import (
    McpDelegates,
    McpManager,
    collect_tool_plugin_provenance,
    configured_mcp_servers,
    effective_mcp_servers,
)


class AsyncConfig:
    def __init__(self) -> None:
        self.calls = 0

    async def to_mcp_config(self, plugins_manager: object) -> dict[str, object]:
        self.calls += 1
        return {
            "servers": {"filesystem": {"command": "fs"}},
            "effective_servers": {"filesystem": {"command": "fs", "auth": "ok"}},
            "tool_plugin_provenance": {"filesystem": {"plugin": "core"}},
            "plugins_manager": plugins_manager,
        }


class SyncConfig:
    def __init__(self) -> None:
        self.plugins_manager = None

    def to_mcp_config(self, plugins_manager: object) -> dict[str, object]:
        self.plugins_manager = plugins_manager
        return {"servers": {"local": {"command": "run"}}}


class McpManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_manager_delegates_through_config_to_mcp_config(self) -> None:
        config = AsyncConfig()
        manager = McpManager(plugins_manager={"plugins": []})

        self.assertEqual(await manager.configured_servers(config), {"filesystem": {"command": "fs"}})
        self.assertEqual(await manager.effective_servers(config, auth={"user": "u"}), {"filesystem": {"command": "fs", "auth": "ok"}})
        self.assertEqual(await manager.tool_plugin_provenance(config), {"filesystem": {"plugin": "core"}})
        self.assertEqual(config.calls, 3)

    async def test_manager_accepts_injected_delegate_functions(self) -> None:
        manager = McpManager(
            plugins_manager=None,
            delegates=McpDelegates(
                configured_mcp_servers=lambda _cfg: {"a": {"kind": "configured"}},
                effective_mcp_servers=lambda _cfg, auth: {"a": {"auth": auth}},
                tool_plugin_provenance=lambda _cfg: {"a": {"plugin": "p"}},
            ),
        )

        self.assertEqual(await manager.configured_servers({"servers": {}}), {"a": {"kind": "configured"}})
        self.assertEqual(await manager.effective_servers({"servers": {}}, auth="token"), {"a": {"auth": "token"}})
        self.assertEqual(await manager.tool_plugin_provenance({"servers": {}}), {"a": {"plugin": "p"}})

    async def test_manager_accepts_sync_to_mcp_config(self) -> None:
        config = SyncConfig()
        plugins_manager = {"plugins": ["p"]}
        manager = McpManager(plugins_manager=plugins_manager)

        self.assertEqual(
            await manager.configured_servers(config),
            {"local": {"command": "run"}},
        )
        self.assertIs(config.plugins_manager, plugins_manager)

    async def test_manager_rejects_non_mapping_delegate_server_results(self) -> None:
        manager = McpManager(
            plugins_manager=None,
            delegates=McpDelegates(
                configured_mcp_servers=lambda _cfg: ["not", "a", "mapping"],
            ),
        )

        with self.assertRaisesRegex(TypeError, "configured_mcp_servers must be a mapping"):
            await manager.configured_servers({"servers": {}})


class McpPureHelpersTests(unittest.TestCase):
    def test_configured_servers_prefers_configured_servers_then_servers(self) -> None:
        self.assertEqual(
            configured_mcp_servers({"configured_servers": {"a": {"url": "one"}}, "servers": {"b": {"url": "two"}}}),
            {"a": {"url": "one"}},
        )
        self.assertEqual(configured_mcp_servers({"servers": {"b": {"url": "two"}}}), {"b": {"url": "two"}})

    def test_effective_servers_falls_back_to_configured_servers(self) -> None:
        self.assertEqual(effective_mcp_servers({"servers": {"b": {"url": "two"}}}), {"b": {"url": "two"}})

    def test_tool_plugin_provenance_defaults_to_empty(self) -> None:
        self.assertEqual(collect_tool_plugin_provenance({"servers": {}}), {})


if __name__ == "__main__":
    unittest.main()
