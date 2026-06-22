from __future__ import annotations

import asyncio
import os
import stat
import sys

import pytest

from pycodex import uds


def test_prepare_private_socket_directory_creates_directory(tmp_path):
    # Rust crate/module: codex-uds src/lib.rs. Rust test:
    # prepare_private_socket_directory_creates_directory.
    socket_dir = tmp_path / "app-server-control"

    asyncio.run(uds.prepare_private_socket_directory(socket_dir))

    assert socket_dir.is_dir()


@pytest.mark.skipif(sys.platform == "win32", reason="Rust permission normalization is Unix-only")
def test_prepare_private_socket_directory_sets_existing_permissions_to_owner_only(tmp_path):
    # Rust crate/module: codex-uds src/lib.rs. Rust test:
    # prepare_private_socket_directory_sets_existing_permissions_to_owner_only.
    for mode in (0o755, 0o600):
        socket_dir = tmp_path / f"app-server-control-{mode:o}"
        socket_dir.mkdir()
        os.chmod(socket_dir, mode)

        asyncio.run(uds.prepare_private_socket_directory(socket_dir))

        assert stat.S_IMODE(socket_dir.stat().st_mode) == 0o700


@pytest.mark.skipif(sys.platform == "win32", reason="Rust regular-file stale check is Unix-only")
def test_regular_file_path_is_not_stale_socket_path(tmp_path):
    # Rust crate/module: codex-uds src/lib.rs. Rust test:
    # regular_file_path_is_not_stale_socket_path.
    regular_file = tmp_path / "not-a-socket"
    regular_file.write_bytes(b"not a socket")

    assert asyncio.run(uds.is_stale_socket_path(regular_file)) is False


@pytest.mark.skipif(not uds.unix_socket_support_available(), reason="asyncio Unix sockets unavailable")
def test_bound_listener_path_is_stale_socket_path(tmp_path):
    # Rust crate/module: codex-uds src/lib.rs. Rust test:
    # bound_listener_path_is_stale_socket_path.
    socket_path = tmp_path / "socket"

    async def run() -> None:
        listener = await uds.UnixListener.bind(socket_path)
        try:
            assert await uds.is_stale_socket_path(socket_path) is True
        finally:
            listener.close()
            await listener.wait_closed()

    asyncio.run(run())


@pytest.mark.skipif(not uds.unix_socket_support_available(), reason="asyncio Unix sockets unavailable")
def test_stream_round_trips_data_between_listener_and_client(tmp_path):
    # Rust crate/module: codex-uds src/lib.rs. Rust test:
    # stream_round_trips_data_between_listener_and_client.
    socket_path = tmp_path / "socket"

    async def server_task(server_stream: uds.UnixStream) -> None:
        request = await server_stream.read_exactly(7)
        assert request == b"request"
        await server_stream.write_all(b"response")
        server_stream.close()
        await server_stream.wait_closed()

    async def client_task(client_stream: uds.UnixStream) -> None:
        await client_stream.write_all(b"request")
        response = await client_stream.read_exactly(8)
        assert response == b"response"

    asyncio.run(uds.run_connected_pair(socket_path, server_task, client_task))


def test_prepare_private_socket_directory_rejects_existing_file(tmp_path):
    # Rust crate/module: codex-uds src/lib.rs. Source contract: an existing
    # non-directory rendezvous path returns an AlreadyExists-style error.
    socket_dir = tmp_path / "app-server-control"
    socket_dir.write_text("not a directory")

    with pytest.raises(FileExistsError):
        asyncio.run(uds.prepare_private_socket_directory(socket_dir))


def test_windows_stale_socket_path_uses_existence(monkeypatch, tmp_path):
    # Rust crate/module: codex-uds src/lib.rs. Windows source contract:
    # uds_windows represents the rendezvous as a regular path, so existence is
    # the stale-path signal.
    socket_path = tmp_path / "socket"
    socket_path.write_text("rendezvous")
    monkeypatch.setattr(uds.sys, "platform", "win32")

    assert asyncio.run(uds.is_stale_socket_path(socket_path)) is True
    assert asyncio.run(uds.is_stale_socket_path(tmp_path / "missing")) is False
