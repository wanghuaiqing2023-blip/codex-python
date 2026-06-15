"""Clipboard paste helpers for Rust ``codex-tui::clipboard_paste``.

Python ports the deterministic path-normalization and image-format behavior.
Native image clipboard capture remains an explicit dependency boundary because
Rust uses ``arboard`` and ``image`` crates for that platform integration.
"""

from __future__ import annotations

import json
import os
import shlex
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Tuple
from urllib.parse import unquote, urlparse

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="clipboard_paste",
    source="codex/codex-rs/tui/src/clipboard_paste.rs",
    status="complete",
)


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


def paste_image_as_png() -> Tuple[bytes, PastedImageInfo]:
    if sys.platform == "win32":
        dumped = try_dump_windows_clipboard_image_with_info()
        if dumped is None:
            raise PasteImageError.no_image("no image on clipboard")
        path, info = dumped
        try:
            return Path(path).read_bytes(), info
        except OSError as exc:
            raise PasteImageError.io_error(str(exc)) from None

    if sys.platform == "android":
        raise PasteImageError.clipboard_unavailable("clipboard image paste is unsupported on Android")

    raise PasteImageError.clipboard_unavailable(
        "clipboard image paste requires a platform clipboard backend"
    )


def paste_image_to_temp_png() -> Tuple[Path, PastedImageInfo]:
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


def try_wsl_clipboard_fallback(error: PasteImageError) -> Optional[Tuple[Path, PastedImageInfo]]:
    if not is_probably_wsl() or error.kind not in {
        PasteImageErrorKind.CLIPBOARD_UNAVAILABLE,
        PasteImageErrorKind.NO_IMAGE,
    }:
        return None

    dumped = try_dump_windows_clipboard_image_with_info()
    if dumped is None:
        return None
    win_path, info = dumped
    mapped = convert_windows_path_to_wsl(win_path)
    if mapped is None:
        return None
    probed = _probe_png_info(mapped)
    return mapped, probed or info


def try_dump_windows_clipboard_image() -> Optional[str]:
    dumped = try_dump_windows_clipboard_image_with_info()
    return dumped[0] if dumped else None


def try_dump_windows_clipboard_image_with_info() -> Optional[Tuple[str, PastedImageInfo]]:
    script = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "Add-Type -AssemblyName System.Drawing; "
        "$img = $null; "
        "try { $img = Get-Clipboard -Format Image } catch {} "
        "if ($img -eq $null) { "
        "  try { "
        "    $files = Get-Clipboard -Format FileDropList; "
        "    foreach ($f in $files) { "
        "      try { $img = [System.Drawing.Image]::FromFile($f); break } catch {} "
        "    } "
        "  } catch {} "
        "} "
        "if ($img -ne $null) { "
        "  $p=[System.IO.Path]::GetTempFileName(); "
        "  $p = [System.IO.Path]::ChangeExtension($p,'png'); "
        "  $img.Save($p,[System.Drawing.Imaging.ImageFormat]::Png); "
        "  $o=[pscustomobject]@{ path=$p; width=$img.Width; height=$img.Height }; "
        "  $o | ConvertTo-Json -Compress "
        "} else { exit 1 }"
    )
    for cmd in ("powershell.exe", "pwsh", "powershell"):
        try:
            output = subprocess.run([cmd, "-NoProfile", "-Command", script], capture_output=True, text=True, check=False)
        except OSError:
            continue
        if output.returncode == 0:
            raw = output.stdout.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
                path = str(data["path"])
                width = int(data["width"])
                height = int(data["height"])
            except Exception:
                path = raw
                info = _probe_png_info(Path(path))
                if info is None:
                    continue
                return path, info
            return path, PastedImageInfo(width, height, EncodedImageFormat.PNG)
    return None


def normalize_pasted_path(pasted: str) -> Optional[Path]:
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


def _file_url_to_path(parsed: Any) -> Optional[Path]:
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


def convert_windows_path_to_wsl(input: str) -> Optional[Path]:
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


def normalize_windows_path(input: str) -> Optional[Path]:
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


def pasted_image_format(path: Any) -> EncodedImageFormat:
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


def _probe_png_info(path: Path) -> Optional[PastedImageInfo]:
    try:
        with Path(path).open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    return _png_info_from_bytes(header)


def _png_info_from_bytes(data: bytes) -> Optional[PastedImageInfo]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return PastedImageInfo(width=width, height=height, encoded_format=EncodedImageFormat.PNG)


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
    "try_dump_windows_clipboard_image_with_info",
    "try_wsl_clipboard_fallback",
]
