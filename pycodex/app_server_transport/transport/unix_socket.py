from __future__ import annotations

import asyncio
import errno
import os
from pathlib import Path
from typing import Any

from pycodex.uds import UnixListener
from pycodex.uds import UnixStream
from pycodex.uds import is_stale_socket_path
from pycodex.uds import prepare_private_socket_directory


class AppServerStartupLock:
    def __init__(self, file: Any) -> None:
        self._file = file
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        _unlock_file(self._file)
        self._file.close()
        self._closed = True

    def __enter__(self) -> "AppServerStartupLock":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except OSError:
            pass


async def prepare_control_socket_path(socket_path: str | os.PathLike[str]) -> None:
    path = Path(socket_path)
    if path.parent != path:
        await prepare_private_socket_directory(path.parent)

    try:
        stream = await UnixStream.connect(path)
    except FileNotFoundError:
        return
    except ConnectionRefusedError:
        pass
    except OSError:
        if not path.exists():
            return
        if os.name != "nt":
            raise
    else:
        stream.close()
        await stream.wait_closed()
        raise OSError(
            errno.EADDRINUSE,
            f"app-server control socket is already in use at {path}",
            path,
        )

    if not path.exists():
        return
    if not await is_stale_socket_path(path):
        raise FileExistsError(
            errno.EEXIST,
            f"app-server control socket path exists and is not a socket: {path}",
            path,
        )
    await asyncio.to_thread(path.unlink)


async def acquire_app_server_startup_lock(
    startup_lock_path: str | os.PathLike[str],
) -> AppServerStartupLock:
    path = Path(startup_lock_path)
    if path.parent != path:
        await prepare_private_socket_directory(path.parent)

    def acquire() -> AppServerStartupLock:
        file = path.open("a+b")
        try:
            _lock_file(file)
        except BaseException:
            file.close()
            raise
        return AppServerStartupLock(file)

    return await asyncio.to_thread(acquire)


async def start_control_socket_acceptor(
    socket_path: str | os.PathLike[str],
    transport_event_tx: Any,
    shutdown_token: Any,
) -> asyncio.Task[None]:
    path = Path(socket_path)
    await prepare_control_socket_path(path)
    listener = await UnixListener.bind(path)
    if os.name != "nt":
        await asyncio.to_thread(os.chmod, path, 0o600)
    return asyncio.create_task(
        _run_control_socket_acceptor(
            listener,
            path,
            transport_event_tx,
            shutdown_token,
        ),
        name="app-server-control-socket-acceptor",
    )


async def _run_control_socket_acceptor(
    listener: UnixListener,
    socket_path: Path,
    transport_event_tx: Any,
    shutdown_token: Any,
) -> None:
    try:
        while not _is_cancelled(shutdown_token):
            accept_task = asyncio.create_task(listener.accept())
            shutdown_task = asyncio.create_task(_wait_cancelled(shutdown_token))
            done, _ = await asyncio.wait(
                {accept_task, shutdown_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if shutdown_task in done:
                accept_task.cancel()
                break
            shutdown_task.cancel()
            try:
                stream = accept_task.result()
            except OSError as exc:
                if exc.errno in {
                    errno.ECONNABORTED,
                    errno.ECONNRESET,
                    errno.EINTR,
                }:
                    continue
                await asyncio.sleep(1)
                continue
            asyncio.create_task(
                _run_control_socket_connection(stream, transport_event_tx)
            )
    finally:
        listener.close()
        await listener.wait_closed()
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass


async def _run_control_socket_connection(
    stream: UnixStream,
    transport_event_tx: Any,
) -> None:
    from pycodex.app_server_transport.transport.websocket import (
        run_websocket_connection,
    )

    await run_websocket_connection(stream, stream, transport_event_tx)


def _lock_file(file: Any) -> None:
    if os.name == "nt":
        import msvcrt

        file.seek(0, os.SEEK_END)
        if file.tell() == 0:
            file.write(b"\0")
            file.flush()
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(file: Any) -> None:
    if os.name == "nt":
        import msvcrt

        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def _is_cancelled(token: Any) -> bool:
    value = getattr(token, "is_cancelled", None)
    if callable(value):
        return bool(value())
    return bool(getattr(token, "cancelled", False))


async def _wait_cancelled(token: Any) -> None:
    for name in ("cancelled", "wait"):
        method = getattr(token, name, None)
        if callable(method):
            result = method()
            if hasattr(result, "__await__"):
                await result
                return
    while not _is_cancelled(token):
        await asyncio.sleep(0.05)


__all__ = [
    "AppServerStartupLock",
    "acquire_app_server_startup_lock",
    "prepare_control_socket_path",
    "start_control_socket_acceptor",
]
