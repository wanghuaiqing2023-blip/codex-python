"""Safe plugin bundle tar/gzip packing and extraction.

Rust owner: ``codex-core-plugins::plugin_bundle_archive``.
"""

from __future__ import annotations

import io
import tarfile
from pathlib import Path, PurePosixPath


class PluginBundlePackError(Exception):
    """Base error raised while creating a plugin bundle archive."""


class InvalidPluginPathError(PluginBundlePackError):
    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"invalid plugin path `{path}`: {reason}")


class ArchiveTooLargeError(PluginBundlePackError):
    def __init__(self, bytes: int, max_bytes: int) -> None:
        self.bytes = bytes
        self.max_bytes = max_bytes
        super().__init__(
            f"plugin archive would be {bytes} bytes, "
            f"exceeding maximum size of {max_bytes} bytes"
        )


class PluginBundleUnpackError(Exception):
    """Base error raised while extracting a plugin bundle archive."""


class ExtractedBundleTooLargeError(PluginBundleUnpackError):
    def __init__(self, bytes: int, max_bytes: int) -> None:
        self.bytes = bytes
        self.max_bytes = max_bytes
        super().__init__(
            f"plugin bundle extracted size would be {bytes} bytes, "
            f"exceeding maximum total size of {max_bytes} bytes"
        )


class InvalidPluginBundleError(PluginBundleUnpackError):
    pass


def pack_plugin_bundle_tar_gz(plugin_path: Path, max_bytes: int) -> bytes:
    plugin_path = Path(plugin_path)
    if not plugin_path.is_dir():
        raise InvalidPluginPathError(plugin_path, "expected a plugin directory")
    if not (plugin_path / ".codex-plugin" / "plugin.json").is_file():
        raise InvalidPluginPathError(
            plugin_path,
            "missing .codex-plugin/plugin.json",
        )

    output = io.BytesIO()
    try:
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for path in sorted(
                plugin_path.rglob("*"),
                key=lambda item: item.relative_to(plugin_path).as_posix(),
            ):
                if path.is_symlink() or not (path.is_dir() or path.is_file()):
                    raise InvalidPluginPathError(
                        path,
                        f"unsupported plugin archive entry type: {path}",
                    )
                archive.add(
                    path,
                    arcname=path.relative_to(plugin_path).as_posix(),
                    recursive=False,
                )
    except PluginBundlePackError:
        raise
    except OSError as exc:
        raise PluginBundlePackError(f"failed to archive plugin bundle: {exc}") from exc

    contents = output.getvalue()
    if len(contents) > max_bytes:
        raise ArchiveTooLargeError(len(contents), max_bytes)
    return contents


def unpack_plugin_bundle_tar_gz(
    contents: bytes,
    destination: Path,
    max_total_bytes: int,
) -> None:
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    try:
        archive = tarfile.open(fileobj=io.BytesIO(contents), mode="r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise PluginBundleUnpackError(
            f"failed to read plugin bundle tar: {exc}"
        ) from exc

    extracted_bytes = 0
    with archive:
        for entry in archive:
            output_path = _checked_tar_output_path(destination, entry.name)
            if entry.isdir():
                output_path.mkdir(parents=True, exist_ok=True)
                continue
            if entry.issym() or entry.islnk():
                raise InvalidPluginBundleError(
                    f"plugin bundle tar entry `{entry.name}` is a link"
                )
            if not entry.isfile():
                raise InvalidPluginBundleError(
                    f"plugin bundle tar entry `{entry.name}` "
                    f"has unsupported type {entry.type!r}"
                )

            extracted_bytes += entry.size
            if extracted_bytes > max_total_bytes:
                raise ExtractedBundleTooLargeError(
                    extracted_bytes,
                    max_total_bytes,
                )

            source = archive.extractfile(entry)
            if source is None:
                raise InvalidPluginBundleError(
                    f"failed to read plugin bundle tar entry `{entry.name}`"
                )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with source, output_path.open("wb") as target:
                    while chunk := source.read(64 * 1024):
                        target.write(chunk)
            except OSError as exc:
                raise PluginBundleUnpackError(
                    f"failed to unpack plugin bundle entry: {exc}"
                ) from exc


def _checked_tar_output_path(destination: Path, entry_name: str) -> Path:
    normalized = entry_name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or not path.parts
        or any(part == ".." for part in path.parts)
    ):
        raise InvalidPluginBundleError(
            f"plugin bundle tar entry `{entry_name}` escapes extraction root"
        )

    parts = [part for part in path.parts if part not in {"", "."}]
    if not parts:
        raise InvalidPluginBundleError("plugin bundle tar entry has an empty path")
    return destination.joinpath(*parts)


__all__ = [
    "ArchiveTooLargeError",
    "ExtractedBundleTooLargeError",
    "InvalidPluginBundleError",
    "InvalidPluginPathError",
    "PluginBundlePackError",
    "PluginBundleUnpackError",
    "pack_plugin_bundle_tar_gz",
    "unpack_plugin_bundle_tar_gz",
]
