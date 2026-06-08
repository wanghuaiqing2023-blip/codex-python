"""Re-export of path helpers from ``codex-core::utils::path_utils``.

Rust ``codex/codex-rs/core/src/utils/path_utils.rs`` re-exports
``codex_utils_path::*``. The implementation lives in
``pycodex.utils.path_utils``; this module preserves the core crate coordinate.
"""

from __future__ import annotations

from pycodex.utils.path_utils import (
    SymlinkWritePaths,
    is_wsl,
    normalize_for_native_workdir,
    normalize_for_native_workdir_with_flag,
    normalize_for_path_comparison,
    normalize_for_wsl,
    normalize_for_wsl_with_flag,
    paths_match_after_normalization,
    resolve_symlink_write_paths,
    write_atomically,
)

__all__ = [
    "SymlinkWritePaths",
    "is_wsl",
    "normalize_for_native_workdir",
    "normalize_for_native_workdir_with_flag",
    "normalize_for_path_comparison",
    "normalize_for_wsl",
    "normalize_for_wsl_with_flag",
    "paths_match_after_normalization",
    "resolve_symlink_write_paths",
    "write_atomically",
]
