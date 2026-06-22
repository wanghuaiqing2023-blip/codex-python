from __future__ import annotations

import asyncio
import base64
import errno
from pathlib import Path

import pytest

from pycodex.exec_server import (
    CopyOptions,
    CreateDirectoryOptions,
    ExecServerError,
    ExecServerTransportParams,
    FileMetadata,
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
    LazyRemoteExecServerClient,
    ReadDirectoryEntry,
    RemoteFileSystemBoundary,
    RemoveOptions,
    map_remote_error,
    remote_sandbox_context,
)
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FileSystemSpecialPath,
    NetworkSandboxPolicy,
    PermissionProfile,
)
from pycodex.utils.absolute_path import AbsolutePathBuf


def _transport() -> ExecServerTransportParams:
    return ExecServerTransportParams.from_websocket_url("ws://127.0.0.1:9999")


def _remote_fs(client: object) -> RemoteFileSystemBoundary:
    return RemoteFileSystemBoundary.new(LazyRemoteExecServerClient(_transport(), client=client))


def _server_error(code: int, message: str) -> ExecServerError:
    error = ExecServerError(message, "server")
    error.code = code
    return error


def _restricted_policy(entries: list[FileSystemSandboxEntry]) -> FileSystemSandboxPolicy:
    return FileSystemSandboxPolicy.restricted(entries)


def _path_entry(path: AbsolutePathBuf, access: FileSystemAccessMode) -> FileSystemSandboxEntry:
    return FileSystemSandboxEntry(FileSystemPath.explicit_path(path.as_path()), access)


def _special_entry(value: FileSystemSpecialPath, access: FileSystemAccessMode) -> FileSystemSandboxEntry:
    return FileSystemSandboxEntry(FileSystemPath.special(value), access)


def _sandbox_context(policy: FileSystemSandboxPolicy, cwd: AbsolutePathBuf) -> FileSystemSandboxContext:
    return FileSystemSandboxContext.from_permission_profile_with_cwd(
        PermissionProfile.from_runtime_permissions(policy, NetworkSandboxPolicy.RESTRICTED),
        cwd,
    )


def test_remote_sandbox_context_drops_unused_cwd(tmp_path: Path) -> None:
    # Rust crate/module/test:
    # codex-exec-server/src/remote_file_system.rs::tests::remote_sandbox_context_drops_unused_cwd.
    # Contract: cwd is not sent to the remote side when permissions do not
    # contain cwd-dependent project-root entries.
    remote_root = AbsolutePathBuf.from_absolute_path(tmp_path / "remote-root")
    cwd = AbsolutePathBuf.from_absolute_path(tmp_path / "host-checkout")
    policy = _restricted_policy([_path_entry(remote_root, FileSystemAccessMode.READ)])
    sandbox = _sandbox_context(policy, cwd)

    remote = remote_sandbox_context(sandbox)

    assert remote is not None
    assert remote.cwd is None


def test_remote_sandbox_context_preserves_required_cwd(tmp_path: Path) -> None:
    # Rust test:
    # codex-exec-server/src/remote_file_system.rs::tests::remote_sandbox_context_preserves_required_cwd.
    # Contract: cwd is preserved when project-root permissions require the
    # remote side to resolve dynamic paths.
    cwd = AbsolutePathBuf.from_absolute_path(tmp_path / "host-checkout")
    policy = _restricted_policy(
        [_special_entry(FileSystemSpecialPath.project_roots(), FileSystemAccessMode.WRITE)]
    )
    sandbox = _sandbox_context(policy, cwd)

    remote = remote_sandbox_context(sandbox)

    assert remote is not None
    assert remote.cwd == cwd


def test_transport_errors_map_to_broken_pipe() -> None:
    # Rust test:
    # codex-exec-server/src/remote_file_system.rs::tests::transport_errors_map_to_broken_pipe.
    errors = [
        ExecServerError("closed", "closed"),
        ExecServerError("exec-server transport disconnected", "disconnected"),
    ]

    mapped = [map_remote_error(error) for error in errors]

    assert [type(error) for error in mapped] == [BrokenPipeError, BrokenPipeError]
    assert [str(error) for error in mapped] == [
        "exec-server transport closed",
        "exec-server transport closed",
    ]


def test_remote_errors_map_by_jsonrpc_code() -> None:
    # Rust module contract: server -32004 maps to NotFound, -32600 maps to
    # InvalidInput, and other server errors become generic IO errors.
    missing = map_remote_error(_server_error(-32004, "missing"))
    invalid = map_remote_error(_server_error(-32600, "bad params"))
    other = map_remote_error(_server_error(-32099, "boom"))

    assert isinstance(missing, FileNotFoundError)
    assert str(missing) == "missing"
    assert invalid.errno == errno.EINVAL
    assert "bad params" in str(invalid)
    assert isinstance(other, OSError)
    assert str(other) == "boom"


