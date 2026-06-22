"""Rust-derived tests for codex-exec-server/src/server/file_system_handler.rs."""

from __future__ import annotations

import asyncio
import base64

from pycodex.app_server.error_code import INVALID_REQUEST_ERROR_CODE
from pycodex.app_server_protocol.jsonrpc_lite import JSONRPCErrorError
from pycodex.exec_server import (
    CopyOptions,
    CreateDirectoryOptions,
    ExecServerRuntimePaths,
    FileMetadata,
    FileSystemHandler,
    FileSystemSandboxContext,
    FsCopyParams,
    FsCopyResponse,
    FsCreateDirectoryParams,
    FsCreateDirectoryResponse,
    FsGetMetadataParams,
    FsGetMetadataResponse,
    FsReadDirectoryEntry,
    FsReadDirectoryParams,
    FsReadDirectoryResponse,
    FsReadFileParams,
    FsReadFileResponse,
    FsRemoveParams,
    FsRemoveResponse,
    FsWriteFileParams,
    FsWriteFileResponse,
    LocalFileSystem,
    ReadDirectoryEntry,
    RemoveOptions,
)
from pycodex.protocol import NetworkSandboxPolicy, PermissionProfile
from pycodex.utils.absolute_path import AbsolutePathBuf


class RecordingLocalFileSystem(LocalFileSystem):
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def read_file(self, path, sandbox=None) -> bytes:
        self.calls.append(("read_file", (path, sandbox)))
        return b"recorded"

    async def write_file(self, path, contents, sandbox=None) -> None:
        self.calls.append(("write_file", (path, bytes(contents), sandbox)))

    async def create_directory(self, path, options: CreateDirectoryOptions, sandbox=None) -> None:
        self.calls.append(("create_directory", (path, options, sandbox)))

    async def get_metadata(self, path, sandbox=None) -> FileMetadata:
        self.calls.append(("get_metadata", (path, sandbox)))
        return FileMetadata(
            is_directory=False,
            is_file=True,
            is_symlink=False,
            created_at_ms=10,
            modified_at_ms=20,
        )

    async def read_directory(self, path, sandbox=None) -> list[ReadDirectoryEntry]:
        self.calls.append(("read_directory", (path, sandbox)))
        return [
            ReadDirectoryEntry(file_name="a.txt", is_directory=False, is_file=True),
            ReadDirectoryEntry(file_name="sub", is_directory=True, is_file=False),
        ]

    async def remove(self, path, options: RemoveOptions, sandbox=None) -> None:
        self.calls.append(("remove", (path, options, sandbox)))

    async def copy(self, source_path, destination_path, options: CopyOptions, sandbox=None) -> None:
        self.calls.append(("copy", (source_path, destination_path, options, sandbox)))


def _no_platform_sandbox_context(tmp_path, profile: PermissionProfile) -> FileSystemSandboxContext:
    return FileSystemSandboxContext.from_permission_profile_with_cwd(
        profile,
        AbsolutePathBuf.from_absolute_path(tmp_path),
    )


def test_no_platform_sandbox_policies_do_not_require_configured_sandbox_helper(tmp_path):
    # Rust: codex-exec-server/src/server/file_system_handler.rs
    # Test: no_platform_sandbox_policies_do_not_require_configured_sandbox_helper
    # Contract: danger-full-access/disabled and external sandbox profiles route
    # through the unsandboxed LocalFileSystem without requiring a configured
    # filesystem helper backend.
    runtime_paths = ExecServerRuntimePaths.new(tmp_path / "codex", None)
    handler = FileSystemHandler.new(runtime_paths)

    async def run():
        results = []
        for name, profile in [
            ("danger.txt", PermissionProfile.disabled()),
            ("external.txt", PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED)),
        ]:
            path = tmp_path / name
            sandbox = _no_platform_sandbox_context(tmp_path, profile)
            write = await handler.write_file(
                FsWriteFileParams(
                    path=str(path),
                    data_base64=base64.b64encode(b"ok").decode("ascii"),
                    sandbox=sandbox,
                )
            )
            read = await handler.read_file(FsReadFileParams(path=str(path), sandbox=sandbox))
            results.append((write, read))
        return results

    results = asyncio.run(run())

    for write, read in results:
        assert write == FsWriteFileResponse()
        assert read == FsReadFileResponse(data_base64=base64.b64encode(b"ok").decode("ascii"))


