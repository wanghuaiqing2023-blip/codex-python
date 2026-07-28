from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest


def test_curated_snapshot_paths_and_sha_require_manifest_and_sha(
    tmp_path: Path,
) -> None:
    from pycodex.core_plugins.startup_sync import (
        curated_plugins_repo_path,
        has_local_curated_plugins_snapshot,
        read_curated_plugins_sha,
    )

    repo = curated_plugins_repo_path(tmp_path)
    assert repo == tmp_path / ".tmp" / "plugins"
    assert read_curated_plugins_sha(tmp_path) is None
    assert not has_local_curated_plugins_snapshot(tmp_path)

    manifest = repo / ".agents" / "plugins" / "marketplace.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}\n", encoding="utf-8")
    assert not has_local_curated_plugins_snapshot(tmp_path)

    sha = tmp_path / ".tmp" / "plugins.sha"
    sha.write_text("abc123\n", encoding="utf-8")
    assert read_curated_plugins_sha(tmp_path) == "abc123"
    assert has_local_curated_plugins_snapshot(tmp_path)


def test_extract_zipball_strips_single_archive_root_and_rejects_traversal(
    tmp_path: Path,
) -> None:
    from pycodex.core_plugins.startup_sync import extract_zipball_to_dir

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "openai-plugins-abc/.agents/plugins/marketplace.json",
            "{}\n",
        )
    destination = tmp_path / "out"
    extract_zipball_to_dir(output.getvalue(), destination)
    assert (
        destination / ".agents" / "plugins" / "marketplace.json"
    ).read_text(encoding="utf-8") == "{}\n"

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("root/../../escape", "bad")
    with pytest.raises(ValueError, match="escapes extraction root"):
        extract_zipball_to_dir(output.getvalue(), tmp_path / "unsafe")
