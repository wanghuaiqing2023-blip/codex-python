"""Parity tests for ``codex-tui/src/diff_model.rs``."""

from pathlib import Path

import pytest

from pycodex.tui.diff_model import FileChange


def test_file_change_add_serializes_with_snake_case_tag() -> None:
    # Rust: #[serde(tag = "type", rename_all = "snake_case")] FileChange::Add
    change = FileChange.add("hello\n")
    assert change.is_add()
    assert change.to_dict() == {"type": "add", "content": "hello\n"}
    assert FileChange.from_dict(change.to_dict()) == change


def test_file_change_delete_serializes_with_snake_case_tag() -> None:
    # Rust: FileChange::Delete { content }
    change = FileChange.delete("gone\n")
    assert change.is_delete()
    assert change.to_dict() == {"type": "delete", "content": "gone\n"}
    assert FileChange.from_dict(change.to_dict()) == change


def test_file_change_update_serializes_unified_diff_and_optional_move_path() -> None:
    # Rust: FileChange::Update { unified_diff, move_path: Option<PathBuf> }
    without_move = FileChange.update("@@ -1 +1 @@\n")
    assert without_move.is_update()
    assert without_move.to_dict() == {
        "type": "update",
        "unified_diff": "@@ -1 +1 @@\n",
        "move_path": None,
    }
    assert FileChange.from_dict(without_move.to_dict()) == without_move

    with_move = FileChange.update("diff", Path("new/name.txt"))
    assert with_move.to_dict() == {
        "type": "update",
        "unified_diff": "diff",
        "move_path": "new/name.txt",
    }
    assert FileChange.from_dict(with_move.to_dict()) == with_move


def test_file_change_rejects_unknown_or_malformed_variants() -> None:
    # Rust serde rejects unknown enum tags and missing/wrong-typed variant fields.
    with pytest.raises(ValueError):
        FileChange.from_dict({"type": "rename", "content": "x"})
    with pytest.raises(TypeError):
        FileChange.from_dict({"type": "add"})
    with pytest.raises(TypeError):
        FileChange.from_dict({"type": "update", "unified_diff": "x", "move_path": 123})
    with pytest.raises(ValueError):
        FileChange(type="unknown").to_dict()


def test_file_change_to_dict_requires_variant_fields() -> None:
    # Rust enum variants cannot be constructed without their required fields.
    with pytest.raises(ValueError):
        FileChange(type="add").to_dict()
    with pytest.raises(ValueError):
        FileChange(type="delete").to_dict()
    with pytest.raises(ValueError):
        FileChange(type="update").to_dict()
