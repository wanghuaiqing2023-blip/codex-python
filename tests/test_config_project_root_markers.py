import unittest

from pycodex.config import (
    PROJECT_ROOT_MARKERS_ERROR,
    default_project_root_markers,
    project_root_markers_from_config,
)


class ConfigProjectRootMarkersTests(unittest.TestCase):
    def test_default_project_root_markers_returns_git_marker(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/project_root_markers.rs
        # Behavior anchor: DEFAULT_PROJECT_ROOT_MARKERS contains only ".git".
        self.assertEqual(default_project_root_markers(), [".git"])

    def test_project_root_markers_from_config_returns_none_when_absent_or_non_table(self) -> None:
        # Rust module: src/project_root_markers.rs
        # Behavior anchor: absent project_root_markers returns Ok(None).
        self.assertIsNone(project_root_markers_from_config({}))
        self.assertIsNone(project_root_markers_from_config(False))

    def test_project_root_markers_from_config_accepts_string_array_and_empty_array(self) -> None:
        # Rust module: src/project_root_markers.rs
        # Behavior anchor: specified arrays return Some(markers), including
        # Some(Vec::new()) for an empty array that disables root detection.
        self.assertEqual(
            project_root_markers_from_config({"project_root_markers": [".git", ".codex-root"]}),
            [".git", ".codex-root"],
        )
        self.assertEqual(project_root_markers_from_config({"project_root_markers": []}), [])

    def test_project_root_markers_from_config_rejects_non_array_or_non_string_entries(self) -> None:
        # Rust module: src/project_root_markers.rs
        # Behavior anchor: invalid specified values return InvalidData.
        for config in (
            {"project_root_markers": ".git"},
            {"project_root_markers": [".git", 1]},
        ):
            with self.subTest(config=config):
                with self.assertRaisesRegex(ValueError, PROJECT_ROOT_MARKERS_ERROR):
                    project_root_markers_from_config(config)


if __name__ == "__main__":
    unittest.main()
