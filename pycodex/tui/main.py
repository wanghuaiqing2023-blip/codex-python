"""Binary entry helpers for Rust ``codex-tui/src/main.rs``."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
import sys
from typing import Any, Awaitable, Callable, Iterable, TextIO

from pycodex.protocol import TokenUsage
from pycodex.utils_cli import resume_hint

from . import AppExitInfo, Cli, ExitReason, ExitReasonPayload, RUST_MODULE as TUI_LIB_RUST_MODULE, run_main
from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="main",
    source="codex/codex-rs/tui/src/main.rs",
    status="complete",
)


@dataclass(frozen=True)
class CliConfigOverrides:
    raw_overrides: tuple[Any, ...] = ()


@dataclass(frozen=True)
class TopCli:
    config_overrides: CliConfigOverrides = field(default_factory=CliConfigOverrides)
    inner: Cli = field(default_factory=Cli)


def _token_usage_is_zero(token_usage: Any) -> bool:
    if token_usage is None:
        return True
    is_zero = getattr(token_usage, "is_zero", None)
    if callable(is_zero):
        return bool(is_zero())
    return False


def format_exit_messages(exit_info: AppExitInfo, color_enabled: bool = False) -> list[str]:
    """Mirror Rust ``main.rs::format_exit_messages``."""

    lines: list[str] = []
    token_usage = exit_info.token_usage
    if not _token_usage_is_zero(token_usage):
        lines.append(str(token_usage))

    command = resume_hint(exit_info.thread_name, exit_info.thread_id)
    if command is not None:
        if color_enabled:
            command = f"\x1b[36m{command}\x1b[39m"
        lines.append(f"To continue this session, run {command}")
    return lines


def merge_top_cli_overrides(top_cli: TopCli) -> Cli:
    """Apply top-level ``-c`` overrides before TUI-local overrides."""

    inner = deepcopy(top_cli.inner)
    existing = tuple(getattr(getattr(inner, "config_overrides", None), "raw_overrides", ()))
    merged = tuple(top_cli.config_overrides.raw_overrides) + existing
    config_overrides = getattr(inner, "config_overrides", None)
    if config_overrides is None:
        object.__setattr__(inner, "config_overrides", CliConfigOverrides(merged)) if hasattr(inner, "__dataclass_fields__") else setattr(inner, "config_overrides", CliConfigOverrides(merged))
    elif hasattr(config_overrides, "raw_overrides"):
        try:
            config_overrides.raw_overrides = merged
        except Exception:
            object.__setattr__(inner, "config_overrides", CliConfigOverrides(merged))
    elif isinstance(config_overrides, dict):
        config_overrides["raw_overrides"] = merged
    return inner


async def run_top_cli(
    top_cli: TopCli,
    *,
    arg0_paths: Any = None,
    loader_overrides: Any = None,
    explicit_remote_endpoint: Any = None,
    run_main_fn: Callable[..., Awaitable[AppExitInfo]] = run_main,
) -> AppExitInfo:
    inner = merge_top_cli_overrides(top_cli)
    return await run_main_fn(
        inner,
        arg0_paths,
        loader_overrides,
        explicit_remote_endpoint=explicit_remote_endpoint,
    )


def handle_exit_info(
    exit_info: AppExitInfo,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    color_enabled: bool = False,
) -> int:
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    reason = exit_info.exit_reason
    if isinstance(reason, ExitReasonPayload) and reason.reason == ExitReason.FATAL:
        print(f"ERROR: {reason.message or ''}", file=err)
        return 1
    if reason == ExitReason.FATAL:
        print("ERROR: ", file=err)
        return 1
    for line in format_exit_messages(exit_info, color_enabled):
        print(line, file=out)
    return 0


def main(
    argv: Iterable[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    run_main_fn: Callable[..., Awaitable[AppExitInfo]] = run_main,
    color_enabled: bool = False,
) -> int:
    """Small Python projection of the Rust binary entry point.

    Full clap parsing lives in the top-level Python CLI parser.  This helper is
    intentionally injectable for tests and embedding.
    """

    del argv
    exit_info = asyncio.run(run_top_cli(TopCli(), run_main_fn=run_main_fn))
    return handle_exit_info(exit_info, stdout=stdout, stderr=stderr, color_enabled=color_enabled)


__all__ = [
    "CliConfigOverrides",
    "RUST_MODULE",
    "TUI_LIB_RUST_MODULE",
    "TopCli",
    "format_exit_messages",
    "handle_exit_info",
    "main",
    "merge_top_cli_overrides",
    "run_top_cli",
]
