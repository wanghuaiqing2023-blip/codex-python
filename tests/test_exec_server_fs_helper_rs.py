"""Rust-derived tests for codex-exec-server/src/fs_helper.rs."""

from __future__ import annotations

import asyncio
import base64
import io
import json

from pycodex.app_server.error_code import INTERNAL_ERROR_CODE, INVALID_REQUEST_ERROR_CODE
from pycodex.exec_server import (
    FS_CREATE_DIRECTORY_METHOD,
    FS_READ_DIRECTORY_METHOD,
    FS_READ_FILE_METHOD,
    FS_WRITE_FILE_METHOD,
    FsCreateDirectoryParams,
    FsHelperPayload,
    FsHelperRequest,
    FsHelperResponse,
    FsReadDirectoryParams,
    FsReadDirectoryResponse,
    FsReadFileParams,
    FsReadFileResponse,
    FsWriteFileParams,
    FsWriteFileResponse,
    JSONRPCErrorError,
    map_fs_error,
    run_direct_request,
    run_fs_helper_main,
    run_fs_helper_once,
)


def test_helper_requests_use_fs_method_names(tmp_path):
    # Rust: codex-exec-server/src/fs_helper.rs
    # Test: helper_requests_use_fs_method_names
    # Contract: serde-tagged helper requests use the protocol fs method string
    # as the "operation" discriminator.
    request = FsHelperRequest.write_file(
        FsWriteFileParams(path=str(tmp_path / "file"), data_base64="", sandbox=None)
    )

    assert request.to_mapping()["operation"] == FS_WRITE_FILE_METHOD
    assert request.to_mapping()["params"] == {
        "path": str(tmp_path / "file"),
        "dataBase64": "",
    }


def test_helper_payload_and_response_wire_shape_round_trip(tmp_path):
    # Rust: codex-exec-server/src/fs_helper.rs
    # Contract: FsHelperPayload is serde-tagged with operation/response, and
    # FsHelperResponse is serde-tagged with status/payload using camelCase.
    payload = FsHelperPayload.read_file(FsReadFileResponse(data_base64="YWJj"))
    response = FsHelperResponse.ok(payload)

    assert response.to_mapping() == {
        "status": "ok",
        "payload": {
            "operation": FS_READ_FILE_METHOD,
            "response": {"dataBase64": "YWJj"},
        },
    }
    assert FsHelperResponse.from_mapping(response.to_mapping()) == response

    request = FsHelperRequest.from_mapping(
        {
            "operation": FS_CREATE_DIRECTORY_METHOD,
            "params": {"path": str(tmp_path / "dir"), "recursive": False},
        }
    )
    assert request == FsHelperRequest.create_directory(
        FsCreateDirectoryParams(path=str(tmp_path / "dir"), recursive=False, sandbox=None)
    )


def test_helper_payload_expect_methods_reject_wrong_operation():
    # Rust: codex-exec-server/src/fs_helper.rs
    # Contract: expect_* returns the typed response for matching payloads and
    # internal JSON-RPC error text for mismatched helper responses.
    payload = FsHelperPayload.write_file(FsWriteFileResponse())

    assert isinstance(payload.expect_write_file(), FsWriteFileResponse)
    error = payload.expect_read_file()

    assert isinstance(error, JSONRPCErrorError)
    assert error.code == INTERNAL_ERROR_CODE
    assert error.message == (
        f"unexpected fs sandbox helper response: expected {FS_READ_FILE_METHOD}, got {FS_WRITE_FILE_METHOD}"
    )


def test_run_direct_request_reads_and_writes_base64(tmp_path):
    # Rust: codex-exec-server/src/fs_helper.rs::run_direct_request
    # Contract: direct read/write helper requests go through base64 dataBase64
    # and return the matching FsHelperPayload variant.
    target = tmp_path / "file.txt"
    encoded = base64.b64encode(b"hello").decode("ascii")

    write_payload = asyncio.run(
        run_direct_request(FsHelperRequest.write_file(FsWriteFileParams(str(target), encoded)))
    )
    assert isinstance(write_payload, FsHelperPayload)
    assert isinstance(write_payload.expect_write_file(), FsWriteFileResponse)
    assert target.read_bytes() == b"hello"

    read_payload = asyncio.run(run_direct_request(FsHelperRequest.read_file(FsReadFileParams(str(target)))))
    assert isinstance(read_payload, FsHelperPayload)
    read_response = read_payload.expect_read_file()
    assert isinstance(read_response, FsReadFileResponse)
    assert read_response.data_base64 == encoded


