"""Test support helpers for Rust ``codex-tui::history_cell::tests``.

Rust source: ``codex/codex-rs/tui/src/history_cell/tests.rs``.

This module is a test-only evidence module.  It does not own production
history-cell rendering behavior; those contracts live in the individual
``history_cell`` modules.  The Python port mirrors the reusable fixture helpers
that the Rust test module itself defines.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="history_cell::tests",
    source="codex/codex-rs/tui/src/history_cell/tests.rs",
)

SMALL_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="

HELPER_NAMES: tuple[str, ...] = (
    "test_config",
    "test_cwd",
    "stdio_server_config",
    "streamable_http_server_config",
    "string_map_to_toml_value",
    "render_lines",
    "render_transcript",
    "assert_unstyled_lines",
    "image_block",
    "text_block",
    "resource_link_block",
)

RENDERING_BEHAVIOR_TESTS: tuple[str, ...] = (
    "raw_lines_from_source_preserves_explicit_blank_lines",
    "source_backed_cells_render_raw_source_without_prefix_or_style",
    "proposed_plan_cell_renders_markdown_table",
    "prefixed_wrapped_history_cell_indents_wrapped_lines",
    "agent_markdown_cell_renders_source_at_different_widths",
    "consolidation_walker_replaces_agent_message_cells",
)


@dataclass(frozen=True)
class TestConfig:
    codex_home: Path


@dataclass(frozen=True)
class McpServerConfig:
    transport: str
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] | None = None
    env_vars: tuple[str, ...] = ()
    url: str | None = None
    bearer_token_env_var: str | None = None
    http_headers: dict[str, str] | None = None
    env_http_headers: dict[str, str] | None = None


@dataclass(frozen=True)
class SpanLike:
    content: str
    style: Any = None


@dataclass(frozen=True)
class LineLike:
    spans: tuple[SpanLike, ...] = ()
    style: Any = None


@dataclass(frozen=True)
class ResourceLinkBlock:
    uri: str
    name: str
    title: str | None = None
    description: str | None = None
    mime_type: str | None = None
    size: int | None = None
    icons: Any | None = None
    meta: Any | None = None


async def test_config() -> TestConfig:
    """Return a minimal semantic test config rooted at the temp directory."""

    return TestConfig(codex_home=Path(tempfile.gettempdir()))


def test_cwd() -> Path:
    """Return a stable absolute cwd, matching Rust's temp_dir fixture intent."""

    return Path(tempfile.gettempdir())


def string_map_to_toml_value(entries: Mapping[str, str]) -> dict[str, str]:
    """Semantic stand-in for a TOML table of string values."""

    return {str(key): str(value) for key, value in entries.items()}


def stdio_server_config(
    command: str,
    args: Iterable[str] = (),
    env: Mapping[str, str] | None = None,
    env_vars: Iterable[str] = (),
) -> McpServerConfig:
    return McpServerConfig(
        transport="stdio",
        command=str(command),
        args=tuple(str(arg) for arg in args),
        env=None if env is None else string_map_to_toml_value(env),
        env_vars=tuple(str(name) for name in env_vars),
    )


def streamable_http_server_config(
    url: str,
    bearer_token_env_var: str | None = None,
    http_headers: Mapping[str, str] | None = None,
    env_http_headers: Mapping[str, str] | None = None,
) -> McpServerConfig:
    return McpServerConfig(
        transport="streamable_http",
        url=str(url),
        bearer_token_env_var=bearer_token_env_var,
        http_headers=None if http_headers is None else string_map_to_toml_value(http_headers),
        env_http_headers=None if env_http_headers is None else string_map_to_toml_value(env_http_headers),
    )


def render_lines(lines: Iterable[Any]) -> list[str]:
    rendered: list[str] = []
    for line in lines:
        if isinstance(line, str):
            rendered.append(line)
            continue
        if isinstance(line, Mapping):
            if "spans" in line:
                rendered.append("".join(_span_content(span) for span in line["spans"]))
            else:
                rendered.append(str(line.get("text", "")))
            continue
        spans = getattr(line, "spans", None)
        if spans is not None:
            rendered.append("".join(_span_content(span) for span in spans))
        else:
            rendered.append(str(getattr(line, "text", line)))
    return rendered


def render_transcript(cell: Any) -> list[str]:
    transcript_lines = getattr(cell, "transcript_lines", None)
    if callable(transcript_lines):
        return render_lines(transcript_lines(65535))
    raw_lines = getattr(cell, "raw_lines", None)
    if callable(raw_lines):
        return render_lines(raw_lines())
    if isinstance(cell, Iterable) and not isinstance(cell, (str, bytes, Mapping)):
        return render_lines(cell)
    return render_lines([cell])


def assert_unstyled_lines(lines: Iterable[Any]) -> None:
    for line in lines:
        line_style = _style(line)
        if line_style not in (None, "", "default"):
            raise AssertionError(f"line has non-default style: {line_style!r}")
        spans = _spans(line)
        for span in spans:
            span_style = _style(span)
            if span_style not in (None, "", "default"):
                raise AssertionError(f"span has non-default style: {span_style!r}")


def image_block(data: str) -> dict[str, Any]:
    return {"type": "image", "data": str(data), "mimeType": "image/png"}


def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": str(text)}


def resource_link_block(
    uri: str,
    name: str,
    title: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "resource_link",
        "resource": {
            "uri": str(uri),
            "name": str(name),
            "title": title,
            "description": description,
            "mime_type": None,
            "size": None,
            "icons": None,
            "meta": None,
        },
    }


def helper_names() -> tuple[str, ...]:
    return HELPER_NAMES


def rendering_behavior_tests() -> tuple[str, ...]:
    return RENDERING_BEHAVIOR_TESTS


def _span_content(span: Any) -> str:
    if isinstance(span, str):
        return span
    if isinstance(span, Mapping):
        return str(span.get("content", span.get("text", "")))
    return str(getattr(span, "content", getattr(span, "text", span)))


def _style(value: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get("style")
    return getattr(value, "style", None)


def _spans(value: Any) -> tuple[Any, ...]:
    if isinstance(value, str):
        return ()
    if isinstance(value, Mapping):
        return tuple(value.get("spans", ()))
    return tuple(getattr(value, "spans", ()))


def __getattr__(name: str) -> Any:
    if name.startswith("test_") or name in RENDERING_BEHAVIOR_TESTS:
        raise not_ported(
            "history_cell::tests production rendering assertion belongs to the owning history_cell module: "
            + name
        )
    raise AttributeError(name)


__all__ = [
    "HELPER_NAMES",
    "LineLike",
    "McpServerConfig",
    "RENDERING_BEHAVIOR_TESTS",
    "RUST_MODULE",
    "ResourceLinkBlock",
    "SMALL_PNG_BASE64",
    "SpanLike",
    "TestConfig",
    "assert_unstyled_lines",
    "helper_names",
    "image_block",
    "render_lines",
    "render_transcript",
    "rendering_behavior_tests",
    "resource_link_block",
    "stdio_server_config",
    "streamable_http_server_config",
    "string_map_to_toml_value",
    "test_config",
    "test_cwd",
    "text_block",
]
