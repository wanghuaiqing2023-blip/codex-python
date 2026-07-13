"""UAC setup-helper orchestration.

Rust owner: ``codex-windows-sandbox::setup::run_setup_exe`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

from .setup import ElevationPayload, sandbox_dir
from .setup_error import (
    SetupErrorCode,
    SetupFailure,
    clear_setup_error_report,
    read_setup_error_report,
)


if os.name == "nt":
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SW_HIDE = 0
    INFINITE = 0xFFFFFFFF
    ERROR_CANCELLED = 1223
    SECURITY_BUILTIN_DOMAIN_RID = 0x20
    DOMAIN_ALIAS_RID_ADMINS = 0x220

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", ctypes.c_ulong),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    _shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    _shell32.ShellExecuteExW.restype = wintypes.BOOL
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _advapi32.CheckTokenMembership.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL)]
    _advapi32.CheckTokenMembership.restype = wintypes.BOOL
    _advapi32.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    _advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def is_elevated() -> bool:
    _require_windows()
    sid = ctypes.c_void_p()
    if not _advapi32.ConvertStringSidToSidW("S-1-5-32-544", ctypes.byref(sid)):
        error = ctypes.get_last_error()
        raise SetupFailure(SetupErrorCode.ORCHESTRATOR_ELEVATION_CHECK_FAILED, f"resolve Administrators SID failed: {error}")
    try:
        member = wintypes.BOOL()
        if not _advapi32.CheckTokenMembership(None, sid, ctypes.byref(member)):
            error = ctypes.get_last_error()
            raise SetupFailure(SetupErrorCode.ORCHESTRATOR_ELEVATION_CHECK_FAILED, f"CheckTokenMembership failed: {error}")
        return bool(member.value)
    finally:
        _kernel32.LocalFree(sid)


def run_setup_helper(payload: ElevationPayload, *, elevate: bool) -> None:
    _require_windows()
    codex_home = payload.codex_home
    try:
        sandbox_dir(codex_home).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SetupFailure(
            SetupErrorCode.ORCHESTRATOR_SANDBOX_DIR_CREATE_FAILED,
            f"failed to create sandbox dir {sandbox_dir(codex_home)}: {exc}",
        ) from exc
    try:
        encoded = base64.b64encode(
            json.dumps(payload.to_mapping(), separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
    except (TypeError, ValueError) as exc:
        raise SetupFailure(SetupErrorCode.ORCHESTRATOR_PAYLOAD_SERIALIZE_FAILED, str(exc)) from exc
    cleared_report = True
    try:
        clear_setup_error_report(codex_home)
    except OSError:
        cleared_report = False
    exit_code = _run_helper_process(encoded, elevate=elevate)
    if exit_code != 0:
        _raise_helper_failure(codex_home, cleared_report, exit_code)
    try:
        clear_setup_error_report(codex_home)
    except OSError:
        pass


def _run_helper_process(encoded: str, *, elevate: bool) -> int:
    arguments = ["-m", "pycodex.windows_sandbox.setup_helper", encoded]
    if not elevate:
        completed = subprocess.run(
            [sys.executable, *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        return completed.returncode

    parameters = subprocess.list2cmdline(arguments)
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = sys.executable
    info.lpParameters = parameters
    info.lpDirectory = str(Path.cwd())
    info.nShow = SW_HIDE
    ctypes.set_last_error(0)
    if not _shell32.ShellExecuteExW(ctypes.byref(info)) or not info.hProcess:
        error = ctypes.get_last_error()
        code = (
            SetupErrorCode.ORCHESTRATOR_HELPER_LAUNCH_CANCELED
            if error == ERROR_CANCELLED
            else SetupErrorCode.ORCHESTRATOR_HELPER_LAUNCH_FAILED
        )
        raise SetupFailure(code, f"ShellExecuteExW failed to launch setup helper: {error}")
    try:
        _kernel32.WaitForSingleObject(info.hProcess, INFINITE)
        exit_code = wintypes.DWORD(1)
        if not _kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code)):
            error = ctypes.get_last_error()
            raise SetupFailure(SetupErrorCode.ORCHESTRATOR_HELPER_LAUNCH_FAILED, f"GetExitCodeProcess failed: {error}")
        return int(exit_code.value)
    finally:
        _kernel32.CloseHandle(info.hProcess)


def _raise_helper_failure(codex_home: Path, cleared_report: bool, exit_code: int) -> None:
    detail = f"setup helper exited with status {exit_code}"
    if cleared_report:
        try:
            report = read_setup_error_report(codex_home)
        except (OSError, ValueError) as exc:
            raise SetupFailure(
                SetupErrorCode.ORCHESTRATOR_HELPER_REPORT_READ_FAILED,
                f"{detail}; failed to read setup_error.json: {exc}",
            ) from exc
        if report is not None:
            raise SetupFailure(report.code, report.message)
    raise SetupFailure(SetupErrorCode.ORCHESTRATOR_HELPER_EXIT_NONZERO, detail)


def _require_windows() -> None:
    if os.name != "nt":
        raise SetupFailure(SetupErrorCode.ORCHESTRATOR_HELPER_LAUNCH_FAILED, "setup helper requires Windows")


__all__ = ["is_elevated", "run_setup_helper"]