def test_run_direct_request_uses_rust_default_options(tmp_path):
    # Rust: codex-exec-server/src/fs_helper.rs::run_direct_request
    # Contract: createDirectory defaults recursive to true, and readDirectory
    # returns fileName/isDirectory/isFile entries.
    nested = tmp_path / "a" / "b"
    create_payload = asyncio.run(
        run_direct_request(FsHelperRequest.create_directory(FsCreateDirectoryParams(str(nested))))
    )
    assert isinstance(create_payload, FsHelperPayload)
    assert nested.is_dir()
    existing_payload = asyncio.run(
        run_direct_request(FsHelperRequest.create_directory(FsCreateDirectoryParams(str(nested))))
    )
    assert isinstance(existing_payload, FsHelperPayload)

    file_path = nested / "note.txt"
    file_path.write_text("x", encoding="utf-8")
    read_dir_payload = asyncio.run(
        run_direct_request(FsHelperRequest.read_directory(FsReadDirectoryParams(str(nested))))
    )
    assert isinstance(read_dir_payload, FsHelperPayload)
    read_dir_response = read_dir_payload.expect_read_directory()
    assert isinstance(read_dir_response, FsReadDirectoryResponse)
    assert read_dir_response.entries == [
        type(read_dir_response.entries[0])(file_name="note.txt", is_directory=False, is_file=True)
    ]


def test_run_direct_request_invalid_base64_maps_to_invalid_request(tmp_path):
    # Rust: codex-exec-server/src/fs_helper.rs::run_direct_request
    # Contract: writeFile invalid base64 maps to invalid_request with the fs
    # method name and dataBase64 field in the message.
    payload = asyncio.run(
        run_direct_request(FsHelperRequest.write_file(FsWriteFileParams(str(tmp_path / "file"), "%%%")))
    )

    assert isinstance(payload, JSONRPCErrorError)
    assert payload.code == INVALID_REQUEST_ERROR_CODE
    assert payload.message.startswith(f"{FS_WRITE_FILE_METHOD} requires valid base64 dataBase64:")


def test_map_fs_error_matches_fs_helper_error_kinds():
    # Rust: codex-exec-server/src/fs_helper.rs::map_fs_error
    # Contract: NotFound maps to -32004, invalid input and permission errors
    # map to invalid_request, and other errors map to internal_error.
    missing = map_fs_error(FileNotFoundError("missing"))
    invalid = map_fs_error(ValueError("bad"))
    internal = map_fs_error(RuntimeError("boom"))

    assert missing.code == -32004
    assert invalid.code == INVALID_REQUEST_ERROR_CODE
    assert internal.code == INTERNAL_ERROR_CODE


def test_run_fs_helper_once_wraps_payload_as_json_line(tmp_path):
    # Rust: codex-exec-server/src/fs_helper_main.rs::run_main
    # Contract: the helper reads one complete JSON FsHelperRequest from stdin,
    # runs run_direct_request, wraps Ok payloads as FsHelperResponse::Ok, and
    # writes compact JSON followed by a newline.
    target = tmp_path / "entrypoint.txt"
    encoded = base64.b64encode(b"entrypoint").decode("ascii")
    request = FsHelperRequest.write_file(FsWriteFileParams(str(target), encoded))

    output = asyncio.run(run_fs_helper_once(json.dumps(request.to_mapping()).encode("utf-8")))

    assert output.endswith(b"\n")
    assert json.loads(output) == {
        "status": "ok",
        "payload": {
            "operation": FS_WRITE_FILE_METHOD,
            "response": {},
        },
    }
    assert target.read_bytes() == b"entrypoint"


def test_run_fs_helper_once_wraps_direct_request_errors(tmp_path):
    # Rust: codex-exec-server/src/fs_helper_main.rs::run_main
    # Contract: run_direct_request errors are serialized as
    # FsHelperResponse::Error instead of failing the helper process.
    request = FsHelperRequest.write_file(FsWriteFileParams(str(tmp_path / "file"), "%%%"))

    output = asyncio.run(run_fs_helper_once(json.dumps(request.to_mapping()).encode("utf-8")))
    response = FsHelperResponse.from_mapping(json.loads(output))

    assert response.status == "error"
    assert isinstance(response.payload, JSONRPCErrorError)
    assert response.payload.code == INVALID_REQUEST_ERROR_CODE
    assert response.payload.message.startswith(f"{FS_WRITE_FILE_METHOD} requires valid base64 dataBase64:")


def test_run_fs_helper_main_reports_invalid_input_to_stderr():
    # Rust: codex-exec-server/src/fs_helper_main.rs::main
    # Contract: malformed helper input prints the Rust error prefix and exits
    # with code 1.
    stdout = io.BytesIO()
    stderr = io.StringIO()

    try:
        run_fs_helper_main(io.BytesIO(b"{"), stdout, stderr)
    except SystemExit as exc:
        exit_code = exc.code
    else:  # pragma: no cover - mirrors process::exit in Rust.
        raise AssertionError("run_fs_helper_main did not exit")

    assert exit_code == 1
    assert stdout.getvalue() == b""
    assert stderr.getvalue().startswith("fs sandbox helper failed:")
