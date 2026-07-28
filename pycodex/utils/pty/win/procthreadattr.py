"""Windows process attribute lists from procthreadattr.rs."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016


def _kernel32() -> ctypes.WinDLL:
    if os.name != "nt":
        raise OSError("Windows process attributes are only available on Windows")
    return ctypes.WinDLL("kernel32", use_last_error=True)


class ProcThreadAttributeList:
    def __init__(self, buffer: ctypes.Array[ctypes.c_char]) -> None:
        self._buffer = buffer
        self._deleted = False

    @classmethod
    def with_capacity(cls, num_attributes: int) -> "ProcThreadAttributeList":
        kernel32 = _kernel32()
        size = ctypes.c_size_t()
        kernel32.InitializeProcThreadAttributeList(None, num_attributes, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not kernel32.InitializeProcThreadAttributeList(buffer, num_attributes, 0, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        return cls(buffer)

    def as_mut_ptr(self) -> ctypes.c_void_p:
        return ctypes.cast(self._buffer, ctypes.c_void_p)

    def set_pty(self, con: int) -> None:
        kernel32 = _kernel32()
        if not kernel32.UpdateProcThreadAttribute(
            self.as_mut_ptr(),
            0,
            PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
            ctypes.c_void_p(int(con)),
            ctypes.sizeof(wintypes.HANDLE),
            None,
            None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self._deleted or os.name != "nt":
            return
        _kernel32().DeleteProcThreadAttributeList(self.as_mut_ptr())
        self._deleted = True

    def __enter__(self) -> "ProcThreadAttributeList":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


__all__ = ["ProcThreadAttributeList"]
