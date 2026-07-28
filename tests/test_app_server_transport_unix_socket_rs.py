from __future__ import annotations

import errno
from pathlib import Path

import pytest

from pycodex.app_server_transport.transport.unix_socket import (
    acquire_app_server_startup_lock,
)
from pycodex.app_server_transport.transport.unix_socket import (
    prepare_control_socket_path,
)


@pytest.mark.asyncio
async def test_prepare_control_socket_path_creates_private_parent(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "private" / "control.sock"

    await prepare_control_socket_path(socket_path)

    assert socket_path.parent.is_dir()


@pytest.mark.asyncio
async def test_startup_lock_keeps_the_lock_file_open(tmp_path: Path) -> None:
    lock_path = tmp_path / "private" / "startup.lock"

    lock = await acquire_app_server_startup_lock(lock_path)
    try:
        assert lock_path.is_file()
        assert not lock._file.closed
    finally:
        lock.close()


@pytest.mark.asyncio
async def test_existing_non_socket_path_is_rejected_on_unix(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "control.sock"
    socket_path.write_text("not a socket", encoding="utf-8")

    if __import__("os").name == "nt":
        await prepare_control_socket_path(socket_path)
        assert not socket_path.exists()
    else:
        with pytest.raises(FileExistsError) as exc_info:
            await prepare_control_socket_path(socket_path)
        assert exc_info.value.errno == errno.EEXIST
