from __future__ import annotations

import importlib


def test_git_utils_items_follow_rust_module_owners() -> None:
    expected = {
        "apply": ("ApplyGitRequest", "apply_git_patch"),
        "baseline": ("GitBaselineDiff", "diff_since_latest_init"),
        "branch": ("merge_base_with_head",),
        "errors": ("GitToolingError",),
        "info": ("collect_git_info", "GitDiffToRemote"),
        "operations": ("ensure_git_repository", "resolve_head"),
        "platform": ("create_symlink",),
    }

    for module_name, names in expected.items():
        module = importlib.import_module(f"pycodex.git_utils.{module_name}")
        for name in names:
            assert getattr(module, name).__module__ == module.__name__
