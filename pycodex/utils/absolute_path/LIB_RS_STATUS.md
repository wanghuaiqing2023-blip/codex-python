# codex-utils-absolute-path src/lib.rs status

Rust coordinate: `codex/codex-rs/utils/absolute-path/src/lib.rs`

Python coordinate: `pycodex/utils/absolute_path/__init__.py`

Status: `complete`

Behavior contract:

- `AbsolutePathBuf` stores normalized absolute paths and rejects checked relative inputs.
- paths can be resolved against explicit bases, the current directory, or an active deserialization guard.
- `join`, `parent`, `ancestors`, path conversion, display, and string helpers preserve the absolute-path wrapper boundary.
- canonicalization returns another `AbsolutePathBuf` and errors for missing existing paths.
- `AbsolutePathBufGuard` supplies a thread-local/context-local base for deserializing relative paths.
- `~`, `~/...`, and doubled-slash home subpaths expand to the home directory.
- Windows verbatim/device prefixes are normalized for supported drive and UNC forms.
- symlink-preserving canonicalization keeps logical paths when canonicalization would rewrite nested symlinks, and propagates errors for existing-path canonicalization.

Evidence:

- `tests/test_utils_absolute_path_absolutize.py` includes Rust-derived tests for `src/lib.rs` public behavior and crate-local normalization helpers.
- With `src/absolutize.rs` already certified, this completes the crate module set.
