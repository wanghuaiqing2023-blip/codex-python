"""Native Rust/Python TUI comparison helpers.

Rust evidence:
- ``codex-cli/src/main.rs::run_interactive_tui`` owns the pre-TUI terminal
  startup guard.
- ``codex-tui/src/cli.rs`` exposes ``--no-alt-screen`` for inline rendering.
- ``codex-tui/src/lib.rs::determine_alt_screen_mode`` keeps that inline path
  out of the alternate screen.

This harness intentionally starts with pipe/subprocess comparisons.  It can
prove deterministic pre-TUI and inline transcript contracts, while full
composer/cursor/spinner parity still requires a future ConPTY layer.
"""

from __future__ import annotations

import os
import re
import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

from pycodex.utils.pty import TerminalSize, conpty_supported


RUN_NATIVE_COMPARISON_ENV = "PYCODEX_RUN_NATIVE_TUI_COMPARISON"
RUN_EXPERIMENTAL_CONPTY_ENV = "PYCODEX_RUN_EXPERIMENTAL_CONPTY_TUI"
RUN_VERIFIED_CONPTY_ENV = "PYCODEX_CONPTY_DRIVER_VERIFIED"
RUN_VERIFIED_CONPTY_TUI_ENV = "PYCODEX_CONPTY_TUI_INPUT_VERIFIED"
NATIVE_CODEX_EXE_ENV = "PYCODEX_NATIVE_CODEX_EXE"
DEFAULT_NATIVE_CODEX_EXE = Path(r"C:\Users\27605\AppData\Local\codex-rust-target\codex-rs\debug\codex.exe")

_OSC_RE = re.compile(r"\x1b\][^\x07]*(?:\x07|\x1b\\)")
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_CREATE_UNICODE_ENVIRONMENT = 0x00000400
_STARTF_USESTDHANDLES = 0x00000100
_PSEUDOCONSOLE_RESIZE_QUIRK = 0x2
_STILL_ACTIVE = 259
_WAIT_TIMEOUT = 0x00000102
_INFINITE = 0xFFFFFFFF
_ERROR_BROKEN_PIPE = 109
_ERROR_HANDLE_EOF = 38
_ERROR_NO_DATA = 232


def _timing_trace(event: str, **fields: object) -> None:
    path = os.environ.get("PYCODEX_TUI_TIMING_LOG")
    if not path:
        return
    record = {"t": time.monotonic(), "event": event, **fields}
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    except OSError:
        pass


@dataclass(frozen=True)
class TuiComparisonCommand:
    """A Rust or Python command for the same inline TUI comparison scenario."""

    kind: str
    argv: tuple[str, ...]
    cwd: Path


