from __future__ import annotations

import json
from pathlib import Path

from pycodex.windows_sandbox import (
    load_or_create_cap_sids,
    workspace_cap_sid_for_cwd,
    workspace_write_cap_sid_for_root,
    workspace_write_root_contains_path,
    workspace_write_root_overlaps_path,
    writable_root_cap_sid_for_path,
)


def test_equivalent_cwd_spellings_share_workspace_sid_key(tmp_path: Path) -> None:
    # Rust: codex-windows-sandbox::cap::equivalent_cwd_spellings_share_workspace_sid_key.
    codex_home = tmp_path / "codex-home"
    workspace = tmp_path / "WorkspaceRoot"
    workspace.mkdir()
    alternative = Path(str(workspace.resolve()).replace("\\", "/").upper())

    first = workspace_cap_sid_for_cwd(codex_home, workspace.resolve())
    second = workspace_cap_sid_for_cwd(codex_home, alternative)

    assert first == second
    assert len(load_or_create_cap_sids(codex_home).workspace_by_cwd) == 1


def test_write_roots_get_path_scoped_sids(tmp_path: Path) -> None:
    # Rust: codex-windows-sandbox::cap::write_roots_get_path_scoped_sids.
    codex_home = tmp_path / "codex-home"
    workspace = tmp_path / "workspace"
    extra_root = tmp_path / "extra-root"
    workspace.mkdir()
    extra_root.mkdir()

    workspace_sid = workspace_write_cap_sid_for_root(codex_home, workspace, workspace)
    extra_sid = workspace_write_cap_sid_for_root(codex_home, workspace, extra_root)

    assert workspace_sid != extra_sid
    assert extra_sid == writable_root_cap_sid_for_path(codex_home, extra_root)
    caps = load_or_create_cap_sids(codex_home)
    assert len(caps.workspace_by_cwd) == 1
    assert len(caps.writable_root_by_path) == 1


def test_legacy_single_sid_file_is_migrated(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    sid_path = codex_home / "cap_sid"
    sid_path.write_text("S-1-5-21-1-2-3-4", encoding="utf-8")

    caps = load_or_create_cap_sids(codex_home)

    assert caps.workspace == "S-1-5-21-1-2-3-4"
    assert caps.readonly.startswith("S-1-5-21-")
    assert isinstance(json.loads(sid_path.read_text(encoding="utf-8")), dict)


def test_write_root_path_relationships_use_canonical_paths(tmp_path: Path) -> None:
    root = tmp_path / "root"
    child = root / "child"
    sibling = tmp_path / "sibling"
    child.mkdir(parents=True)
    sibling.mkdir()

    assert workspace_write_root_contains_path(root, child)
    assert not workspace_write_root_contains_path(root, sibling)
    assert workspace_write_root_overlaps_path(root, child)
    assert workspace_write_root_overlaps_path(child, root)
