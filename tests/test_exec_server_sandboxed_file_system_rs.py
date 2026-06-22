"""Rust-derived tests for codex-exec-server/src/sandboxed_file_system.rs."""

from __future__ import annotations

import asyncio
import base64

import pytest

from pycodex.exec_server import (
    CopyOptions,
    CreateDirectoryOptions,
    ExecServerRuntimePaths,
    FS_COPY_METHOD,
    FS_CREATE_DIRECTORY_METHOD,
    FS_GET_METADATA_METHOD,
    FS_READ_DIRECTORY_METHOD,
    FS_READ_FILE_METHOD,
    FS_REMOVE_METHOD,
    FS_WRITE_FILE_METHOD,
    FileMetadata,
    FsCopyResponse,
    FsCreateDirectoryResponse,
    FsGetMetadataResponse,
    FsHelperPayload,
    FsReadDirectoryEntry,
    FsReadDirectoryResponse,
    FsReadFileResponse,
    FsRemoveResponse,
    FsWriteFileResponse,
    LocalFileSystem,
    ReadDirectoryEntry,
    RemoveOptions,
    SandboxedFileSystem,
    internal_error,
    invalid_request,
    map_sandbox_error,
    not_found,
)


class Sandbox:
    def should_run_in_sandbox(self) -> bool:
        return True


class NonPlatformSandbox:
    def should_run_in_sandbox(self) -> bool:
        return False


class RecordingRunner:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def run(self, sandbox, request):
        self.calls.append((sandbox, request))
        return self.responses.pop(0)


def test_sandboxed_file_system_rejects_missing_or_non_platform_sandbox(tmp_path):
    # Rust: codex-exec-server/src/sandboxed_file_system.rs::require_platform_sandbox
    # Contract: sandboxed filesystem operations require a context that should
    # run in the platform sandbox.
    fs = SandboxedFileSystem(RecordingRunner())

    with pytest.raises(ValueError, match="ReadOnly or WorkspaceWrite sandbox policy"):
        asyncio.run(fs.read_file(tmp_path / "file", None))
    with pytest.raises(ValueError, match="ReadOnly or WorkspaceWrite sandbox policy"):
        asyncio.run(fs.read_file(tmp_path / "file", NonPlatformSandbox()))


def test_sandboxed_file_system_read_file_decodes_helper_base64(tmp_path):
    # Rust: sandboxed_file_system.rs::SandboxedFileSystem::read_file
    # Contract: readFile sends a helper request without nested sandbox context
    # and decodes the returned dataBase64.
    sandbox = Sandbox()
    runner = RecordingRunner(FsHelperPayload.read_file(FsReadFileResponse("aGVsbG8=")))
    fs = SandboxedFileSystem(runner)

    data = asyncio.run(fs.read_file(tmp_path / "file.txt", sandbox))

    assert data == b"hello"
    called_sandbox, request = runner.calls[0]
    assert called_sandbox is sandbox
    assert request.operation == FS_READ_FILE_METHOD
    assert request.params.path == str(tmp_path / "file.txt")
    assert request.params.sandbox is None


def test_sandboxed_file_system_write_create_remove_and_copy_requests(tmp_path):
    # Rust: sandboxed_file_system.rs ExecutorFileSystem impl
    # Contract: mutating operations encode options into FsHelperRequest params
    # and map matching helper payloads to unit results.
    sandbox = Sandbox()
    runner = RecordingRunner(
        FsHelperPayload.write_file(FsWriteFileResponse()),
        FsHelperPayload.create_directory(FsCreateDirectoryResponse()),
        FsHelperPayload.remove(FsRemoveResponse()),
        FsHelperPayload.copy(FsCopyResponse()),
    )
    fs = SandboxedFileSystem(runner)

    asyncio.run(fs.write_file(tmp_path / "file.txt", b"hello", sandbox))
    asyncio.run(fs.create_directory(tmp_path / "dir", CreateDirectoryOptions(recursive=False), sandbox))
    asyncio.run(fs.remove(tmp_path / "dir", RemoveOptions(recursive=True, force=False), sandbox))
    asyncio.run(fs.copy(tmp_path / "src", tmp_path / "dst", CopyOptions(recursive=True), sandbox))

    requests = [request for _, request in runner.calls]
    assert [request.operation for request in requests] == [
        FS_WRITE_FILE_METHOD,
        FS_CREATE_DIRECTORY_METHOD,
        FS_REMOVE_METHOD,
        FS_COPY_METHOD,
    ]
    assert requests[0].params.data_base64 == base64.b64encode(b"hello").decode("ascii")
    assert requests[0].params.sandbox is None
    assert requests[1].params.recursive is False
    assert requests[2].params.recursive is True
    assert requests[2].params.force is False
    assert requests[3].params.source_path == str(tmp_path / "src")
    assert requests[3].params.destination_path == str(tmp_path / "dst")
    assert requests[3].params.recursive is True