def test_file_system_handler_projects_read_write_metadata_and_directory():
    # Rust: FileSystemHandler read_file/write_file/get_metadata/read_directory
    # Contract: handler methods translate protocol params/responses and forward
    # sandbox context to the underlying LocalFileSystem.
    file_system = RecordingLocalFileSystem()
    handler = FileSystemHandler(file_system)
    sandbox = object()

    async def run():
        read = await handler.read_file(FsReadFileParams(path="/tmp/read", sandbox=sandbox))
        write = await handler.write_file(
            FsWriteFileParams(
                path="/tmp/write",
                data_base64=base64.b64encode(b"hello").decode("ascii"),
                sandbox=sandbox,
            )
        )
        metadata = await handler.get_metadata(FsGetMetadataParams(path="/tmp/meta", sandbox=sandbox))
        directory = await handler.read_directory(FsReadDirectoryParams(path="/tmp/dir", sandbox=sandbox))
        return read, write, metadata, directory

    read, write, metadata, directory = asyncio.run(run())

    assert read == FsReadFileResponse(data_base64=base64.b64encode(b"recorded").decode("ascii"))
    assert write == FsWriteFileResponse()
    assert metadata == FsGetMetadataResponse(
        is_directory=False,
        is_file=True,
        is_symlink=False,
        created_at_ms=10,
        modified_at_ms=20,
    )
    assert directory == FsReadDirectoryResponse(
        entries=[
            FsReadDirectoryEntry(file_name="a.txt", is_directory=False, is_file=True),
            FsReadDirectoryEntry(file_name="sub", is_directory=True, is_file=False),
        ]
    )
    assert file_system.calls == [
        ("read_file", ("/tmp/read", sandbox)),
        ("write_file", ("/tmp/write", b"hello", sandbox)),
        ("get_metadata", ("/tmp/meta", sandbox)),
        ("read_directory", ("/tmp/dir", sandbox)),
    ]


def test_file_system_handler_uses_rust_default_options_for_create_and_remove():
    # Rust: FileSystemHandler::create_directory and ::remove
    # Contract: omitted recursive/force options default to true before calling
    # the LocalFileSystem backend.
    file_system = RecordingLocalFileSystem()
    handler = FileSystemHandler(file_system)

    async def run():
        created = await handler.create_directory(FsCreateDirectoryParams(path="/tmp/new"))
        removed = await handler.remove(FsRemoveParams(path="/tmp/new"))
        return created, removed

    created, removed = asyncio.run(run())

    assert created == FsCreateDirectoryResponse()
    assert removed == FsRemoveResponse()
    assert file_system.calls == [
        ("create_directory", ("/tmp/new", CreateDirectoryOptions(recursive=True), None)),
        ("remove", ("/tmp/new", RemoveOptions(recursive=True, force=True), None)),
    ]


def test_file_system_handler_copy_forwards_recursive_option():
    # Rust: FileSystemHandler::copy
    # Contract: copy wraps params.recursive in CopyOptions and returns the empty
    # protocol response on success.
    file_system = RecordingLocalFileSystem()
    handler = FileSystemHandler(file_system)

    result = asyncio.run(
        handler.copy(
            FsCopyParams(
                source_path="/tmp/source",
                destination_path="/tmp/destination",
                recursive=True,
            )
        )
    )

    assert result == FsCopyResponse()
    assert file_system.calls == [
        ("copy", ("/tmp/source", "/tmp/destination", CopyOptions(recursive=True), None))
    ]


def test_file_system_handler_invalid_base64_maps_to_invalid_request():
    # Rust: FileSystemHandler::write_file
    # Contract: invalid dataBase64 is rejected before filesystem IO with the
    # fs/writeFile method name in the error message.
    handler = FileSystemHandler(RecordingLocalFileSystem())

    result = asyncio.run(handler.write_file(FsWriteFileParams(path="/tmp/file", data_base64="not base64!")))

    assert isinstance(result, JSONRPCErrorError)
    assert result.code == INVALID_REQUEST_ERROR_CODE
    assert result.message.startswith("fs/writeFile requires valid base64 dataBase64:")


def test_file_system_handler_maps_filesystem_errors():
    # Rust: file_system_handler.rs::map_fs_error
    # Contract: filesystem errors are converted to JSON-RPC errors through the
    # same not_found/invalid_request/internal_error mapping used by the helper.
    class FailingLocalFileSystem(RecordingLocalFileSystem):
        async def read_file(self, path, sandbox=None) -> bytes:
            raise FileNotFoundError(path)

        async def create_directory(self, path, options, sandbox=None) -> None:
            raise PermissionError(path)

        async def get_metadata(self, path, sandbox=None):
            raise OSError("boom")

    handler = FileSystemHandler(FailingLocalFileSystem())

    async def run():
        missing = await handler.read_file(FsReadFileParams(path="/missing"))
        denied = await handler.create_directory(FsCreateDirectoryParams(path="/denied"))
        internal = await handler.get_metadata(FsGetMetadataParams(path="/boom"))
        return missing, denied, internal

    missing, denied, internal = asyncio.run(run())

    assert missing.code == -32004
    assert denied.code == INVALID_REQUEST_ERROR_CODE
    assert internal.code == -32603