@dataclass(frozen=True)
class TuiProcessTranscript:
    """Captured process result with normalized text helpers."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    def normalized_stdout(self) -> str:
        return normalize_tui_text(self.stdout)

    def normalized_stderr(self) -> str:
        return normalize_tui_text(self.stderr)

    def normalized_combined(self) -> str:
        return normalize_tui_text(self.stdout + self.stderr)

    def screen_stdout(self, *, rows: int, cols: int) -> str:
        """Return a best-effort current-screen projection for ConPTY stdout.

        This is intentionally a small VT subset for native comparison tests,
        not a full terminal emulator. It covers the CSI operations emitted by
        the Rust Ratatui and Python Textual no-alt-screen paths in current
        harness traces: cursor positioning/movement, line/screen clearing,
        character erasure, SGR/color sequences, and repeated blanks.
        """

        return vt_screen_text(self.stdout, rows=rows, cols=cols)


@dataclass(frozen=True)
class ConptyInputStep:
    """One staged input write for a Windows ConPTY TUI process."""

    text: str
    resize: TerminalSize | None = None
    ready_pattern: str | None = None
    ready_text: str | None = None
    ready_text_sequence: tuple[str, ...] = ()
    ready_timeout: float = 0.2
    chunk_delay: float = 0.01
    ready_quiet_period: float = 0.0


class NativeComparisonLayer(Enum):
    """Native comparison fidelity layers for TUI evidence."""

    PIPE = "pipe"
    INTERACTIVE_PTY = "interactive_pty"


@dataclass(frozen=True)
class InteractiveTuiComparisonCapability:
    """Host capability report for real interactive Rust/Python TUI comparison.

    Pipe/subprocess runs can prove startup guards.  They cannot prove composer,
    cursor, spinner, or live transcript behavior.  This structure makes that
    boundary explicit before a test claims interactive native evidence.
    """

    layer: NativeComparisonLayer
    available: bool
    host_platform: str
    conpty_supported: bool | None
    reason: str

    def require_available(self) -> None:
        if not self.available:
            raise RuntimeError(self.reason)


def normalize_tui_text(value: str) -> str:
    """Strip ANSI/control noise and normalize newlines for stable assertions."""

    text = _OSC_RE.sub("", value)
    text = _ANSI_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def vt_screen_text(value: str, *, rows: int, cols: int) -> str:
    """Render a conservative VT screen snapshot from a captured text stream.

    Rust-focused evidence:
    - ``codex-tui`` renders through Ratatui/crossterm, which updates terminal
      cells using CSI cursor movement and erase commands.
    - Native comparison assertions that need the *current* screen must not use
      cumulative stdout alone.
    """

    row_count = max(int(rows), 1)
    col_count = max(int(cols), 1)
    screen = [[" "] * col_count for _ in range(row_count)]
    row = 0
    col = 0
    stream = _OSC_RE.sub("", value)
    index = 0
    length = len(stream)

    def clamp_cursor() -> None:
        nonlocal row, col
        row = min(max(row, 0), row_count - 1)
        col = min(max(col, 0), col_count - 1)

    def erase_display(mode: int) -> None:
        nonlocal screen
        if mode == 2:
            screen = [[" "] * col_count for _ in range(row_count)]
        elif mode == 0:
            for r in range(row, row_count):
                start = col if r == row else 0
                for c in range(start, col_count):
                    screen[r][c] = " "
        elif mode == 1:
            for r in range(0, row + 1):
                end = col if r == row else col_count - 1
                for c in range(0, min(end + 1, col_count)):
                    screen[r][c] = " "

    def erase_line(mode: int) -> None:
        if mode == 2:
            start, end = 0, col_count
        elif mode == 1:
            start, end = 0, min(col + 1, col_count)
        else:
            start, end = col, col_count
        for c in range(start, end):
            screen[row][c] = " "

    def parse_params(raw: str) -> list[int | None]:
        if not raw:
            return []
        values: list[int | None] = []
        for part in raw.split(";"):
            if part == "" or part.startswith("?"):
                values.append(None)
                continue
            try:
                values.append(int(part))
            except ValueError:
                values.append(None)
        return values

    while index < length:
        ch = stream[index]
        if ch == "\x1b" and index + 1 < length and stream[index + 1] == "[":
            match = re.match(r"\x1b\[([0-?]*)([ -/]*)([@-~])", stream[index:])
            if not match:
                index += 1
                continue
            params = parse_params(match.group(1))
            final = match.group(3)
            first = params[0] if params and params[0] is not None else None
            count = max(int(first or 1), 1)
            if final in {"H", "f"}:
                target_row = params[0] if len(params) >= 1 and params[0] is not None else 1
                target_col = params[1] if len(params) >= 2 and params[1] is not None else 1
                row = int(target_row) - 1
                col = int(target_col) - 1
                clamp_cursor()
            elif final == "A":
                row -= count
                clamp_cursor()
            elif final == "B":
                row += count
                clamp_cursor()
            elif final == "C":
                col += count
                clamp_cursor()
            elif final == "D":
                col -= count
                clamp_cursor()
            elif final == "G":
                col = count - 1
                clamp_cursor()
            elif final == "J":
                erase_display(int(first or 0))
            elif final == "K":
                erase_line(int(first or 0))
            elif final == "X":
                for c in range(col, min(col + count, col_count)):
                    screen[row][c] = " "
            # SGR/color and mode toggles are intentionally ignored.
            index += len(match.group(0))
            continue
        if ch == "\r":
            col = 0
        elif ch == "\n":
            row = min(row + 1, row_count - 1)
        elif ch == "\b":
            col = max(col - 1, 0)
        elif ch >= " ":
            screen[row][col] = ch
            if col < col_count - 1:
                col += 1
        index += 1

    return "\n".join("".join(line).rstrip() for line in screen).rstrip()


def native_comparison_enabled(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return source.get(RUN_NATIVE_COMPARISON_ENV) == "1"


def native_codex_exe_from_env(env: Mapping[str, str] | None = None) -> Path:
    source = os.environ if env is None else env
    return Path(source.get(NATIVE_CODEX_EXE_ENV, str(DEFAULT_NATIVE_CODEX_EXE)))


def interactive_tui_comparison_capability(
    *,
    os_name: str | None = None,
    conpty_probe: bool | None = None,
    conpty_driver_available: bool | None = None,
    unix_pty_driver_available: bool = False,
) -> InteractiveTuiComparisonCapability:
    """Report whether the harness can drive a real interactive terminal.

    Rust owns this boundary through ``codex-utils-pty``.  On Windows, Rust
    gates ConPTY availability through ``win::conpty_supported`` and then uses a
    real ConPTY-backed ``portable_pty`` system.  The Python port currently has a
    dependency-light PTY facade, so this harness must not treat pipe output as
    interactive TUI evidence.
    """

    platform = os.name if os_name is None else os_name
    if platform == "nt":
        supported = conpty_supported() if conpty_probe is None else bool(conpty_probe)
        driver_available = (
            _windows_conpty_driver_available()
            and os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) == "1"
            and os.environ.get(RUN_VERIFIED_CONPTY_ENV) == "1"
            if conpty_driver_available is None
            else bool(conpty_driver_available)
        )
        if not supported:
            return InteractiveTuiComparisonCapability(
                layer=NativeComparisonLayer.INTERACTIVE_PTY,
                available=False,
                host_platform=platform,
                conpty_supported=False,
                reason="Windows ConPTY is not supported on this host",
            )
        if not driver_available:
            return InteractiveTuiComparisonCapability(
                layer=NativeComparisonLayer.INTERACTIVE_PTY,
                available=False,
                host_platform=platform,
                conpty_supported=True,
                reason=(
                    "Windows ConPTY is supported, but the Python native comparison harness driver is still "
                    f"experimental; set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 only while debugging the low-level driver "
                    f"and {RUN_VERIFIED_CONPTY_ENV}=1 only after the low-level smoke is stable"
                ),
            )
        return InteractiveTuiComparisonCapability(
            layer=NativeComparisonLayer.INTERACTIVE_PTY,
            available=True,
            host_platform=platform,
            conpty_supported=True,
            reason="Windows ConPTY process driver is available",
        )

    if not unix_pty_driver_available:
        return InteractiveTuiComparisonCapability(
            layer=NativeComparisonLayer.INTERACTIVE_PTY,
            available=False,
            host_platform=platform,
            conpty_supported=None,
            reason="Unix PTY comparison is not wired into the Python native comparison harness yet",
        )
    return InteractiveTuiComparisonCapability(
        layer=NativeComparisonLayer.INTERACTIVE_PTY,
        available=True,
        host_platform=platform,
        conpty_supported=None,
        reason="Unix PTY process driver is available",
    )


def build_inline_tui_command(
    kind: str,
    *,
    repo_root: Path,
    native_exe: Path | None = None,
    python_executable: str | None = None,
    extra_args: Sequence[str] = (),
) -> TuiComparisonCommand:
    """Build equivalent Rust/Python ``--no-alt-screen`` TUI commands."""

    common = ("--no-alt-screen", "-C", str(repo_root), "-s", "read-only", "-a", "never", *map(str, extra_args))
    if kind == "rust":
        exe = native_exe or native_codex_exe_from_env()
        return TuiComparisonCommand(kind="rust", argv=(str(exe), *common), cwd=repo_root)
    if kind == "python":
        py = python_executable or sys.executable
        return TuiComparisonCommand(kind="python", argv=(py, "-m", "pycodex", *common), cwd=repo_root)
    raise ValueError(f"unknown TUI comparison command kind: {kind!r}")


def run_piped_tui_command(
    command: TuiComparisonCommand,
    *,
    input_text: str = "/quit\n",
    env: Mapping[str, str] | None = None,
    timeout: float = 15.0,
) -> TuiProcessTranscript:
    """Run an inline TUI command with piped stdin and capture text output."""

    completed = subprocess.run(
        list(command.argv),
        input=input_text,
        text=True,
        capture_output=True,
        cwd=str(command.cwd),
        env=dict(os.environ if env is None else env),
        timeout=timeout,
    )
    return TuiProcessTranscript(
        argv=command.argv,
        returncode=int(completed.returncode),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def build_rust_python_inline_pair(
    *,
    repo_root: Path,
    native_exe: Path | None = None,
    python_executable: str | None = None,
    extra_args: Sequence[str] = (),
) -> tuple[TuiComparisonCommand, TuiComparisonCommand]:
    """Return Rust then Python commands for the same inline comparison."""

    return (
        build_inline_tui_command("rust", repo_root=repo_root, native_exe=native_exe, extra_args=extra_args),
        build_inline_tui_command(
            "python",
            repo_root=repo_root,
            python_executable=python_executable,
            extra_args=extra_args,
        ),
    )


def _windows_conpty_driver_available() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        for name in (
            "CreatePseudoConsole",
            "ResizePseudoConsole",
            "ClosePseudoConsole",
            "InitializeProcThreadAttributeList",
            "UpdateProcThreadAttribute",
            "DeleteProcThreadAttributeList",
        ):
            getattr(kernel32, name)
        return True
    except Exception:
        return False


if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    HANDLE = wintypes.HANDLE
    DWORD = wintypes.DWORD
    BOOL = wintypes.BOOL
    LPVOID = wintypes.LPVOID
    LPCWSTR = wintypes.LPCWSTR
    LPWSTR = wintypes.LPWSTR
    SIZE_T = ctypes.c_size_t
    HRESULT = ctypes.c_long

    class _COORD(ctypes.Structure):
        _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

    class _SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength", DWORD),
            ("lpSecurityDescriptor", LPVOID),
            ("bInheritHandle", BOOL),
        ]

    class _STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", DWORD),
            ("lpReserved", LPWSTR),
            ("lpDesktop", LPWSTR),
            ("lpTitle", LPWSTR),
            ("dwX", DWORD),
            ("dwY", DWORD),
            ("dwXSize", DWORD),
            ("dwYSize", DWORD),
            ("dwXCountChars", DWORD),
            ("dwYCountChars", DWORD),
            ("dwFillAttribute", DWORD),
            ("dwFlags", DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
            ("hStdInput", HANDLE),
            ("hStdOutput", HANDLE),
            ("hStdError", HANDLE),
        ]

    class _STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [
            ("StartupInfo", _STARTUPINFOW),
            ("lpAttributeList", LPVOID),
        ]

    class _PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", HANDLE),
            ("hThread", HANDLE),
            ("dwProcessId", DWORD),
            ("dwThreadId", DWORD),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _kernel32.CreatePipe.argtypes = [
        ctypes.POINTER(HANDLE),
        ctypes.POINTER(HANDLE),
        ctypes.POINTER(_SECURITY_ATTRIBUTES),
        DWORD,
    ]
    _kernel32.CreatePipe.restype = BOOL
    _kernel32.CreatePseudoConsole.argtypes = [_COORD, HANDLE, HANDLE, DWORD, ctypes.POINTER(HANDLE)]
    _kernel32.CreatePseudoConsole.restype = HRESULT
    _kernel32.ClosePseudoConsole.argtypes = [HANDLE]
    _kernel32.ClosePseudoConsole.restype = None
    _kernel32.ResizePseudoConsole.argtypes = [HANDLE, _COORD]
    _kernel32.ResizePseudoConsole.restype = HRESULT
    _kernel32.InitializeProcThreadAttributeList.argtypes = [LPVOID, DWORD, DWORD, ctypes.POINTER(SIZE_T)]
    _kernel32.InitializeProcThreadAttributeList.restype = BOOL
    _kernel32.UpdateProcThreadAttribute.argtypes = [LPVOID, DWORD, ctypes.c_size_t, LPVOID, SIZE_T, LPVOID, LPVOID]
    _kernel32.UpdateProcThreadAttribute.restype = BOOL
    _kernel32.DeleteProcThreadAttributeList.argtypes = [LPVOID]
    _kernel32.DeleteProcThreadAttributeList.restype = None
    _kernel32.CreateProcessW.argtypes = [
        LPCWSTR,
        LPWSTR,
        LPVOID,
        LPVOID,
        BOOL,
        DWORD,
        LPVOID,
        LPCWSTR,
        LPVOID,
        ctypes.POINTER(_PROCESS_INFORMATION),
    ]
    _kernel32.CreateProcessW.restype = BOOL
    _kernel32.ReadFile.argtypes = [HANDLE, LPVOID, DWORD, ctypes.POINTER(DWORD), LPVOID]
    _kernel32.ReadFile.restype = BOOL
    _kernel32.PeekNamedPipe.argtypes = [
        HANDLE,
        LPVOID,
        DWORD,
        ctypes.POINTER(DWORD),
        ctypes.POINTER(DWORD),
        ctypes.POINTER(DWORD),
    ]
    _kernel32.PeekNamedPipe.restype = BOOL
    _kernel32.WriteFile.argtypes = [HANDLE, LPVOID, DWORD, ctypes.POINTER(DWORD), LPVOID]
    _kernel32.WriteFile.restype = BOOL
    _kernel32.CloseHandle.argtypes = [HANDLE]
    _kernel32.CloseHandle.restype = BOOL
    _kernel32.TerminateProcess.argtypes = [HANDLE, DWORD]
    _kernel32.TerminateProcess.restype = BOOL
    _kernel32.WaitForSingleObject.argtypes = [HANDLE, DWORD]
    _kernel32.WaitForSingleObject.restype = DWORD
    _kernel32.GetExitCodeProcess.argtypes = [HANDLE, ctypes.POINTER(DWORD)]
    _kernel32.GetExitCodeProcess.restype = BOOL
else:
    ctypes = None  # type: ignore[assignment]


def _raise_last_windows_error(context: str) -> None:
    if ctypes is None:
        raise OSError(f"{context}: Windows ctypes unavailable")
    error = ctypes.get_last_error()
    raise ctypes.WinError(error, context)


def _checked_close_handle(handle: object) -> None:
    if os.name != "nt" or ctypes is None:
        return
    raw = int(getattr(handle, "value", handle) or 0)
    if raw:
        _kernel32.CloseHandle(HANDLE(raw))


def _build_environment_block(env: Mapping[str, str] | None) -> object:
    if ctypes is None:
        return None
    source = os.environ if env is None else env
    entries = [f"{str(key)}={str(value)}" for key, value in sorted(source.items(), key=lambda item: str(item[0]).upper())]
    return ctypes.create_unicode_buffer("\0".join(entries) + "\0\0")


def _drain_windows_pipe_available(handle: object) -> bytes:
    if ctypes is None:
        return b""
    raw = HANDLE(int(getattr(handle, "value", handle) or 0))
    chunks: list[bytes] = []
    while True:
        available = DWORD(0)
        ok = _kernel32.PeekNamedPipe(raw, None, 0, None, ctypes.byref(available), None)
        if not ok or int(available.value) <= 0:
            break
        read_size = min(int(available.value), 8192)
        buffer = ctypes.create_string_buffer(read_size)
        read = DWORD(0)
        ok = _kernel32.ReadFile(raw, buffer, DWORD(read_size), ctypes.byref(read), None)
        if not ok or int(read.value) == 0:
            break
        chunks.append(buffer.raw[: int(read.value)])
    return b"".join(chunks)


def _read_windows_pipe_blocking(handle: object, sink: list[bytes], errors: list[str]) -> None:
    if ctypes is None:
        return
    raw = HANDLE(int(getattr(handle, "value", handle) or 0))
    while True:
        buffer = ctypes.create_string_buffer(8192)
        read = DWORD(0)
        ok = _kernel32.ReadFile(raw, buffer, DWORD(len(buffer)), ctypes.byref(read), None)
        if not ok or int(read.value) == 0:
            if not ok and ctypes is not None:
                error = ctypes.get_last_error()
                if error not in {_ERROR_BROKEN_PIPE, _ERROR_HANDLE_EOF, _ERROR_NO_DATA}:
                    errors.append(f"ReadFile failed: {error}")
            break
        sink.append(buffer.raw[: int(read.value)])


def _write_windows_pipe(handle: object, data: bytes) -> None:
    if ctypes is None:
        return
    raw = HANDLE(int(getattr(handle, "value", handle) or 0))
    written = DWORD(0)
    buf = ctypes.create_string_buffer(data)
    ok = _kernel32.WriteFile(raw, buf, DWORD(len(data)), ctypes.byref(written), None)
    if not ok:
        _raise_last_windows_error("WriteFile to ConPTY input failed")


def _write_windows_conpty_text(handle: object, text: str, *, chunk_delay: float) -> None:
    for chunk in _conpty_input_chunks(text):
        _timing_trace(
            "conpty_harness_write_chunk",
            chunk=repr(chunk),
            codepoints=[ord(char) for char in chunk],
        )
        _write_windows_pipe(handle, chunk.encode("utf-8", errors="replace"))
        if chunk_delay > 0:
            time.sleep(float(chunk_delay))


def _conpty_input_chunks(text: str) -> list[str]:
    """Split typed input while keeping VT special-key sequences atomic."""

    chunks: list[str] = []
    index = 0
    while index < len(text):
        if text[index] == "\x1b":
            match = re.match(r"\x1bO[P-S]", text[index:])
            if match:
                chunks.append(match.group(0))
                index += len(match.group(0))
                continue
            match = re.match(r"\x1b\[[0-?]*[ -/]*[@-~]", text[index:])
            if match:
                chunks.append(match.group(0))
                index += len(match.group(0))
                continue
            if index + 1 < len(text):
                chunks.append(text[index : index + 2])
                index += 2
                continue
        chunks.append(text[index])
        index += 1
    return chunks


def _resize_windows_conpty(hpc: object, size: TerminalSize) -> None:
    if ctypes is None:
        return
    hr = _kernel32.ResizePseudoConsole(
        HANDLE(int(getattr(hpc, "value", hpc) or 0)),
        _COORD(int(size.cols), int(size.rows)),
    )
    if int(hr) != 0:
        raise OSError(f"ResizePseudoConsole failed: HRESULT {int(hr)}")


def _captured_windows_pipe_text(chunks: Sequence[bytes]) -> str:
    return b"".join(chunks).decode("utf-8", errors="replace")


def _wait_for_windows_conpty_output_pattern(
    chunks: Sequence[bytes],
    pattern: str,
    *,
    timeout: float,
    start_offset: int = 0,
) -> bool:
    deadline = time.monotonic() + max(float(timeout), 0.0)
    compiled = re.compile(pattern)
    while time.monotonic() < deadline:
        text = normalize_tui_text(_captured_windows_pipe_text(chunks)[max(int(start_offset), 0) :])
        if compiled.search(text):
            return True
        time.sleep(0.05)
    text = normalize_tui_text(_captured_windows_pipe_text(chunks)[max(int(start_offset), 0) :])
    return compiled.search(text) is not None


def _semantic_conpty_text(value: str) -> str:
    """Return text for semantic ConPTY matching across redraw/wrap noise."""

    normalized = normalize_tui_text(value)
    return "".join(char for char in normalized.casefold() if char.isprintable() and not char.isspace())


def _wait_for_windows_conpty_semantic_text(
    chunks: Sequence[bytes],
    needle: str,
    *,
    timeout: float,
    start_offset: int = 0,
) -> bool:
    """Wait for semantic text that may be split by terminal redraw/wrapping.

    Rust's ratatui/crossterm path redraws composer rows; a real ConPTY
    transcript can split one visible draft across rows or CSI clear/redraw
    boundaries.  This helper treats the normalized printable text stream as the
    evidence surface for staged-input readiness instead of requiring a
    contiguous raw transcript line.
    """

    expected = _semantic_conpty_text(needle)
    if not expected:
        return True
    deadline = time.monotonic() + max(float(timeout), 0.0)
    while time.monotonic() < deadline:
        text = _semantic_conpty_text(_captured_windows_pipe_text(chunks)[max(int(start_offset), 0) :])
        if expected in text:
            return True
        time.sleep(0.05)
    text = _semantic_conpty_text(_captured_windows_pipe_text(chunks)[max(int(start_offset), 0) :])
    return expected in text


def _semantic_contains_ordered(value: str, needles: Sequence[str]) -> bool:
    text = _semantic_conpty_text(value)
    position = 0
    for needle in needles:
        expected = _semantic_conpty_text(needle)
        if not expected:
            continue
        found = text.find(expected, position)
        if found < 0:
            return False
        position = found + len(expected)
    return True


def _wait_for_windows_conpty_ordered_semantic_text(
    chunks: Sequence[bytes],
    needles: Sequence[str],
    *,
    timeout: float,
    start_offset: int = 0,
) -> bool:
    """Wait for multiple semantic markers in order in the ConPTY transcript."""

    deadline = time.monotonic() + max(float(timeout), 0.0)
    while time.monotonic() < deadline:
        text = _captured_windows_pipe_text(chunks)[max(int(start_offset), 0) :]
        if _semantic_contains_ordered(text, needles):
            return True
        time.sleep(0.05)
    text = _captured_windows_pipe_text(chunks)[max(int(start_offset), 0) :]
    return _semantic_contains_ordered(text, needles)


def _wait_for_windows_conpty_quiet(
    chunks: Sequence[bytes],
    *,
    quiet_period: float,
    timeout: float,
) -> bool:
    if quiet_period <= 0:
        return True
    deadline = time.monotonic() + max(float(timeout), 0.0)
    last_len = len(_captured_windows_pipe_text(chunks))
    quiet_since = time.monotonic()
    while time.monotonic() < deadline:
        time.sleep(0.05)
        current_len = len(_captured_windows_pipe_text(chunks))
        now = time.monotonic()
        if current_len != last_len:
            last_len = current_len
            quiet_since = now
            continue
        if now - quiet_since >= quiet_period:
            return True
    return False


def run_windows_conpty_tui_command(
    command: TuiComparisonCommand,
    *,
    input_text: str = "/quit\r\n",
    input_steps: Sequence[ConptyInputStep] | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 15.0,
    size: TerminalSize = TerminalSize(rows=24, cols=100),
    input_delay: float = 0.2,
    input_chunk_delay: float = 0.01,
    input_ready_pattern: str | None = None,
    stop_pattern: str | None = None,
    stop_timeout: float | None = None,
    terminate_on_stop_pattern: bool = False,
) -> TuiProcessTranscript:
    """Run an inline TUI command inside a Windows ConPTY.

    Rust uses ``codex-utils-pty`` plus the Windows ConPTY backend for true
    interactive process tests.  This helper mirrors the same OS boundary for
    the native comparison harness; it is opt-in and Windows-only.
    """

    capability = interactive_tui_comparison_capability()
    capability.require_available()
    if os.name != "nt" or ctypes is None:
        raise RuntimeError("Windows ConPTY comparison is only available on Windows")

    input_read = HANDLE()
    input_write = HANDLE()
    output_read = HANDLE()
    output_write = HANDLE()
    hpc = HANDLE()
    attr_buffer = None
    process_info = _PROCESS_INFORMATION()
    output_chunks: list[bytes] = []
    reader_errors: list[str] = []
    reader: threading.Thread | None = None

    try:
        sa = _SECURITY_ATTRIBUTES()
        sa.nLength = ctypes.sizeof(_SECURITY_ATTRIBUTES)
        sa.bInheritHandle = True
        if not _kernel32.CreatePipe(ctypes.byref(input_read), ctypes.byref(input_write), ctypes.byref(sa), 0):
            _raise_last_windows_error("CreatePipe for ConPTY input failed")
        if not _kernel32.CreatePipe(ctypes.byref(output_read), ctypes.byref(output_write), ctypes.byref(sa), 0):
            _raise_last_windows_error("CreatePipe for ConPTY output failed")

        hr = _kernel32.CreatePseudoConsole(
            _COORD(int(size.cols), int(size.rows)),
            input_read,
            output_write,
            DWORD(_PSEUDOCONSOLE_RESIZE_QUIRK),
            ctypes.byref(hpc),
        )
        if int(hr) != 0:
            raise OSError(f"CreatePseudoConsole failed: HRESULT {int(hr)}")
        # Keep the terminal-side pipe handles alive until ClosePseudoConsole.
        # Rust's PsuedoCon owns these handles for the pseudo-console lifetime.

        attr_size = SIZE_T(0)
        _kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(attr_size))
        attr_buffer = ctypes.create_string_buffer(int(attr_size.value))
        if not _kernel32.InitializeProcThreadAttributeList(attr_buffer, 1, 0, ctypes.byref(attr_size)):
            _raise_last_windows_error("InitializeProcThreadAttributeList failed")

        hpc_value = LPVOID(int(hpc.value or 0))
        if not _kernel32.UpdateProcThreadAttribute(
            attr_buffer,
            0,
            _PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
            hpc_value,
            ctypes.sizeof(HANDLE),
            None,
            None,
        ):
            _raise_last_windows_error("UpdateProcThreadAttribute for ConPTY failed")

        startup = _STARTUPINFOEXW()
        startup.StartupInfo.cb = ctypes.sizeof(_STARTUPINFOEXW)
        startup.StartupInfo.dwFlags = DWORD(_STARTF_USESTDHANDLES)
        startup.StartupInfo.hStdInput = HANDLE(-1)
        startup.StartupInfo.hStdOutput = HANDLE(-1)
        startup.StartupInfo.hStdError = HANDLE(-1)
        startup.lpAttributeList = ctypes.cast(attr_buffer, LPVOID)
        env_block = _build_environment_block(env) if env is not None else None
        cmdline = ctypes.create_unicode_buffer(subprocess.list2cmdline(command.argv))
        cwd = str(command.cwd)
        creation_flags = _EXTENDED_STARTUPINFO_PRESENT
        if env_block is not None:
            creation_flags |= _CREATE_UNICODE_ENVIRONMENT
        application_name = str(command.argv[0]) if command.argv else None
        created = _kernel32.CreateProcessW(
            application_name,
            cmdline,
            None,
            None,
            False,
            DWORD(creation_flags),
            ctypes.cast(env_block, LPVOID) if env_block is not None else None,
            cwd,
            ctypes.byref(startup),
            ctypes.byref(process_info),
        )
        if not created:
            _raise_last_windows_error("CreateProcessW for ConPTY command failed")

        reader = threading.Thread(
            target=_read_windows_pipe_blocking,
            args=(output_read, output_chunks, reader_errors),
            name="pycodex-native-conpty-reader",
            daemon=True,
        )
        reader.start()

        steps = input_steps
        if steps is None and input_text:
            steps = (
                ConptyInputStep(
                    input_text,
                    ready_pattern=input_ready_pattern,
                    ready_timeout=float(input_delay),
                    chunk_delay=float(input_chunk_delay),
                ),
            )
        search_offset = 0
        input_error: str | None = None
        for step in steps or ():
            if step.ready_pattern is not None or step.ready_text is not None or step.ready_text_sequence:
                if step.ready_pattern is not None:
                    ready = _wait_for_windows_conpty_output_pattern(
                        output_chunks,
                        step.ready_pattern,
                        timeout=float(step.ready_timeout),
                        start_offset=search_offset,
                    )
                elif step.ready_text_sequence:
                    ready = _wait_for_windows_conpty_ordered_semantic_text(
                        output_chunks,
                        step.ready_text_sequence,
                        timeout=float(step.ready_timeout),
                        start_offset=search_offset,
                    )
                else:
                    ready = _wait_for_windows_conpty_semantic_text(
                        output_chunks,
                        step.ready_text or "",
                        timeout=float(step.ready_timeout),
                        start_offset=search_offset,
                    )
                if not ready:
                    if step.ready_pattern is not None:
                        expected = step.ready_pattern
                    elif step.ready_text_sequence:
                        expected = " -> ".join(step.ready_text_sequence)
                    else:
                        expected = step.ready_text
                    input_error = f"ConPTY ready condition timed out: {expected}"
                    _kernel32.TerminateProcess(process_info.hProcess, 1)
                    break
                if step.ready_quiet_period > 0 and not _wait_for_windows_conpty_quiet(
                    output_chunks,
                    quiet_period=float(step.ready_quiet_period),
                    timeout=float(step.ready_timeout),
                ):
                    input_error = f"ConPTY output did not become quiet after ready pattern: {step.ready_pattern}"
                    _kernel32.TerminateProcess(process_info.hProcess, 1)
                    break
            elif step.ready_timeout > 0:
                time.sleep(float(step.ready_timeout))
            if step.resize is not None:
                _resize_windows_conpty(hpc, step.resize)
            if step.text:
                search_offset = len(_captured_windows_pipe_text(output_chunks))
                _write_windows_conpty_text(input_write, step.text, chunk_delay=float(step.chunk_delay))

        stopped_on_pattern = False
        if input_error is None and stop_pattern is not None:
            stopped_on_pattern = _wait_for_windows_conpty_output_pattern(
                output_chunks,
                stop_pattern,
                timeout=float(timeout if stop_timeout is None else stop_timeout),
            )
            if stopped_on_pattern and terminate_on_stop_pattern:
                _kernel32.TerminateProcess(process_info.hProcess, 1)

        deadline = time.monotonic() + float(timeout)
        timed_out = False
        while time.monotonic() < deadline:
            wait_ms = max(1, min(100, int((deadline - time.monotonic()) * 1000)))
            wait_result = _kernel32.WaitForSingleObject(process_info.hProcess, DWORD(wait_ms))
            if int(wait_result) != _WAIT_TIMEOUT:
                break
        else:
            timed_out = True
            _kernel32.TerminateProcess(process_info.hProcess, 1)

        final_wait = _kernel32.WaitForSingleObject(process_info.hProcess, DWORD(2000))
        exit_code = DWORD(_STILL_ACTIVE)
        if int(final_wait) == _WAIT_TIMEOUT:
            exit_code = DWORD(1)
        elif not _kernel32.GetExitCodeProcess(process_info.hProcess, ctypes.byref(exit_code)):
            _raise_last_windows_error("GetExitCodeProcess failed")
        if int(getattr(hpc, "value", 0) or 0):
            _kernel32.ClosePseudoConsole(hpc)
            hpc = HANDLE()
        _checked_close_handle(output_write)
        output_write = HANDLE()
        if reader is not None:
            reader.join(timeout=1.0)
        output_chunks.append(_drain_windows_pipe_available(output_read))

        raw_output = _captured_windows_pipe_text(output_chunks)
        stderr = input_error or ("ConPTY command timed out" if timed_out else "")
        if stopped_on_pattern and terminate_on_stop_pattern:
            stderr = "; ".join(filter(None, [stderr, "ConPTY command terminated after stop pattern"]))
        if reader_errors:
            stderr = "; ".join([stderr, *reader_errors]).strip("; ")
        return TuiProcessTranscript(
            argv=command.argv,
            returncode=int(exit_code.value),
            stdout=raw_output,
            stderr=stderr,
        )
    finally:
        if attr_buffer is not None and os.name == "nt" and ctypes is not None:
            _kernel32.DeleteProcThreadAttributeList(attr_buffer)
        if int(getattr(hpc, "value", 0) or 0):
            _kernel32.ClosePseudoConsole(hpc)
        for handle in (
            process_info.hThread,
            process_info.hProcess,
            input_read,
            input_write,
            output_read,
            output_write,
        ):
            _checked_close_handle(handle)
