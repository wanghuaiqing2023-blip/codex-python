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
from pathlib import Path
from typing import Any, Mapping

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="pets::image_protocol",
    source="codex/codex-rs/tui/src/pets/image_protocol.rs",
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
    protocol_value: ImageProtocol | None = None
    reason: PetImageUnsupportedReason | None = None

    @classmethod
    def supported(cls, protocol: ImageProtocol) -> "PetImageSupport":
        return cls(protocol_value=protocol)

    @classmethod
    def unsupported(cls, reason: PetImageUnsupportedReason) -> "PetImageSupport":
        return cls(reason=reason)

    def protocol(self) -> ImageProtocol | None:
        return self.protocol_value

    def unsupported_message(self) -> str | None:
        return None if self.reason is None else self.reason.message()


class ProtocolSelection(Enum):
    AUTO = "auto"
    KITTY = "kitty"
    SIXEL = "sixel"

    def resolve(
        self,
        *,
        env: Mapping[str, str] | None = None,
        terminal_info: Any | None = None,
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
    env: Mapping[str, str] | None = None,
    terminal_info: Any | None = None,
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


def terminal_field_contains(value: str | None, needle: str) -> bool:
    return value is not None and needle.lower() in str(value).lower()


def version_is_at_least(version: str | None, minimum: tuple[int, int, int]) -> bool:
    parsed = parse_dotted_version(version)
    return parsed is not None and parsed >= minimum


def parse_dotted_version(version: str | None) -> tuple[int, int, int] | None:
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
    image_id: int | None = None,
    *,
    env: Mapping[str, str] | None = None,
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
    image_id: int | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    resolved = Path(path).resolve(strict=True)
    payload = base64.b64encode(str(resolved).encode()).decode("ascii")
    command = (
        f"{ESC}_Ga=T,t=f,f=100,c={columns},r={rows},q=2"
        f"{kitty_image_id_arg(image_id)};{payload}{ST}"
    )
    return wrap_for_tmux_if_needed(command, env=env)


def kitty_image_id_arg(image_id: int | None) -> str:
    return "" if image_id is None else f",i={image_id}"


def wrap_for_tmux_if_needed(command: str, *, env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    if not _env_present(env, "TMUX"):
        return command
    return f"{ESC}Ptmux;{command.replace(ESC, ESC + ESC)}{ST}"


def sixel_frame(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "sixel_frame")


@dataclass
class EnvVarGuard:
    name: str
    previous: str | None = None

    @classmethod
    def new(cls, name: str, value: str | None) -> "EnvVarGuard":
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
    multiplexer: str | None = None
    term_program: str | None = None
    version: str | None = None
    term: str | None = None


def terminal_info_for_test(
    name: str,
    multiplexer: str | None,
    term_program: str | None,
    term: str | None,
) -> TerminalInfo:
    return terminal_info_with_version_for_test(name, multiplexer, term_program, None, term)


def terminal_info_with_version_for_test(
    name: str,
    multiplexer: str | None,
    term_program: str | None,
    version: str | None,
    term: str | None,
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
