from __future__ import annotations

from pathlib import Path

from pycodex.core.utils import path_utils as core_path_utils
from pycodex.utils import path_utils as utility_path_utils


def test_core_utils_path_utils_reexports_utility_surface() -> None:
    # Rust source: codex/codex-rs/core/src/utils/mod.rs
    # Rust source: codex/codex-rs/core/src/utils/path_utils.rs
    # Rust crate/module: codex-core::utils::path_utils
    # Contract: core path_utils publicly re-exports codex-utils-path-utils.
    for name in utility_path_utils.__all__:
        assert getattr(core_path_utils, name) is getattr(utility_path_utils, name)


def test_core_utils_path_utils_behavior_matches_reexported_helper() -> None:
    # Rust source: codex/codex-rs/core/src/utils/path_utils.rs
    # Contract: calls through the core coordinate use the same path-utils behavior.
    normalized = core_path_utils.normalize_for_wsl_with_flag(
        Path("/mnt/C/Users/Dev"),
        True,
        is_linux=True,
    )

    assert normalized == Path("/mnt/c/users/dev")
