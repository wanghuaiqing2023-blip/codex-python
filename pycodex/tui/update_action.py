"""Behavior port for Rust ``codex-tui::update_action``.

Upstream source: ``codex/codex-rs/tui/src/update_action.rs``.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Tuple, Union

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="update_action", source="codex/codex-rs/tui/src/update_action.rs", status="complete")


class InstallMethod(str, Enum):
    NPM = "npm"
    BUN = "bun"
    BREW = "brew"
    STANDALONE = "standalone"
    OTHER = "other"


class StandalonePlatform(str, Enum):
    UNIX = "unix"
    WINDOWS = "windows"


@dataclass(frozen=True)
class InstallContext:
    method: Union[InstallMethod, str]
    platform: Optional[Union[StandalonePlatform, str]] = None
    package_layout: Any = None


class UpdateAction(Enum):
    """Update action the CLI should perform after the TUI exits."""

    NPM_GLOBAL_LATEST = "npm_global_latest"
    BUN_GLOBAL_LATEST = "bun_global_latest"
    BREW_UPGRADE = "brew_upgrade"
    STANDALONE_UNIX = "standalone_unix"
    STANDALONE_WINDOWS = "standalone_windows"

    @classmethod
    def from_install_context(cls, context: Any) -> Optional["UpdateAction"]:
        method = _install_method(context)
        if method is InstallMethod.NPM:
            return cls.NPM_GLOBAL_LATEST
        if method is InstallMethod.BUN:
            return cls.BUN_GLOBAL_LATEST
        if method is InstallMethod.BREW:
            return cls.BREW_UPGRADE
        if method is InstallMethod.STANDALONE:
            platform = _standalone_platform(_get(context, "platform", _get(_get(context, "method"), "platform")))
            if platform is StandalonePlatform.UNIX:
                return cls.STANDALONE_UNIX
            if platform is StandalonePlatform.WINDOWS:
                return cls.STANDALONE_WINDOWS
            raise ValueError("standalone install context requires unix or windows platform")
        return None

    def command_args(self) -> Tuple[str, Tuple[str, ...]]:
        if self is UpdateAction.NPM_GLOBAL_LATEST:
            return "npm", ("install", "-g", "@openai/codex")
        if self is UpdateAction.BUN_GLOBAL_LATEST:
            return "bun", ("install", "-g", "@openai/codex")
        if self is UpdateAction.BREW_UPGRADE:
            return "brew", ("upgrade", "--cask", "codex")
        if self is UpdateAction.STANDALONE_UNIX:
            return (
                "sh",
                (
                    "-c",
                    "curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh",
                ),
            )
        if self is UpdateAction.STANDALONE_WINDOWS:
            return (
                "powershell",
                (
                    "-ExecutionPolicy",
                    "Bypass",
                    "-c",
                    "$env:CODEX_NON_INTERACTIVE=1; irm https://chatgpt.com/codex/install.ps1 | iex",
                ),
            )
        raise AssertionError(f"unhandled update action: {self}")

    def command_str(self) -> str:
        command, args = self.command_args()
        return shlex.join((command, *args))


def get_update_action(
    context: Any = None,
    *,
    current_context: Optional[Callable[[], Any]] = None,
) -> Optional[UpdateAction]:
    """Resolve the current update action from an install context.

    Rust delegates to ``InstallContext::current()`` in release builds. Python
    delegates to the ported ``pycodex.install_context.InstallContext.current``
    by default while still accepting injected contexts for deterministic tests.
    """

    if context is None:
        if current_context is None:
            from pycodex.install_context import InstallContext as CurrentInstallContext

            current_context = CurrentInstallContext.current
        context = current_context()
    if context is None:
        return None
    return UpdateAction.from_install_context(context)


def maps_install_context_to_update_action() -> None:
    assert UpdateAction.from_install_context(InstallContext(InstallMethod.OTHER)) is None
    assert UpdateAction.from_install_context(InstallContext(InstallMethod.NPM)) is UpdateAction.NPM_GLOBAL_LATEST
    assert UpdateAction.from_install_context(InstallContext(InstallMethod.BUN)) is UpdateAction.BUN_GLOBAL_LATEST
    assert UpdateAction.from_install_context(InstallContext(InstallMethod.BREW)) is UpdateAction.BREW_UPGRADE
    assert (
        UpdateAction.from_install_context(InstallContext(InstallMethod.STANDALONE, StandalonePlatform.UNIX))
        is UpdateAction.STANDALONE_UNIX
    )
    assert (
        UpdateAction.from_install_context(InstallContext(InstallMethod.STANDALONE, StandalonePlatform.WINDOWS))
        is UpdateAction.STANDALONE_WINDOWS
    )


def standalone_update_commands_rerun_latest_installer() -> None:
    assert UpdateAction.STANDALONE_UNIX.command_args() == (
        "sh",
        ("-c", "curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh"),
    )
    assert UpdateAction.STANDALONE_WINDOWS.command_args() == (
        "powershell",
        (
            "-ExecutionPolicy",
            "Bypass",
            "-c",
            "$env:CODEX_NON_INTERACTIVE=1; irm https://chatgpt.com/codex/install.ps1 | iex",
        ),
    )


def _install_method(context: Any) -> InstallMethod:
    raw = _get(context, "method", context)
    kind = _get(raw, "kind")
    if kind is not None:
        raw = kind
    if isinstance(raw, dict) and "type" in raw:
        raw = raw["type"]
    if isinstance(raw, InstallMethod):
        return raw
    normalized = _token(raw)
    mapping = {
        "npm": InstallMethod.NPM,
        "bun": InstallMethod.BUN,
        "brew": InstallMethod.BREW,
        "standalone": InstallMethod.STANDALONE,
        "other": InstallMethod.OTHER,
    }
    return mapping.get(normalized, InstallMethod.OTHER)


def _standalone_platform(raw: Any) -> Optional[StandalonePlatform]:
    if isinstance(raw, dict):
        raw = raw.get("platform")
    platform = _get(raw, "platform")
    if platform is not None:
        raw = platform
    if isinstance(raw, StandalonePlatform):
        return raw
    if raw is None:
        return None
    normalized = _token(raw)
    if normalized == "unix":
        return StandalonePlatform.UNIX
    if normalized == "windows":
        return StandalonePlatform.WINDOWS
    return None


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _token(raw: Any) -> str:
    value = getattr(raw, "value", raw)
    if isinstance(value, str):
        return value.lower()
    name = getattr(raw, "name", None)
    if isinstance(name, str):
        return name.lower()
    return str(raw).lower()


__all__ = [
    "InstallContext",
    "InstallMethod",
    "RUST_MODULE",
    "StandalonePlatform",
    "UpdateAction",
    "get_update_action",
    "maps_install_context_to_update_action",
    "standalone_update_commands_rerun_latest_installer",
]

