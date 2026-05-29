from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pycodex.core import (
    CONFIG_LOCK_VERSION,
    ConfigLockError,
    ConfigLockReplayOptions,
    ConfigLockfile,
    clear_config_lock_debug_controls,
    config_lock_for_comparison,
    config_lockfile,
    config_without_lock_controls,
    lock_layer_from_config,
    read_config_lock_from_path,
    toml_value,
    validate_config_lock_metadata_shape,
    validate_config_lock_replay,
)


class ConfigLockTests(unittest.TestCase):
    def test_config_lockfile_sets_version_and_copies_config(self) -> None:
        config = {"model": "gpt-5", "debug": {"config_lockfile": {"path": "lock.toml"}}}

        lockfile = config_lockfile(config, codex_version="1.2.3")
        config["model"] = "changed"

        self.assertEqual(lockfile.version, CONFIG_LOCK_VERSION)
        self.assertEqual(lockfile.codex_version, "1.2.3")
        self.assertEqual(lockfile.config["model"], "gpt-5")
        with self.assertRaisesRegex(ConfigLockError, "codex_version must be a string"):
            config_lockfile({}, codex_version=123)  # type: ignore[arg-type]

    def test_clear_config_lock_debug_controls_removes_nested_control(self) -> None:
        config = {"debug": {"config_lockfile": {"allow_codex_version_mismatch": True}}}

        clear_config_lock_debug_controls(config)

        self.assertEqual(config, {})
        with self.assertRaisesRegex(ConfigLockError, "config must be a mutable mapping"):
            clear_config_lock_debug_controls({"debug": {"config_lockfile": {}}}.items())  # type: ignore[arg-type]

    def test_clear_config_lock_debug_controls_preserves_other_debug_fields(self) -> None:
        config = {"debug": {"config_lockfile": {"path": "lock.toml"}, "trace": True}}

        clear_config_lock_debug_controls(config)

        self.assertEqual(config, {"debug": {"trace": True}})

    def test_config_without_lock_controls_does_not_mutate_input(self) -> None:
        config = {"model": "gpt-5", "debug": {"config_lockfile": {"path": "lock.toml"}}}

        without_controls = config_without_lock_controls(config)

        self.assertEqual(without_controls, {"model": "gpt-5"})
        self.assertIn("debug", config)

    def test_validate_config_lock_replay_accepts_matching_config_without_debug_controls(self) -> None:
        expected = config_lockfile(
            {"model": "gpt-5", "debug": {"config_lockfile": {"path": "lock.toml"}}},
            codex_version="1.0.0",
        )
        actual = config_lockfile({"model": "gpt-5"}, codex_version="1.0.0")

        validate_config_lock_replay(expected, actual)

    def test_validate_config_lock_replay_rejects_codex_version_mismatch(self) -> None:
        expected = config_lockfile({"model": "gpt-5"}, codex_version="1.0.0")
        actual = config_lockfile({"model": "gpt-5"}, codex_version="2.0.0")

        with self.assertRaisesRegex(ConfigLockError, "Codex version mismatch"):
            validate_config_lock_replay(expected, actual)

    def test_validate_config_lock_replay_allows_codex_version_mismatch_when_option_set(self) -> None:
        expected = config_lockfile({"model": "gpt-5"}, codex_version="1.0.0")
        actual = config_lockfile({"model": "gpt-5"}, codex_version="2.0.0")

        validate_config_lock_replay(
            expected,
            actual,
            ConfigLockReplayOptions(allow_codex_version_mismatch=True),
        )
        compared = config_lock_for_comparison(
            expected,
            ConfigLockReplayOptions(allow_codex_version_mismatch=True),
        )
        self.assertEqual(compared.codex_version, "")
        with self.assertRaisesRegex(TypeError, "allow_codex_version_mismatch must be a bool"):
            ConfigLockReplayOptions(allow_codex_version_mismatch=1)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "options must be ConfigLockReplayOptions"):
            validate_config_lock_replay(expected, actual, options=object())  # type: ignore[arg-type]

    def test_validate_config_lock_replay_rejects_unsupported_lock_version(self) -> None:
        with self.assertRaisesRegex(ConfigLockError, "unsupported config lock version 2"):
            validate_config_lock_metadata_shape(ConfigLockfile(version=2, codex_version="1.0.0", config={}))
        with self.assertRaisesRegex(ConfigLockError, "unsigned 32-bit"):
            ConfigLockfile(version=2**32, codex_version="1.0.0", config={})

    def test_validate_config_lock_replay_reports_diff(self) -> None:
        expected = config_lockfile({"model": "gpt-5"}, codex_version="1.0.0")
        actual = config_lockfile({"model": "gpt-5.1"}, codex_version="1.0.0")

        with self.assertRaises(ConfigLockError) as caught:
            validate_config_lock_replay(expected, actual)

        message = str(caught.exception)
        self.assertIn("replayed effective config does not match config lock", message)
        self.assertIn("--- expected", message)
        self.assertIn("+++ actual", message)
        self.assertIn('"model": "gpt-5"', message)
        self.assertIn('"model": "gpt-5.1"', message)

    def test_read_config_lock_from_path_parses_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.lock.toml"
            path.write_text(
                "\n".join(
                    [
                        "version = 1",
                        'codex_version = "0.1.0"',
                        "",
                        "[config]",
                        'model = "gpt-5"',
                        "",
                        "[config.debug.config_lockfile]",
                        'path = "config.lock.toml"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            lockfile = read_config_lock_from_path(path)

        self.assertEqual(lockfile.codex_version, "0.1.0")
        self.assertEqual(lockfile.config["model"], "gpt-5")
        self.assertEqual(lockfile.config["debug"]["config_lockfile"]["path"], "config.lock.toml")

    def test_lock_layer_from_config_removes_debug_controls(self) -> None:
        lockfile = config_lockfile(
            {"model": "gpt-5", "debug": {"config_lockfile": {"path": "lock.toml"}}},
            codex_version="1.0.0",
        )

        entry = lock_layer_from_config("lock.toml", lockfile)

        self.assertEqual(entry.source_file, Path("lock.toml"))
        self.assertIsNone(entry.profile)
        self.assertEqual(entry.value, {"model": "gpt-5"})
        with self.assertRaisesRegex(ConfigLockError, "source_file must be a Path"):
            type(entry)(source_file="lock.toml", profile=None, value={})  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "lock_path must be path-like"):
            lock_layer_from_config(object(), lockfile)  # type: ignore[arg-type]

    def test_toml_value_rejects_non_toml_shapes(self) -> None:
        with self.assertRaisesRegex(ConfigLockError, "non-string TOML key"):
            toml_value({1: "bad"}, "config lock")
        with self.assertRaisesRegex(ConfigLockError, "null value"):
            toml_value({"model": None}, "config lock")
        with self.assertRaisesRegex(TypeError, "label must be a string"):
            toml_value({}, 1)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
