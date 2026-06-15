import asyncio
import tempfile
import unittest
from pathlib import Path

from pycodex.config import (
    PluginConfigEdit,
    apply_user_plugin_config_edits,
    clear_user_plugin,
    set_user_plugin_enabled,
)
from pycodex.config import toml_compat as toml


def run(coro):
    return asyncio.run(coro)


class ConfigPluginEditTests(unittest.TestCase):
    def test_set_user_plugin_enabled_writes_plugin_entry(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/plugin_edit.rs
        # Rust test: set_user_plugin_enabled_writes_plugin_entry
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)

            run(set_user_plugin_enabled(home, "demo@market", True))

            self.assertEqual(
                _read_config(home),
                {"plugins": {"demo@market": {"enabled": True}}},
            )

    def test_set_user_plugin_enabled_preserves_existing_plugin_fields(self) -> None:
        # Rust test: set_user_plugin_enabled_preserves_existing_plugin_fields
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "config.toml").write_text(
                """
[plugins."demo@market"]
enabled = false
source = "/tmp/plugin"
""",
                encoding="utf-8",
            )

            run(set_user_plugin_enabled(home, "demo@market", True))

            self.assertEqual(
                _read_config(home),
                {"plugins": {"demo@market": {"enabled": True, "source": "/tmp/plugin"}}},
            )

    def test_clear_user_plugin_removes_empty_plugins_table(self) -> None:
        # Rust test: clear_user_plugin_removes_empty_plugins_table
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "config.toml").write_text(
                """
[plugins."demo@market"]
enabled = true
""",
                encoding="utf-8",
            )

            run(clear_user_plugin(home, "demo@market"))

            self.assertEqual((home / "config.toml").read_text(encoding="utf-8"), "")

    def test_clear_user_plugin_missing_entry_does_not_create_config(self) -> None:
        # Rust test: clear_user_plugin_missing_entry_does_not_create_config
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)

            run(clear_user_plugin(home, "demo@market"))

            self.assertFalse((home / "config.toml").exists())

    def test_apply_user_plugin_config_edits_noops_for_empty_edits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)

            run(apply_user_plugin_config_edits(home, []))

            self.assertFalse((home / "config.toml").exists())

    def test_apply_user_plugin_config_edits_applies_ordered_edits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)

            run(
                apply_user_plugin_config_edits(
                    home,
                    [
                        PluginConfigEdit.set_enabled("demo@market", True),
                        PluginConfigEdit.set_enabled("other@market", False),
                        PluginConfigEdit.clear("demo@market"),
                    ],
                )
            )

            self.assertEqual(
                _read_config(home),
                {"plugins": {"other@market": {"enabled": False}}},
            )


def _read_config(home: Path) -> dict[str, object]:
    return dict(toml.loads((home / "config.toml").read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
