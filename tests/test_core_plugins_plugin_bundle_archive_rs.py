from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest


def _plugin(root: Path) -> Path:
    plugin = root / "demo"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / ".codex-plugin" / "plugin.json").write_text(
        '{"name":"demo"}\n',
        encoding="utf-8",
    )
    (plugin / "README.md").write_text("demo\n", encoding="utf-8")
    return plugin


def _tar_gz(entries: list[tuple[str, bytes, int]]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, contents, entry_type in entries:
            info = tarfile.TarInfo(name)
            info.type = entry_type
            info.size = len(contents)
            archive.addfile(info, io.BytesIO(contents))
    return output.getvalue()


def test_pack_requires_plugin_directory_and_manifest(tmp_path: Path) -> None:
    from pycodex.core_plugins.plugin_bundle_archive import (
        InvalidPluginPathError,
        pack_plugin_bundle_tar_gz,
    )

    with pytest.raises(InvalidPluginPathError, match="expected a plugin directory"):
        pack_plugin_bundle_tar_gz(tmp_path / "missing", 1024)

    plugin = tmp_path / "plugin"
    plugin.mkdir()
    with pytest.raises(InvalidPluginPathError, match="missing .codex-plugin/plugin.json"):
        pack_plugin_bundle_tar_gz(plugin, 1024)


def test_pack_and_unpack_plugin_tree(tmp_path: Path) -> None:
    from pycodex.core_plugins.plugin_bundle_archive import (
        pack_plugin_bundle_tar_gz,
        unpack_plugin_bundle_tar_gz,
    )

    plugin = _plugin(tmp_path)
    archive = pack_plugin_bundle_tar_gz(plugin, 64 * 1024)
    destination = tmp_path / "unpacked"
    unpack_plugin_bundle_tar_gz(archive, destination, 64 * 1024)

    assert (destination / ".codex-plugin" / "plugin.json").read_text(
        encoding="utf-8"
    ) == '{"name":"demo"}\n'
    assert (destination / "README.md").read_text(encoding="utf-8") == "demo\n"


def test_pack_enforces_compressed_archive_limit(tmp_path: Path) -> None:
    from pycodex.core_plugins.plugin_bundle_archive import (
        ArchiveTooLargeError,
        pack_plugin_bundle_tar_gz,
    )

    plugin = _plugin(tmp_path)
    with pytest.raises(ArchiveTooLargeError):
        pack_plugin_bundle_tar_gz(plugin, 1)


@pytest.mark.parametrize(
    ("entry_name", "entry_type", "message"),
    [
        ("../escape", tarfile.REGTYPE, "escapes extraction root"),
        ("/absolute", tarfile.REGTYPE, "escapes extraction root"),
        ("link", tarfile.SYMTYPE, "is a link"),
    ],
)
def test_unpack_rejects_unsafe_entries(
    tmp_path: Path,
    entry_name: str,
    entry_type: int,
    message: str,
) -> None:
    from pycodex.core_plugins.plugin_bundle_archive import (
        InvalidPluginBundleError,
        unpack_plugin_bundle_tar_gz,
    )

    archive = _tar_gz([(entry_name, b"x", entry_type)])
    with pytest.raises(InvalidPluginBundleError, match=message):
        unpack_plugin_bundle_tar_gz(archive, tmp_path / "out", 1024)


def test_unpack_enforces_total_extracted_size(tmp_path: Path) -> None:
    from pycodex.core_plugins.plugin_bundle_archive import (
        ExtractedBundleTooLargeError,
        unpack_plugin_bundle_tar_gz,
    )

    archive = _tar_gz(
        [
            ("one", b"1234", tarfile.REGTYPE),
            ("two", b"5678", tarfile.REGTYPE),
        ]
    )
    with pytest.raises(ExtractedBundleTooLargeError) as exc_info:
        unpack_plugin_bundle_tar_gz(archive, tmp_path / "out", 7)

    assert exc_info.value.bytes == 8
    assert exc_info.value.max_bytes == 7
