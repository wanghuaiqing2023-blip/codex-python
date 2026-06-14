"""Clipboard paste helpers for Rust ``codex-tui::clipboard_paste``.

Python ports the deterministic path-normalization and image-format behavior.
Native image clipboard capture remains an explicit dependency boundary because
Rust uses ``arboard`` and ``image`` crates for that platform integration.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="clipboard_paste", source="codex/codex-rs/tui/src/clipboard_paste.rs")


class PasteImageErrorKind(Enum):
    CLIPBOARD_UNAVAILABLE = "ClipboardUnavailable"
    NO_IMAGE = "NoImage"
    ENCODE_FAILED = "EncodeFailed"
    IO_ERROR = "IoError"


@dataclass(frozen=True)
class PasteImageError(Exception):
    kind: PasteImageErrorKind
    message: str

    @classmethod
    def clipboard_unavailable(cls, message: str) -> "PasteImageError":
        return cls(PasteImageErrorKind.CLIPBOARD_UNAVAILABLE, message)

    @classmethod
    def no_image(cls, message: str) -> "PasteImageError":
        return cls(PasteImageErrorKind.NO_IMAGE, message)

    @classmethod
    def encode_failed(cls, message: str) -> "PasteImageError":
        return cls(PasteImageErrorKind.ENCODE_FAILED, message)

    @classmethod
    def io_error(cls, message: str) -> "PasteImageError":
        return cls(PasteImageErrorKind.IO_ERROR, message)

    def __str__(self) -> str:
        if self.kind is PasteImageErrorKind.CLIPBOARD_UNAVAILABLE:
            return f"clipboard unavailable: {self.message}"
        if self.kind is PasteImageErrorKind.NO_IMAGE:
            return f"no image on clipboard: {self.message}"
        if self.kind is PasteImageErrorKind.ENCODE_FAILED:
            return f"could not encode image: {self.message}"
        return f"io error: {self.message}"


def fmt(error: PasteImageError) -> str:
    return str(error)


class EncodedImageFormat(Enum):
    PNG = "Png"
    JPEG = "Jpeg"
    OTHER = "Other"

    def label(self) -> str:
        if self is EncodedImageFormat.PNG:
            return "PNG"
        if self is EncodedImageFormat.JPEG:
            return "JPEG"
        return "IMG"


@dataclass(frozen=True)
class PastedImageInfo:
    width: int
    height: int
    encoded_format: EncodedImageFormat


def paste_image_as_png() -> tuple[bytes, PastedImageInfo]:
    raise PasteImageError.clipboard_unavailable("clipboard image paste is unsupported by the Python stdlib backend")


def paste_image_to_temp_png() -> tuple[Path, PastedImageInfo]:
    try:
        png, info = paste_image_as_png()
    except PasteImageError as error:
        fallback = try_wsl_clipboard_fallback(error)
        if fallback is not None:
            return fallback
        raise

    try:
        handle = tempfile.NamedTemporaryFile(prefix="codex-clipboard-", suffix=".png", delete=False)
        path = Path(handle.name)
        with handle:
            handle.write(png)
        return path, info
    except OSError as exc:
        raise PasteImageError.io_error(str(exc)) from None


def try_wsl_clipboard_fallback(error: PasteImageError) -> tuple[Path, PastedImageInfo] | None:
    if not is_probably_wsl() or error.kind not in {
        PasteImageErrorKind.CLIPBOARD_UNAVAILABLE,
        PasteImageErrorKind.NO_IMAGE,
    }:
        return None

    win_path = try_dump_windows_clipboard_image()
    if not win_path:
        return None
    mapped = convert_windows_path_to_wsl(win_path)
    if mapped is None:
        return None

    return mapped, PastedImageInfo(width=0, height=0, encoded_format=EncodedImageFormat.PNG)


def try_dump_windows_clipboard_image() -> str | None:
    script = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "$img = Get-Clipboard -Format Image; "
        "if ($img -ne $null) { "
        "$p=[System.IO.Path]::GetTempFileName(); "
        "$p = [System.IO.Path]::ChangeExtension($p,'png'); "
        "$img.Save($p,[System.Drawing.Imaging.ImageFormat]::Png); "
        "Write-Output $p "
        "} else { exit 1 }"
    )
    for cmd in ("powershell.exe", "pwsh", "powershell"):
        try:
            output = subprocess.run([cmd, "-NoProfile", "-Command", script], capture_output=True, text=True, check=False)
        except OSError:
            continue
        if output.returncode == 0:
            path = output.stdout.strip()
            if path:
                return path
    return None


def normalize_pasted_path(pasted: str) -> Path | None:
    pasted = pasted.strip()
    unquoted = _strip_matching_simple_quotes(pasted)

    parsed = urlparse(unquoted)
    if parsed.scheme == "file":
        return _file_url_to_path(parsed)

    windows = normalize_windows_path(unquoted)
    if windows is not None:
        return windows

    try:
        parts = shlex.split(pasted, posix=True)
    except ValueError:
        parts = []
    if len(parts) == 1:
        part = parts[0]
        windows = normalize_windows_path(part)
        if windows is not None:
            return windows
        return Path(part)

    return None


def _strip_matching_simple_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _file_url_to_path(parsed: Any) -> Path | None:
    if parsed.netloc and parsed.netloc not in {"localhost"}:
        path_text = f"//{parsed.netloc}{parsed.path}"
    else:
        path_text = parsed.path
    path_text = unquote(path_text)
    if sys.platform == "win32" and len(path_text) >= 3 and path_text[0] == "/" and path_text[2] == ":":
        path_text = path_text[1:]
    return Path(path_text)


def is_probably_wsl() -> bool:
    if sys.platform != "linux":
        return False
    for proc_path in ("/proc/version", "/proc/sys/kernel/osrelease"):
        try:
            text = Path(proc_path).read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        if "microsoft" in text or "wsl" in text:
            return True
    return "WSL_DISTRO_NAME" in os.environ or "WSL_INTEROP" in os.environ


def convert_windows_path_to_wsl(input: str) -> Path | None:
    if input.startswith("\\\\"):
        return None
    if len(input) < 2 or input[1] != ":":
        return None
    drive_letter = input[0].lower()
    if not ("a" <= drive_letter <= "z"):
        return None
    rest = input[2:].lstrip("\\/")
    result = Path(f"/mnt/{drive_letter}")
    for component in rest.replace("\\", "/").split("/"):
        if component:
            result = result / component
    return result


def normalize_windows_path(input: str) -> Path | None:
    drive = (
        len(input) >= 3
        and input[0].isalpha()
        and input[1] == ":"
        and input[2] in {"\\", "/"}
    )
    unc = input.startswith("\\\\")
    if not drive and not unc:
        return None

    if sys.platform == "linux" and is_probably_wsl():
        converted = convert_windows_path_to_wsl(input)
        if converted is not None:
            return converted

    return Path(input)


def pasted_image_format(path: str | os.PathLike[str]) -> EncodedImageFormat:
    text = os.fspath(path)
    normalized = text.replace("\\", "/")
    filename = normalized.rsplit("/", 1)[-1]
    if "." not in filename:
        return EncodedImageFormat.OTHER
    extension = filename.rsplit(".", 1)[-1].lower()
    if extension == "png":
        return EncodedImageFormat.PNG
    if extension in {"jpg", "jpeg"}:
        return EncodedImageFormat.JPEG
    return EncodedImageFormat.OTHER


__all__ = [
    "EncodedImageFormat",
    "PasteImageError",
    "PasteImageErrorKind",
    "PastedImageInfo",
    "RUST_MODULE",
    "convert_windows_path_to_wsl",
    "fmt",
    "is_probably_wsl",
    "normalize_pasted_path",
    "normalize_windows_path",
    "paste_image_as_png",
    "paste_image_to_temp_png",
    "pasted_image_format",
    "try_dump_windows_clipboard_image",
    "try_wsl_clipboard_fallback",
]