def test_remote_file_system_projects_rpc_params_and_responses(tmp_path: Path) -> None:
    # Rust module contract: RemoteFileSystem implements ExecutorFileSystem by
    # converting filesystem calls to fs/* protocol params and projecting typed
    # responses back to filesystem return values.
    client = RecordingFsClient()
    fs = _remote_fs(client)
    source = tmp_path / "source.txt"
    target = tmp_path / "target.txt"
    sandbox = _sandbox_context(
        _restricted_policy(
            [_special_entry(FileSystemSpecialPath.project_roots(), FileSystemAccessMode.WRITE)]
        ),
        AbsolutePathBuf.from_absolute_path(tmp_path),
    )

    assert asyncio.run(fs.read_file(source, sandbox)) == b"hello"
    asyncio.run(fs.write_file(target, b"write", sandbox))
    asyncio.run(fs.create_directory(tmp_path / "dir", CreateDirectoryOptions(recursive=False), sandbox))
    metadata = asyncio.run(fs.get_metadata(source, sandbox))
    entries = asyncio.run(fs.read_directory(tmp_path, sandbox))
    asyncio.run(fs.remove(target, RemoveOptions(recursive=True, force=False), sandbox))
    asyncio.run(fs.copy(source, target, CopyOptions(recursive=True), sandbox))

    assert metadata == FileMetadata(
        is_directory=False,
        is_file=True,
        is_symlink=False,
        created_at_ms=10,
        modified_at_ms=20,
    )
    assert entries == [ReadDirectoryEntry("child.txt", False, True)]
    assert [type(call).__name__ for call in client.calls] == [
        "FsReadFileParams",
        "FsWriteFileParams",
        "FsCreateDirectoryParams",
        "FsGetMetadataParams",
        "FsReadDirectoryParams",
        "FsRemoveParams",
        "FsCopyParams",
    ]
    write = client.calls[1]
    assert isinstance(write, FsWriteFileParams)
    assert write.data_base64 == base64.b64encode(b"write").decode("ascii")
    mkdir = client.calls[2]
    assert isinstance(mkdir, FsCreateDirectoryParams)
    assert mkdir.recursive is False
    remove = client.calls[5]
    assert isinstance(remove, FsRemoveParams)
    assert remove.recursive is True
    assert remove.force is False
    copy = client.calls[6]
    assert isinstance(copy, FsCopyParams)
    assert copy.source_path == str(source)
    assert copy.destination_path == str(target)
    assert copy.recursive is True
    assert all(call.sandbox is not None and call.sandbox.cwd == sandbox.cwd for call in client.calls)


def test_read_file_rejects_invalid_remote_base64(tmp_path: Path) -> None:
    # Rust module contract: invalid dataBase64 in fs/readFile responses maps to
    # InvalidData with a method/field specific message.
    fs = _remote_fs(InvalidBase64Client())

    with pytest.raises(OSError, match="remote fs/readFile returned invalid base64 dataBase64"):
        asyncio.run(fs.read_file(tmp_path / "file.txt"))


class RecordingFsClient:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def fs_read_file(self, params: FsReadFileParams) -> FsReadFileResponse:
        self.calls.append(params)
        return FsReadFileResponse(base64.b64encode(b"hello").decode("ascii"))

    async def fs_write_file(self, params: FsWriteFileParams) -> FsWriteFileResponse:
        self.calls.append(params)
        return FsWriteFileResponse()

    async def fs_create_directory(self, params: FsCreateDirectoryParams) -> FsCreateDirectoryResponse:
        self.calls.append(params)
        return FsCreateDirectoryResponse()

    async def fs_get_metadata(self, params: FsGetMetadataParams) -> FsGetMetadataResponse:
        self.calls.append(params)
        return FsGetMetadataResponse(False, True, False, 10, 20)

    async def fs_read_directory(self, params: FsReadDirectoryParams) -> FsReadDirectoryResponse:
        self.calls.append(params)
        return FsReadDirectoryResponse([FsReadDirectoryEntry("child.txt", False, True)])

    async def fs_remove(self, params: FsRemoveParams) -> FsRemoveResponse:
        self.calls.append(params)
        return FsRemoveResponse()

    async def fs_copy(self, params: FsCopyParams) -> FsCopyResponse:
        self.calls.append(params)
        return FsCopyResponse()


class InvalidBase64Client:
    async def fs_read_file(self, params: FsReadFileParams) -> FsReadFileResponse:
        return FsReadFileResponse("@@@")
