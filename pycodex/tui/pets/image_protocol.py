"""Terminal image protocol helpers for pets.

Upstream source: ``codex/codex-rs/tui/src/pets/image_protocol.rs``.

The Python port keeps protocol detection and Kitty command generation fully
semantic.  Sixel image resizing/encoding remains an explicit non-stdlib image
processing boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import base64
import os
import struct
import zlib
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="pets::image_protocol",
    source="codex/codex-rs/tui/src/pets/image_protocol.rs",
    status="complete",
)

ESC = "\x1b"
ST = "\x1b\\"
KITTY_CHUNK_SIZE = 4096
SIXEL_CACHE_VERSION = "v2"
ITERM2_KITTY_MIN_VERSION = (3, 6, 0)


class ImageProtocol(Enum):
    KITTY = "kitty"
    KITTY_LOCAL_FILE = "kitty_local_file"
    SIXEL = "sixel"


class PetImageUnsupportedReason(Enum):
    TMUX = "tmux"
    ZELLIJ = "zellij"
    ITERM2_TOO_OLD = "iterm2_too_old"
    TERMINAL = "terminal"

    def message(self) -> str:
        if self is PetImageUnsupportedReason.TMUX:
            return (
                "Pets are disabled in tmux. Terminal images don't stay pane-local in tmux "
                "and can corrupt scrollback or move between panes. Run Codex outside tmux "
                "to use pets."
            )
        if self is PetImageUnsupportedReason.ZELLIJ:
            return (
                "Pets are disabled in Zellij. Terminal images don't stay reliably "
                "pane-local in Zellij. Run Codex outside Zellij to use pets."
            )
        if self is PetImageUnsupportedReason.ITERM2_TOO_OLD:
            return "Pets require iTerm2 3.6 or newer. Upgrade iTerm2 to use terminal pets."
        return (
            "Pets aren't available in this terminal. Terminal pets need image support, and "
            "this terminal environment doesn't expose a supported image protocol. Try a "
            "terminal with Kitty graphics or Sixel support, or run Codex outside tmux."
        )


@dataclass(frozen=True)
class PetImageSupport:
    protocol_value: Optional[ImageProtocol] = None
    reason: Optional[PetImageUnsupportedReason] = None

    @classmethod
    def supported(cls, protocol: ImageProtocol) -> "PetImageSupport":
        return cls(protocol_value=protocol)

    @classmethod
    def unsupported(cls, reason: PetImageUnsupportedReason) -> "PetImageSupport":
        return cls(reason=reason)

    def protocol(self) -> Optional[ImageProtocol]:
        return self.protocol_value

    def unsupported_message(self) -> Optional[str]:
        return None if self.reason is None else self.reason.message()


class ProtocolSelection(Enum):
    AUTO = "auto"
    KITTY = "kitty"
    SIXEL = "sixel"

    def resolve(
        self,
        *,
        env: Optional[Mapping[str, str]] = None,
        terminal_info: Optional[Any] = None,
    ) -> PetImageSupport:
        if self is ProtocolSelection.KITTY:
            return PetImageSupport.supported(ImageProtocol.KITTY)
        if self is ProtocolSelection.SIXEL:
            return PetImageSupport.supported(ImageProtocol.SIXEL)
        return detect_pet_image_support(env=env, terminal_info=terminal_info)


Err = ValueError


def from_str(value: str) -> ProtocolSelection:
    try:
        return ProtocolSelection(value)
    except ValueError as exc:
        raise ValueError(f"unknown protocol {value}; expected auto, kitty, or sixel") from exc


def detect_pet_image_support(
    *,
    env: Optional[Mapping[str, str]] = None,
    terminal_info: Optional[Any] = None,
) -> PetImageSupport:
    env = os.environ if env is None else env
    if _env_present(env, "TMUX") or _env_present(env, "TMUX_PANE"):
        return PetImageSupport.unsupported(PetImageUnsupportedReason.TMUX)
    if (
        _env_present(env, "ZELLIJ")
        or _env_present(env, "ZELLIJ_SESSION_NAME")
        or _env_present(env, "ZELLIJ_VERSION")
    ):
        return PetImageSupport.unsupported(PetImageUnsupportedReason.ZELLIJ)
    if _env_present(env, "KITTY_WINDOW_ID"):
        return PetImageSupport.supported(ImageProtocol.KITTY)
    if _env_present(env, "WEZTERM_EXECUTABLE") or _env_present(env, "WEZTERM_VERSION"):
        return PetImageSupport.supported(ImageProtocol.KITTY)
    return pet_image_support_for_terminal(terminal_info or _terminal_info_from_env(env))


def pet_image_support_for_terminal(info: Any) -> PetImageSupport:
    multiplexer = _field(info, "multiplexer")
    if _matches_name(multiplexer, "tmux"):
        return PetImageSupport.unsupported(PetImageUnsupportedReason.TMUX)
    if _matches_name(multiplexer, "zellij"):
        return PetImageSupport.unsupported(PetImageUnsupportedReason.ZELLIJ)
    if supports_iterm2_kitty_graphics(info):
        return PetImageSupport.supported(ImageProtocol.KITTY_LOCAL_FILE)
    if is_iterm2_terminal(info):
        return PetImageSupport.unsupported(PetImageUnsupportedReason.ITERM2_TOO_OLD)
    if supports_kitty_graphics(info):
        return PetImageSupport.supported(ImageProtocol.KITTY)
    if supports_sixel(info):
        return PetImageSupport.supported(ImageProtocol.SIXEL)
    return PetImageSupport.unsupported(PetImageUnsupportedReason.TERMINAL)


def supports_iterm2_kitty_graphics(info: Any) -> bool:
    return is_iterm2_terminal(info) and version_is_at_least(
        _field(info, "version"),
        ITERM2_KITTY_MIN_VERSION,
    )


def is_iterm2_terminal(info: Any) -> bool:
    return _matches_name(_field(info, "name"), "iterm2") or terminal_field_contains(
        _field(info, "term_program"), "iterm"
    )


def supports_kitty_graphics(info: Any) -> bool:
    return (
        _matches_name(_field(info, "name"), "ghostty", "kitty", "wezterm")
        or terminal_field_contains(_field(info, "term"), "kitty")
        or terminal_field_contains(_field(info, "term"), "ghostty")
        or terminal_field_contains(_field(info, "term"), "wezterm")
        or terminal_field_contains(_field(info, "term_program"), "kitty")
        or terminal_field_contains(_field(info, "term_program"), "ghostty")
        or terminal_field_contains(_field(info, "term_program"), "wezterm")
    )


def supports_sixel(info: Any) -> bool:
    return (
        _matches_name(_field(info, "name"), "windowsterminal", "windows_terminal")
        or terminal_field_contains(_field(info, "term"), "sixel")
        or terminal_field_contains(_field(info, "term"), "mlterm")
        or terminal_field_contains(_field(info, "term"), "foot")
    )


def terminal_field_contains(value: Optional[str], needle: str) -> bool:
    return value is not None and needle.lower() in str(value).lower()


def version_is_at_least(version: Optional[str], minimum: Tuple[int, int, int]) -> bool:
    parsed = parse_dotted_version(version)
    return parsed is not None and parsed >= minimum


def parse_dotted_version(version: Optional[str]) -> Optional[Tuple[int, int, int]]:
    if version is None:
        return None
    parts = version.split(".")
    if len(parts) > 3:
        return None
    try:
        parsed = [int(part) for part in parts]
    except ValueError:
        return None
    while len(parsed) < 3:
        parsed.append(0)
    return tuple(parsed)  # type: ignore[return-value]


def kitty_delete_image(image_id: int, *, env: Mapping[str, str] | None = None) -> str:
    return wrap_for_tmux_if_needed(f"{ESC}_Ga=d,d=I,i={image_id},q=2;{ST}", env=env)


def kitty_transmit_png_with_id(
    path: str | Path,
    columns: int,
    rows: int,
    image_id: Optional[int] = None,
    *,
    env: Optional[Mapping[str, str]] = None,
) -> str:
    payload = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    chunks = [payload[index : index + KITTY_CHUNK_SIZE] for index in range(0, len(payload), KITTY_CHUNK_SIZE)]
    command = []
    for index, chunk in enumerate(chunks):
        more_flag = 1 if index + 1 < len(chunks) else 0
        if index == 0:
            command.append(
                f"{ESC}_Ga=T,t=d,f=100,c={columns},r={rows},q=2"
                f"{kitty_image_id_arg(image_id)},m={more_flag};{chunk}{ST}"
            )
        else:
            command.append(f"{ESC}_Gm={more_flag};{chunk}{ST}")
    return wrap_for_tmux_if_needed("".join(command), env=env)


def kitty_transmit_png_file_with_id(
    path: str | Path,
    columns: int,
    rows: int,
    image_id: Optional[int] = None,
    *,
    env: Optional[Mapping[str, str]] = None,
) -> str:
    resolved = Path(path).resolve(strict=True)
    payload = base64.b64encode(str(resolved).encode()).decode("ascii")
    command = (
        f"{ESC}_Ga=T,t=f,f=100,c={columns},r={rows},q=2"
        f"{kitty_image_id_arg(image_id)};{payload}{ST}"
    )
    return wrap_for_tmux_if_needed(command, env=env)


def kitty_image_id_arg(image_id: Optional[int]) -> str:
    return "" if image_id is None else f",i={image_id}"


def wrap_for_tmux_if_needed(command: str, *, env: Optional[Mapping[str, str]] = None) -> str:
    env = os.environ if env is None else env
    if not _env_present(env, "TMUX"):
        return command
    return f"{ESC}Ptmux;{command.replace(ESC, ESC + ESC)}{ST}"


def sixel_frame(frame_path: Any, cache_dir: Any, height_px: int) -> Path:
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    stem = Path(frame_path).stem
    if not stem:
        raise ValueError("frame path has no valid file stem")
    output = cache_path / f"{stem}_h{height_px}_{SIXEL_CACHE_VERSION}.six"
    if output.exists():
        return output
    width, height, rgba = _read_png_rgba8(Path(frame_path))
    target_height = max(1, int(height_px))
    target_width = max(1, min(0xFFFF_FFFF, (width * target_height) // max(1, height)))
    resized = _resize_rgba_nearest(rgba, width, height, target_width, target_height)
    output.write_text(encode_rgba_sixel(resized, target_width, target_height), encoding="utf-8")
    return output


@dataclass
class EnvVarGuard:
    name: str
    previous: Optional[str] = None

    @classmethod
    def new(cls, name: str, value: Optional[str]) -> "EnvVarGuard":
        previous = os.environ.get(name)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
        return cls(name, previous)

    def drop(self) -> None:
        if self.previous is None:
            os.environ.pop(self.name, None)
        else:
            os.environ[self.name] = self.previous


def drop(guard: EnvVarGuard) -> None:
    guard.drop()


@dataclass(frozen=True)
class TerminalInfo:
    name: str
    multiplexer: Optional[str] = None
    term_program: Optional[str] = None
    version: Optional[str] = None
    term: Optional[str] = None


def terminal_info_for_test(
    name: str,
    multiplexer: Optional[str],
    term_program: Optional[str],
    term: Optional[str],
) -> TerminalInfo:
    return terminal_info_with_version_for_test(name, multiplexer, term_program, None, term)


def terminal_info_with_version_for_test(
    name: str,
    multiplexer: Optional[str],
    term_program: Optional[str],
    version: Optional[str],
    term: Optional[str],
) -> TerminalInfo:
    return TerminalInfo(name, multiplexer, term_program, version, term)


def _env_present(env: Mapping[str, str], name: str) -> bool:
    return name in env and env[name] != ""


def _terminal_info_from_env(env: Mapping[str, str]) -> TerminalInfo:
    return TerminalInfo(
        name=env.get("TERM_PROGRAM", "unknown"),
        term_program=env.get("TERM_PROGRAM"),
        version=env.get("TERM_PROGRAM_VERSION"),
        term=env.get("TERM"),
    )


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _matches_name(value: Any, *names: str) -> bool:
    if value is None:
        return False
    raw = getattr(value, "name", getattr(value, "value", value))
    normalized = str(raw).replace("_", "").replace("-", "").lower()
    return normalized in {name.replace("_", "").replace("-", "").lower() for name in names}


def _read_png_rgba8(path: Path) -> Tuple[int, int, bytes]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("unsupported frame image format; expected PNG")
    pos = 8
    width = height = None
    bit_depth = color_type = None
    idat = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        payload = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", payload[:10])
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    if width is None or height is None:
        raise ValueError("invalid PNG: missing IHDR")
    if bit_depth != 8 or color_type != 6:
        raise ValueError("unsupported PNG format; expected 8-bit RGBA")
    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    rows = []
    previous = bytes(stride)
    cursor = 0
    for _row in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        if filter_type == 0:
            recon = row
        elif filter_type == 1:
            recon = _unfilter_sub(row, 4)
        elif filter_type == 2:
            recon = _unfilter_up(row, previous)
        elif filter_type == 3:
            recon = _unfilter_average(row, previous, 4)
        elif filter_type == 4:
            recon = _unfilter_paeth(row, previous, 4)
        else:
            raise ValueError("invalid PNG filter")
        previous = bytes(recon)
        rows.append(previous)
    return width, height, b"".join(rows)


def _resize_rgba_nearest(rgba: bytes, width: int, height: int, target_width: int, target_height: int) -> bytes:
    output = bytearray(target_width * target_height * 4)
    for y in range(target_height):
        src_y = min(height - 1, (y * height) // target_height)
        for x in range(target_width):
            src_x = min(width - 1, (x * width) // target_width)
            src = (src_y * width + src_x) * 4
            dst = (y * target_width + x) * 4
            output[dst : dst + 4] = rgba[src : src + 4]
    return bytes(output)


def encode_rgba_sixel(rgba: bytes, width: int, height: int) -> str:
    palette = []
    color_to_index = {}
    opaque_pixels = []
    for y in range(height):
        row = []
        for x in range(width):
            offset = (y * width + x) * 4
            r, g, b, a = rgba[offset : offset + 4]
            if a == 0:
                row.append(None)
                continue
            key = (r, g, b)
            if key not in color_to_index:
                color_to_index[key] = 224 + len(palette)
                palette.append(key)
            row.append(color_to_index[key])
        opaque_pixels.append(row)

    parts = [f"{ESC}P9;1;0q\"1;1;{width};{height}"]
    for r, g, b in palette:
        idx = color_to_index[(r, g, b)]
        parts.append(f"#{idx};2;{_pct(r)};{_pct(g)};{_pct(b)}")

    for band_start in range(0, height, 6):
        if band_start:
            parts.append("-")
        for idx in sorted(color_to_index.values()):
            parts.append(f"#{idx}")
            run_char = []
            for x in range(width):
                bits = 0
                for bit in range(6):
                    y = band_start + bit
                    if y < height and opaque_pixels[y][x] == idx:
                        bits |= 1 << bit
                run_char.append(chr(63 + bits))
            parts.append(_compress_sixel_run("".join(run_char)))
            parts.append("$")
        if parts[-1] == "$":
            parts.pop()
    parts.append(ST)
    return "".join(parts)


def _pct(value: int) -> int:
    return round((value / 255) * 100)


def _compress_sixel_run(chars: str) -> str:
    if not chars:
        return ""
    result = []
    index = 0
    while index < len(chars):
        char = chars[index]
        count = 1
        while index + count < len(chars) and chars[index + count] == char:
            count += 1
        if count >= 4:
            result.append(f"!{count}{char}")
        else:
            result.append(char * count)
        index += count
    return "".join(result)


def _unfilter_sub(raw: bytearray, bpp: int) -> bytearray:
    for i in range(bpp, len(raw)):
        raw[i] = (raw[i] + raw[i - bpp]) & 0xFF
    return raw


def _unfilter_up(raw: bytearray, previous: bytes) -> bytearray:
    for i in range(len(raw)):
        raw[i] = (raw[i] + previous[i]) & 0xFF
    return raw


def _unfilter_average(raw: bytearray, previous: bytes, bpp: int) -> bytearray:
    for i in range(len(raw)):
        left = raw[i - bpp] if i >= bpp else 0
        up = previous[i]
        raw[i] = (raw[i] + ((left + up) // 2)) & 0xFF
    return raw


def _unfilter_paeth(raw: bytearray, previous: bytes, bpp: int) -> bytearray:
    for i in range(len(raw)):
        left = raw[i - bpp] if i >= bpp else 0
        up = previous[i]
        up_left = previous[i - bpp] if i >= bpp else 0
        raw[i] = (raw[i] + _paeth(left, up, up_left)) & 0xFF
    return raw


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


__all__ = [
    "ESC",
    "EnvVarGuard",
    "Err",
    "ITERM2_KITTY_MIN_VERSION",
    "ImageProtocol",
    "KITTY_CHUNK_SIZE",
    "PetImageSupport",
    "PetImageUnsupportedReason",
    "ProtocolSelection",
    "RUST_MODULE",
    "SIXEL_CACHE_VERSION",
    "ST",
    "TerminalInfo",
    "detect_pet_image_support",
    "drop",
    "encode_rgba_sixel",
    "from_str",
    "is_iterm2_terminal",
    "kitty_delete_image",
    "kitty_image_id_arg",
    "kitty_transmit_png_file_with_id",
    "kitty_transmit_png_with_id",
    "parse_dotted_version",
    "pet_image_support_for_terminal",
    "sixel_frame",
    "supports_iterm2_kitty_graphics",
    "supports_kitty_graphics",
    "supports_sixel",
    "terminal_field_contains",
    "terminal_info_for_test",
    "terminal_info_with_version_for_test",
    "version_is_at_least",
    "wrap_for_tmux_if_needed",
]
