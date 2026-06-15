import unittest

from pycodex.config import record_origins, version_for_toml


class ConfigFingerprintTests(unittest.TestCase):
    def test_version_for_toml_hashes_canonical_json_with_sorted_object_keys(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/fingerprint.rs
        # Behavior anchor: version_for_toml canonicalizes JSON object keys
        # before serializing and hashing with SHA-256.
        left = {"b": 1, "a": 2}
        right = {"a": 2, "b": 1}

        self.assertEqual(
            version_for_toml(left),
            "sha256:d3626ac30a87e6f7a6428233b3c68299976865fa5508e4267c5415c76af7a772",
        )
        self.assertEqual(version_for_toml(left), version_for_toml(right))

    def test_version_for_toml_recurses_into_arrays_and_nested_tables(self) -> None:
        # Rust module: src/fingerprint.rs
        # Behavior anchor: arrays preserve order while nested object keys are
        # canonicalized recursively.
        value = {"n": None, "arr": [{"z": False, "a": "x"}, 3]}

        self.assertEqual(
            version_for_toml(value),
            "sha256:34d8f8836ff3e499fcb99c4869bec6b6f404304ce82242336ce7fa03c0323bf8",
        )
        self.assertNotEqual(
            version_for_toml(value),
            version_for_toml({"n": None, "arr": [3, {"z": False, "a": "x"}]}),
        )

    def test_record_origins_records_only_leaf_paths_with_array_indexes(self) -> None:
        # Rust module: src/fingerprint.rs
        # Behavior anchor: record_origins traverses tables and arrays, records
        # scalar leaves, and joins path components with dots.
        metadata = {"name": "session-flags", "version": "sha256:test"}
        origins = record_origins(
            {
                "model": "gpt",
                "profiles": {
                    "work": {
                        "tools": ["shell", "patch"],
                        "empty": {},
                    }
                },
            },
            metadata,
        )

        self.assertEqual(
            origins,
            {
                "model": metadata,
                "profiles.work.tools.0": metadata,
                "profiles.work.tools.1": metadata,
            },
        )
        self.assertNotIn("profiles", origins)
        self.assertNotIn("profiles.work.empty", origins)

    def test_record_origins_ignores_root_scalar_like_rust_empty_path_guard(self) -> None:
        # Rust module: src/fingerprint.rs
        # Behavior anchor: a scalar at an empty root path is not inserted.
        self.assertEqual(record_origins("model", "meta"), {})


if __name__ == "__main__":
    unittest.main()
