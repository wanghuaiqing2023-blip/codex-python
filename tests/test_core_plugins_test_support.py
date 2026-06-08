from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from pycodex.core.plugins import test_support
from pycodex.core_plugins import OPENAI_CURATED_MARKETPLACE_NAME


def test_write_file_creates_parent_directories() -> None:
    # Rust source: codex-core/src/plugins/test_support.rs write_file.
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "a" / "b" / "fixture.txt"

        test_support.write_file(target, "hello")

        assert target.read_text(encoding="utf-8") == "hello"


def test_write_curated_plugin_matches_rust_fixture_shape() -> None:
    # Rust source: codex-core/src/plugins/test_support.rs write_curated_plugin.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        test_support.write_curated_plugin(root, "calendar")

        plugin_root = root / "plugins" / "calendar"
        plugin = json.loads((plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        assert plugin == {
            "name": "calendar",
            "description": "Plugin that includes skills, MCP servers, and app connectors",
        }
        assert (plugin_root / "skills" / "SKILL.md").read_text(encoding="utf-8") == (
            "---\nname: sample\ndescription: sample\n---\n"
        )
        assert json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8")) == {
            "mcpServers": {
                "sample-docs": {
                    "type": "http",
                    "url": "https://sample.example/mcp",
                }
            }
        }
        assert json.loads((plugin_root / ".app.json").read_text(encoding="utf-8")) == {
            "apps": {"calendar": {"id": "connector_calendar"}}
        }


def test_write_openai_curated_marketplace_and_plugins() -> None:
    # Rust source: codex-core/src/plugins/test_support.rs write_openai_curated_marketplace.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        test_support.write_openai_curated_marketplace(root, ["github", "slack"])

        marketplace = json.loads((root / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
        assert marketplace == {
            "name": OPENAI_CURATED_MARKETPLACE_NAME,
            "plugins": [
                {"name": "github", "source": {"source": "local", "path": "./plugins/github"}},
                {"name": "slack", "source": {"source": "local", "path": "./plugins/slack"}},
            ],
        }
        assert (root / "plugins" / "github" / ".codex-plugin" / "plugin.json").exists()
        assert (root / "plugins" / "slack" / ".codex-plugin" / "plugin.json").exists()


def test_curated_plugin_sha_and_feature_config() -> None:
    # Rust source: codex-core/src/plugins/test_support.rs SHA/config helpers.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        test_support.write_curated_plugin_sha(root)
        assert (root / ".tmp" / "plugins.sha").read_text(encoding="utf-8") == (
            test_support.TEST_CURATED_PLUGIN_SHA + "\n"
        )

        test_support.write_curated_plugin_sha_with(root, "abc123")
        assert (root / ".tmp" / "plugins.sha").read_text(encoding="utf-8") == "abc123\n"

        test_support.write_plugins_feature_config(root)
        assert (root / "config.toml").read_text(encoding="utf-8") == "[features]\nplugins = true\n"


def test_load_plugins_config_reads_plugins_feature() -> None:
    # Rust source: codex-core/src/plugins/test_support.rs load_plugins_config.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        test_support.write_plugins_feature_config(root)

        config = asyncio.run(test_support.load_plugins_config(root))

        assert config.codex_home == root
        assert config.fallback_cwd == root
        assert config.plugins_enabled is True
        assert config.raw_config == {"features": {"plugins": True}}
