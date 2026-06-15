import tempfile
import unittest
from pathlib import Path

from pycodex.config import (
    MarketplaceConfigUpdate,
    RemoveMarketplaceConfigOutcome,
    RemoveMarketplaceConfigResult,
    record_user_marketplace,
    remove_user_marketplace,
    remove_user_marketplace_config,
)
from pycodex.config import toml_compat as toml


class ConfigMarketplaceEditTests(unittest.TestCase):
    def test_remove_user_marketplace_removes_requested_entry(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/marketplace_edit.rs
        # Rust test: remove_user_marketplace_removes_requested_entry
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            update = _update()
            record_user_marketplace(home, "debug", update)
            record_user_marketplace(home, "other", update)

            removed = remove_user_marketplace(home, "debug")

            self.assertTrue(removed)
            marketplaces = _read_config(home)["marketplaces"]
            self.assertEqual(len(marketplaces), 1)
            self.assertIn("other", marketplaces)

    def test_remove_user_marketplace_returns_false_when_missing(self) -> None:
        # Rust test: remove_user_marketplace_returns_false_when_missing
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(remove_user_marketplace(Path(tmp), "debug"))

    def test_remove_user_marketplace_config_reports_case_mismatch(self) -> None:
        # Rust test: remove_user_marketplace_config_reports_case_mismatch
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            record_user_marketplace(home, "debug", _update())

            outcome = remove_user_marketplace_config(home, "Debug")

            self.assertEqual(outcome, RemoveMarketplaceConfigResult.name_case_mismatch("debug"))

    def test_remove_user_marketplace_config_removes_inline_table_entry(self) -> None:
        # Rust test: remove_user_marketplace_config_removes_inline_table_entry
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "config.toml").write_text(
                """
marketplaces = {
  debug = { source_type = "git", source = "https://github.com/owner/repo.git" },
  other = { source_type = "local", source = "/tmp/marketplace" },
}
""",
                encoding="utf-8",
            )

            outcome = remove_user_marketplace_config(home, "debug")

            self.assertEqual(outcome.outcome, RemoveMarketplaceConfigOutcome.REMOVED)
            marketplaces = _read_config(home)["marketplaces"]
            self.assertEqual(len(marketplaces), 1)
            self.assertIn("other", marketplaces)

    def test_record_user_marketplace_writes_optional_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            update = MarketplaceConfigUpdate(
                last_updated="2026-04-13T00:00:00Z",
                last_revision="rev-1",
                source_type="git",
                source="https://github.com/owner/repo.git",
                ref_name="main",
                sparse_paths=("plugins/a", "plugins/b"),
            )

            record_user_marketplace(home, "debug", update)

            entry = _read_config(home)["marketplaces"]["debug"]
            self.assertEqual(entry["last_revision"], "rev-1")
            self.assertEqual(entry["ref"], "main")
            self.assertEqual(entry["sparse_paths"], ["plugins/a", "plugins/b"])


def _update() -> MarketplaceConfigUpdate:
    return MarketplaceConfigUpdate(
        last_updated="2026-04-13T00:00:00Z",
        source_type="git",
        source="https://github.com/owner/repo.git",
        ref_name="main",
    )


def _read_config(home: Path) -> dict[str, object]:
    return dict(toml.loads((home / "config.toml").read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
