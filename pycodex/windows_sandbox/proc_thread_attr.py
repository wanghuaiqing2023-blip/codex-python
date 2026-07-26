"""Win32 process/thread attribute list ownership.

Rust owner: ``codex-windows-sandbox::proc_thread_attr``.
"""

from __future__ import annotations

import ctypes
import os
from collections.abc import Sequence

from . import process as _process


PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x0002_0002
PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x0002_0016

if os.name == "nt":
    _process._kernel32.InitializeProcThreadAttributeList.argtypes = [
        _process.LPVOID,
        _process.DWORD,
        _process.DWORD,
        ctypes.POINTER(_process.SIZE_T),
    ]
    _process._kernel32.InitializeProcThreadAttributeList.restype = _process.BOOL
    _process._kernel32.UpdateProcThreadAttribute.argtypes = [
        _process.LPVOID,
        _process.DWORD,
        _process.SIZE_T,
        _process.LPVOID,
        _process.SIZE_T,
        _process.LPVOID,
        ctypes.POINTER(_process.SIZE_T),
    ]
    _process._kernel32.UpdateProcThreadAttribute.restype = _process.BOOL
    _process._kernel32.DeleteProcThreadAttributeList.argtypes = [_process.LPVOID]


class ProcThreadAttributeList:
    """Own an initialized ``PROC_THREAD_ATTRIBUTE_LIST`` and its values."""

    def __init__(self, attr_count: int) -> None:
        _process._require_windows()
        if attr_count <= 0:
            raise ValueError("attr_count must be positive")
        size = _process.SIZE_T()
        _process._kernel32.InitializeProcThreadAttributeList(
            None,
            attr_count,
            0,
            ctypes.byref(size),
        )
        if not size.value:
            _process._raise_last_error(
                "InitializeProcThreadAttributeList size query failed"
            )
        self._buffer = ctypes.create_string_buffer(size.value)
        self._list = ctypes.cast(self._buffer, _process.LPVOID)
        if not _process._kernel32.InitializeProcThreadAttributeList(
            self._list,
            attr_count,
            0,
            ctypes.byref(size),
        ):
            _process._raise_last_error("InitializeProcThreadAttributeList failed")
        self._handle_list: object | None = None
        self._pseudoconsole: object | None = None
        self._closed = False

    def as_mut_ptr(self) -> object:
        if self._closed:
            raise RuntimeError("process/thread attribute list is closed")
        return self._list

    def set_pseudoconsole(self, hpc: int) -> None:
        value = _process.HANDLE(hpc)
        if not _process._kernel32.UpdateProcThreadAttribute(
            self.as_mut_ptr(),
            0,
            PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
            ctypes.cast(value, _process.LPVOID),
            ctypes.sizeof(_process.HANDLE),
            None,
            None,
        ):
            _process._raise_last_error(
                "UpdateProcThreadAttribute(pseudoconsole) failed"
            )
        self._pseudoconsole = value

    def set_handle_list(self, handles: Sequence[object]) -> None:
        values = tuple(handles)
        if not values:
            raise ValueError("handle list must not be empty")
        handle_list = (_process.HANDLE * len(values))(*values)
        if not _process._kernel32.UpdateProcThreadAttribute(
            self.as_mut_ptr(),
            0,
            PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
            ctypes.cast(handle_list, _process.LPVOID),
            ctypes.sizeof(handle_list),
            None,
            None,
        ):
            _process._raise_last_error(
                "UpdateProcThreadAttribute(handle list) failed"
            )
        self._handle_list = handle_list

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _process._kernel32.DeleteProcThreadAttributeList(self._list)
        self._handle_list = None
        self._pseudoconsole = None

    def __enter__(self) -> "ProcThreadAttributeList":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except BaseException:
            pass


__all__ = [
    "PROC_THREAD_ATTRIBUTE_HANDLE_LIST",
    "PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE",
    "ProcThreadAttributeList",
]
