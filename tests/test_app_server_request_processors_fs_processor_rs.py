"""Rust parity tests for ``codex-app-server/src/request_processors/fs_processor.rs``."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
import pytest

from pycodex.app_server.fs_watch import FsWatchManager
from pycodex.app_server.request_processors_fs_processor import (
    FsRequestProcessor,
    FsRequestProcessorError,
    map_fs_error,
)
from pycodex.app_server_protocol import (
    FsCopyParams,
    FsCreateDirectoryParams,
    FsReadFileParams,
    FsRemoveParams,
    FsWatchParams,
    FsWriteFileParams,
)


class FakeFileSystem:
    def __init__(self) -> None:
        self.calls = []

    def read_file(self, path, sandbox):
        self.calls.append(("read_file", path, sandbox))
        return b"hello"

    def write_file(self, path, data, sandbox):
        self.calls.append(("write_file", path, data, sandbox))

    def create_directory(self, path, options, sandbox):
        self.calls.append(("create_directory", path, options, sandbox))

    def get_metadata(self, path, sandbox):
        self.calls.append(("get_metadata", path, sandbox))
        return {
            "is_directory": False,
            "is_file": True,
            "is_symlink": False,
            "created_at_ms": 10,
            "modified_at_ms": 20,
        }

    def read_directory(self, path, sandbox):
        self.calls.append(("read_directory", path, sandbox))
        return [
            {"file_name": "src", "is_directory": True, "is_file": False},
            {"file_name": "README.md", "is_directory": False, "is_file": True},
        ]

    def remove(self, path, options, sandbox):
        self.calls.append(("remove", path, options, sandbox))

    def copy(self, source, destination, options, sandbox):
        self.calls.append(("copy", source, destination, options, sandbox))


class Environment:
    def __init__(self, filesystem):
        self.filesystem = filesystem

    def get_filesystem(self):
        return self.filesystem


class EnvironmentManager:
    def __init__(self, filesystem=None):
        self.environment = None if filesystem is None else Environment(filesystem)

    def try_local_environment(self):
        return self.environment


def make_processor(filesystem=None):
    filesystem = filesystem or FakeFileSystem()
    return FsRequestProcessor.new(EnvironmentManager(filesystem), FsWatchManager.new(outgoing=None)), filesystem


def assert_error(excinfo, message: str, code: int) -> None:
    assert excinfo.value.error.message == message
    assert excinfo.value.error.code == code


def test_file_system_requires_local_environment_like_rust() -> None:
    processor = FsRequestProcessor.new(EnvironmentManager(None), FsWatchManager.new(outgoing=None))

    with pytest.raises(FsRequestProcessorError) as excinfo:
        processor.file_system()

    assert_error(excinfo, "local filesystem is not configured", -32603)


def test_read_file_returns_base64_data_and_passes_no_sandbox() -> None:
    processor, filesystem = make_processor()

    response = asyncio.run(processor.read_file(FsReadFileParams(path="C:/repo/file.txt")))

    assert response.data_base64 == base64.b64encode(b"hello").decode("ascii")
    assert filesystem.calls == [("read_file", Path("C:/repo/file.txt"), None)]


def test_write_file_decodes_base64_and_rejects_invalid_base64() -> None:
    processor, filesystem = make_processor()

    response = asyncio.run(
        processor.write_file(
            FsWriteFileParams(path="C:/repo/file.txt", data_base64=base64.b64encode(b"data").decode("ascii"))
        )
    )

    assert response.to_mapping() == {}
    assert filesystem.calls == [("write_file", Path("C:/repo/file.txt"), b"data", None)]

    with pytest.raises(FsRequestProcessorError) as excinfo:
        asyncio.run(processor.write_file(FsWriteFileParams(path="C:/repo/file.txt", data_base64="not-base64!")))

    assert "fs/writeFile requires valid base64 dataBase64:" in excinfo.value.error.message
    assert excinfo.value.error.code == -32600


def test_create_remove_and_copy_use_rust_default_options() -> None:
    processor, filesystem = make_processor()

    asyncio.run(processor.create_directory(FsCreateDirectoryParams(path="C:/repo/new")))
    asyncio.run(processor.remove(FsRemoveParams(path="C:/repo/old")))
    asyncio.run(
        processor.copy(
            FsCopyParams(source_path="C:/repo/a", destination_path="C:/repo/b", recursive=True)
        )
    )

    assert filesystem.calls == [
        ("create_directory", Path("C:/repo/new"), {"recursive": True}, None),
        ("remove", Path("C:/repo/old"), {"recursive": True, "force": True}, None),
        ("copy", Path("C:/repo/a"), Path("C:/repo/b"), {"recursive": True}, None),
    ]


def test_metadata_and_directory_entries_project_protocol_shapes() -> None:
    processor, _filesystem = make_processor()

    metadata = asyncio.run(processor.get_metadata({"path": "C:/repo/file.txt"}))
    directory = asyncio.run(processor.read_directory({"path": "C:/repo"}))

    assert metadata.to_mapping() == {
        "is_directory": False,
        "is_file": True,
        "is_symlink": False,
        "created_at_ms": 10,
        "modified_at_ms": 20,
    }
    assert [entry.file_name for entry in directory.entries] == ["src", "README.md"]
    assert directory.entries[0].is_directory is True
    assert directory.entries[1].is_file is True


def test_fs_errors_map_invalid_input_to_invalid_request_otherwise_internal() -> None:
    assert map_fs_error(ValueError("bad path")).code == -32600
    assert map_fs_error(OSError("disk gone")).code == -32603


def test_watch_unwatch_and_connection_closed_delegate_after_filesystem_check() -> None:
    processor, _filesystem = make_processor()

    response = asyncio.run(processor.watch(7, FsWatchParams(watch_id="w1", path="C:/repo")))
    assert response.path == Path("C:/repo")
    assert len(processor.fs_watch_manager.active_watch_keys()) == 1

    asyncio.run(processor.unwatch(7, {"watchId": "w1"}))
    assert len(processor.fs_watch_manager.active_watch_keys()) == 0

    asyncio.run(processor.watch(7, FsWatchParams(watch_id="w2", path="C:/repo")))
    asyncio.run(processor.connection_closed(7))
    assert len(processor.fs_watch_manager.active_watch_keys()) == 0
