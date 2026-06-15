"""Port of Rust ``codex-login::auth::default_client``.

Rust source:
- ``codex/codex-rs/login/src/auth/default_client.rs``

The Rust module builds ``reqwest`` clients. The Python port keeps the
dependency-free, observable configuration contract: originator selection,
User-Agent construction, residency headers, and sandbox proxy policy.
"""

from __future__ import annotations

import os
import platform
import threading
from dataclasses import dataclass
from typing import Any

from pycodex import __version__
from pycodex.config import ResidencyRequirement


DEFAULT_ORIGINATOR = "codex_cli_rs"
CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR = "CODEX_INTERNAL_ORIGINATOR_OVERRIDE"
RESIDENCY_HEADER_NAME = "x-openai-internal-codex-residency"
USER_AGENT_HEADER_NAME = "user-agent"

_USER_AGENT_SUFFIX: str | None = None
_ORIGINATOR: "Originator | None" = None
_REQUIREMENTS_RESIDENCY: ResidencyRequirement | None = None
_LOCK = threading.RLock()


@dataclass(frozen=True)
class Originator:
    value: str
    header_value: str


class SetOriginatorError(ValueError):
    pass


@dataclass(frozen=True)
class CodexHttpClient:
    default_headers: dict[str, str]
    no_proxy: bool = False

    def get(self, url: str) -> "CodexRequestBuilder":
        return CodexRequestBuilder(client=self, method="GET", url=url)


@dataclass(frozen=True)
class CodexRequestBuilder:
    client: CodexHttpClient
    method: str
    url: str


def set_user_agent_suffix(value: str | None) -> None:
    global _USER_AGENT_SUFFIX
    with _LOCK:
        _USER_AGENT_SUFFIX = value


def set_default_originator(value: str) -> None:
    global _ORIGINATOR
    if not _valid_header_value(value):
        raise SetOriginatorError("InvalidHeaderValue")
    originator_value = _get_originator_value(value)
    with _LOCK:
        if _ORIGINATOR is not None:
            raise SetOriginatorError("AlreadyInitialized")
        _ORIGINATOR = originator_value


def set_default_client_residency_requirement(
    enforce_residency: ResidencyRequirement | str | None,
) -> None:
    global _REQUIREMENTS_RESIDENCY
    with _LOCK:
        _REQUIREMENTS_RESIDENCY = (
            None if enforce_residency is None else ResidencyRequirement(enforce_residency)
        )


def originator() -> Originator:
    global _ORIGINATOR
    with _LOCK:
        if _ORIGINATOR is not None:
            return _ORIGINATOR
        if CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR in os.environ:
            _ORIGINATOR = _get_originator_value(None)
            return _ORIGINATOR
    return _get_originator_value(None)


def is_first_party_originator(originator_value: str) -> bool:
    return (
        originator_value == DEFAULT_ORIGINATOR
        or originator_value == "codex-tui"
        or originator_value == "codex_vscode"
        or originator_value.startswith("Codex ")
    )


def is_first_party_chat_originator(originator_value: str) -> bool:
    return originator_value in {"codex_atlas", "codex_chatgpt_desktop"}


def get_codex_user_agent() -> str:
    current_originator = originator()
    system = platform.system() or "unknown"
    version = platform.release() or platform.version() or "unknown"
    architecture = platform.machine() or "unknown"
    terminal_user_agent = _terminal_user_agent()
    prefix = (
        f"{current_originator.value}/{__version__} "
        f"({system} {version}; {architecture}) {terminal_user_agent}"
    )
    suffix = (_USER_AGENT_SUFFIX or "").strip()
    candidate = f"{prefix} ({suffix})" if suffix else prefix
    return sanitize_user_agent(candidate, prefix)


def sanitize_user_agent(candidate: str, fallback: str) -> str:
    if _valid_header_value(candidate):
        return candidate

    sanitized = "".join(ch if " " <= ch <= "~" else "_" for ch in candidate)
    if sanitized and _valid_header_value(sanitized):
        return sanitized
    if _valid_header_value(fallback):
        return fallback
    return originator().value


def create_client() -> CodexHttpClient:
    return CodexHttpClient(default_headers=default_headers(), no_proxy=is_sandboxed())


def build_reqwest_client() -> CodexHttpClient:
    return try_build_reqwest_client()


def try_build_reqwest_client() -> CodexHttpClient:
    return create_client()


def default_headers() -> dict[str, str]:
    headers = {
        "originator": originator().header_value,
    }
    user_agent = get_codex_user_agent()
    if _valid_header_value(user_agent):
        headers[USER_AGENT_HEADER_NAME] = user_agent
    with _LOCK:
        residency = _REQUIREMENTS_RESIDENCY
    if residency is not None and RESIDENCY_HEADER_NAME not in headers:
        if residency is ResidencyRequirement.US:
            headers[RESIDENCY_HEADER_NAME] = "us"
    return headers


def is_sandboxed(env: dict[str, str] | None = None) -> bool:
    env_map = os.environ if env is None else env
    return env_map.get("CODEX_SANDBOX") == "seatbelt"


def _get_originator_value(provided: str | None) -> Originator:
    value = os.environ.get(CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR) or provided or DEFAULT_ORIGINATOR
    if _valid_header_value(value):
        return Originator(value=value, header_value=value)
    return Originator(value=DEFAULT_ORIGINATOR, header_value=DEFAULT_ORIGINATOR)


def _valid_header_value(value: Any) -> bool:
    return isinstance(value, str) and not any(ch in value for ch in "\r\n\0")


def _terminal_user_agent() -> str:
    term_program = os.environ.get("TERM_PROGRAM")
    if term_program:
        term_version = os.environ.get("TERM_PROGRAM_VERSION")
        return f"{term_program}/{term_version}" if term_version else term_program
    return "unknown"


def _reset_for_tests() -> None:
    global _USER_AGENT_SUFFIX, _ORIGINATOR, _REQUIREMENTS_RESIDENCY
    with _LOCK:
        _USER_AGENT_SUFFIX = None
        _ORIGINATOR = None
        _REQUIREMENTS_RESIDENCY = None


__all__ = [
    "CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR",
    "DEFAULT_ORIGINATOR",
    "RESIDENCY_HEADER_NAME",
    "USER_AGENT_HEADER_NAME",
    "CodexHttpClient",
    "CodexRequestBuilder",
    "Originator",
    "ResidencyRequirement",
    "SetOriginatorError",
    "build_reqwest_client",
    "create_client",
    "default_headers",
    "get_codex_user_agent",
    "is_first_party_chat_originator",
    "is_first_party_originator",
    "is_sandboxed",
    "originator",
    "sanitize_user_agent",
    "set_default_client_residency_requirement",
    "set_default_originator",
    "set_user_agent_suffix",
    "try_build_reqwest_client",
]
