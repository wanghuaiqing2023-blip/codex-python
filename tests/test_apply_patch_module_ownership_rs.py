"""Rust-derived ownership checks for codex-apply-patch.

Rust baseline: 1c7832ffa37a3ab56f601497c00bfce120370bf9.
"""

from pycodex import apply_patch


def test_apply_patch_child_items_are_owned_by_matching_modules() -> None:
    # codex-rs/apply-patch/src/lib.rs declares these five child modules.
    from pycodex.apply_patch.invocation import MaybeApplyPatch, maybe_parse_apply_patch
    from pycodex.apply_patch.standalone_executable import (
        StandaloneApplyPatchResult,
        run_main,
    )

    expected_owners = {
        MaybeApplyPatch: "pycodex.apply_patch.invocation",
        maybe_parse_apply_patch: "pycodex.apply_patch.invocation",
        apply_patch.ApplyPatchParseError: "pycodex.apply_patch.parser",
        apply_patch.Hunk: "pycodex.apply_patch.parser",
        apply_patch.UpdateFileChunk: "pycodex.apply_patch.parser",
        apply_patch.parse_patch: "pycodex.apply_patch.parser",
        apply_patch.StreamingPatchParser: "pycodex.apply_patch.streaming_parser",
        StandaloneApplyPatchResult: "pycodex.apply_patch.standalone_executable",
        run_main: "pycodex.apply_patch.standalone_executable",
    }

    for item, expected_owner in expected_owners.items():
        assert item.__module__ == expected_owner


def test_apply_patch_root_reexports_match_rust_lib() -> None:
    # lib.rs publicly re-exports parser, streaming parser, verified invocation,
    # and standalone entrypoint APIs from their owning child modules.
    from pycodex.apply_patch.invocation import maybe_parse_apply_patch_verified
    from pycodex.apply_patch.parser import Hunk, parse_patch
    from pycodex.apply_patch.streaming_parser import StreamingPatchParser

    assert apply_patch.Hunk is Hunk
    assert apply_patch.parse_patch is parse_patch
    assert apply_patch.StreamingPatchParser is StreamingPatchParser
    assert apply_patch.maybe_parse_apply_patch_verified is maybe_parse_apply_patch_verified