def test_sandboxed_file_system_metadata_and_directory_projection(tmp_path):
    # Rust: sandboxed_file_system.rs::{get_metadata,read_directory}
    # Contract: helper protocol metadata and directory entries are projected
    # into filesystem-domain FileMetadata and ReadDirectoryEntry values.
    sandbox = Sandbox()
    runner = RecordingRunner(
        FsHelperPayload.get_metadata(
            FsGetMetadataResponse(
                is_directory=False,
                is_file=True,
                is_symlink=False,
                created_at_ms=1,
                modified_at_ms=2,
            )
        ),
        FsHelperPayload.read_directory(
            FsReadDirectoryResponse(
                [
                    FsReadDirectoryEntry("file.txt", is_directory=False, is_file=True),
                    FsReadDirectoryEntry("dir", is_directory=True, is_file=False),
                ]
            )
        ),
    )
    fs = SandboxedFileSystem(runner)

    metadata = asyncio.run(fs.get_metadata(tmp_path / "file.txt", sandbox))
    entries = asyncio.run(fs.read_directory(tmp_path, sandbox))

    assert metadata == FileMetadata(
        is_directory=False,
        is_file=True,
        is_symlink=False,
        created_at_ms=1,
        modified_at_ms=2,
    )
    assert entries == [
        ReadDirectoryEntry("file.txt", is_directory=False, is_file=True),
        ReadDirectoryEntry("dir", is_directory=True, is_file=False),
    ]
    assert [request.operation for _, request in runner.calls] == [
        FS_GET_METADATA_METHOD,
        FS_READ_DIRECTORY_METHOD,
    ]


def test_sandboxed_file_system_maps_helper_errors_and_unexpected_payloads(tmp_path):
    # Rust: sandboxed_file_system.rs::map_sandbox_error plus payload expect_*
    # Contract: helper JSON-RPC errors and unexpected payload variants are
    # converted into filesystem errors.
    sandbox = Sandbox()
    missing = SandboxedFileSystem(RecordingRunner(not_found("missing")))
    invalid = SandboxedFileSystem(RecordingRunner(invalid_request("bad request")))
    unexpected = SandboxedFileSystem(RecordingRunner(FsHelperPayload.write_file(FsWriteFileResponse())))

    with pytest.raises(FileNotFoundError, match="missing"):
        asyncio.run(missing.read_file(tmp_path / "missing", sandbox))
    with pytest.raises(ValueError, match="bad request"):
        asyncio.run(invalid.read_file(tmp_path / "bad", sandbox))
    with pytest.raises(OSError, match="unexpected fs sandbox helper response"):
        asyncio.run(unexpected.read_file(tmp_path / "wrong", sandbox))


def test_sandboxed_file_system_invalid_read_base64_is_invalid_data(tmp_path):
    # Rust: sandboxed_file_system.rs::SandboxedFileSystem::read_file
    # Contract: invalid helper dataBase64 becomes an invalid-data filesystem
    # error with the Rust method/field message prefix.
    sandbox = Sandbox()
    fs = SandboxedFileSystem(RecordingRunner(FsHelperPayload.read_file(FsReadFileResponse("%%%"))))

    with pytest.raises(OSError, match="fs/readFile returned invalid base64 dataBase64:"):
        asyncio.run(fs.read_file(tmp_path / "file", sandbox))


def test_map_sandbox_error_matches_rust_jsonrpc_codes():
    # Rust: sandboxed_file_system.rs::map_sandbox_error
    # Contract: not_found maps to NotFound, invalid_request maps to
    # InvalidInput, and other helper errors map to a generic IO error.
    assert isinstance(map_sandbox_error(not_found("missing")), FileNotFoundError)
    assert isinstance(map_sandbox_error(invalid_request("bad")), ValueError)
    assert type(map_sandbox_error(internal_error("boom"))) is OSError


def test_local_file_system_with_runtime_paths_configures_sandboxed_backend(tmp_path):
    # Rust: local_file_system.rs::LocalFileSystem::new collaborates with
    # sandboxed_file_system.rs::SandboxedFileSystem::new.
    # Contract: configured runtime paths install a sandboxed backend instead
    # of rejecting platform sandbox contexts at dispatch time.
    runtime_paths = ExecServerRuntimePaths.new(tmp_path / "codex.exe")

    fs = LocalFileSystem.with_runtime_paths(runtime_paths)

    assert isinstance(fs.sandboxed, SandboxedFileSystem)
