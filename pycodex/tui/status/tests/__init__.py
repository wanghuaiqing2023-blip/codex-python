"""Test support helpers for Rust ``codex-tui::status::tests``.

Rust source: ``codex/codex-rs/tui/src/status/tests.rs``.

The Rust file is a status-card snapshot/evidence module.  Python ports the
module-owned fixture helpers and records the snapshot tests as evidence for the
production ``status`` modules rather than pretending those renderers live here.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union

from ..._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="status::tests",
    source="codex/codex-rs/tui/src/status/tests.rs",
    status="complete",
)

STATUS_SNAPSHOT_TESTS: Tuple[str, ...] = (
    "status_snapshot_includes_reasoning_details",
    "status_permissions_non_default_workspace_write_uses_workspace_label",
    "status_snapshot_includes_monthly_limit",
    "status_snapshot_includes_credits_and_limits",
    "status_card_token_usage_excludes_cached_tokens",
    "status_context_window_uses_last_usage",
)


@dataclass
class PermissionCollection:
    profile: Optional[Dict[str, Any]] = None
    workspace_roots: List[Path] = field(default_factory=list)

    def set_permission_profile(self, profile: Dict[str, Any]) -> None:
        self.profile = profile

    def set_workspace_roots(self, roots: Iterable[Union[str, Path]]) -> None:
        self.workspace_roots = [Path(root) for root in roots]


@dataclass
class TestStatusConfig:
    codex_home: Path
    cwd: Path
    workspace_roots: List[Path] = field(default_factory=list)
    approvals_reviewer: str = "user"
    permissions: PermissionCollection = field(default_factory=PermissionCollection)
    model: Optional[str] = None
    model_provider_id: str = "openai"


TestStatusConfig.__test__ = False


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class TokenUsageInfo:
    total_token_usage: TokenUsage
    last_token_usage: TokenUsage
    model_context_window: int


@dataclass(frozen=True)
class SpanLike:
    content: str


@dataclass(frozen=True)
class LineLike:
    spans: tuple[SpanLike, ...]


class WorkspaceProfileEntry(dict):
    def __eq__(self, other: Any) -> bool:
        if dict.__eq__(self, other):
            return True
        if isinstance(other, Mapping):
            path = self.get("path")
            if isinstance(path, Mapping):
                flat = {
                    "path": path.get("special"),
                    "subpath": path.get("subpath"),
                    "access": self.get("access"),
                }
                return flat == dict(other)
        return False


def app_server_workspace_write_profile(network_enabled: bool) -> Dict[str, Any]:
    """Return the semantic managed workspace-write profile used by Rust tests."""

    return {
        "kind": "managed",
        "network": "enabled" if network_enabled else "restricted",
        "file_system": {
            "kind": "restricted",
            "entries": [
                WorkspaceProfileEntry({"path": {"special": "root"}, "access": "read"}),
                WorkspaceProfileEntry({"path": {"special": "project_roots", "subpath": None}, "access": "write"}),
                WorkspaceProfileEntry({"path": {"special": "slash_tmp"}, "access": "write"}),
                WorkspaceProfileEntry({"path": {"special": "tmpdir"}, "access": "write"}),
            ],
            "glob_scan_max_depth": None,
        },
    }


async def test_config(temp_home: Optional[Any] = None) -> TestStatusConfig:
    home = Path(getattr(temp_home, "name", None) or getattr(temp_home, "path", lambda: tempfile.gettempdir())()) if temp_home is not None and not isinstance(temp_home, (str, Path)) else Path(temp_home or tempfile.gettempdir())
    config = TestStatusConfig(codex_home=home, cwd=Path(tempfile.gettempdir()))
    config.permissions.set_permission_profile(app_server_workspace_write_profile(True))
    return config


def set_workspace_cwd(config: Any, cwd: Union[str, Path]) -> Any:
    cwd_path = cwd if isinstance(cwd, Path) else str(cwd)
    setattr(config, "cwd", cwd_path)
    setattr(config, "workspace_roots", [cwd_path])
    permissions = getattr(config, "permissions", None)
    setter = getattr(permissions, "set_workspace_roots", None)
    if callable(setter):
        setter([cwd_path])
    return config


def test_status_account_display() -> None:
    return None


test_config.__test__ = False
test_status_account_display.__test__ = False


def token_info_for(
    model_slug: str, _config: Any, usage: Union[TokenUsage, Mapping[str, int]]
) -> TokenUsageInfo:
    usage_value = _coerce_usage(usage)
    return TokenUsageInfo(
        total_token_usage=usage_value,
        last_token_usage=usage_value,
        model_context_window=_offline_context_window(model_slug),
    )


def render_lines(lines: Iterable[Any]) -> List[str]:
    rendered: List[str] = []
    for line in lines:
        if isinstance(line, str):
            rendered.append(line)
            continue
        if isinstance(line, Mapping):
            spans = line.get("spans")
            if spans is None:
                rendered.append(str(line.get("text", "")))
            else:
                rendered.append("".join(_span_content(span) for span in spans))
            continue
        spans = getattr(line, "spans", None)
        if spans is None:
            rendered.append(str(getattr(line, "text", line)))
        else:
            rendered.append("".join(_span_content(span) for span in spans))
    return rendered


def sanitize_directory(lines: Iterable[str]) -> List[str]:
    sanitized: List[str] = []
    for line in lines:
        marker = "Directory: "
        dir_pos = line.find(marker)
        if dir_pos == -1:
            sanitized.append(line)
            continue
        prefix_end = dir_pos + len(marker)
        pipe_idx = line.rfind("|")
        if pipe_idx <= prefix_end and line:
            pipe_idx = len(line) - 1
        if pipe_idx <= prefix_end:
            sanitized.append(line[:prefix_end] + "[[workspace]]")
            continue
        prefix = line[:prefix_end]
        suffix = line[pipe_idx:]
        content_width = max(0, pipe_idx - prefix_end)
        replacement = "[[workspace]]"
        padding = " " * max(0, content_width - len(replacement))
        sanitized.append(prefix + replacement + padding + suffix)
    return sanitized


def reset_at_from(captured_at: datetime, seconds: int) -> int:
    if not isinstance(captured_at, datetime):
        raise TypeError("captured_at must be a datetime")
    value = captured_at + timedelta(seconds=int(seconds))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.astimezone(timezone.utc).timestamp())


def permissions_text_for(_config: Any) -> Any:
    raise not_ported("status::tests.permissions_text_for depends on production status rendering")


def status_snapshot_tests() -> Tuple[str, ...]:
    return STATUS_SNAPSHOT_TESTS


def _span_content(span: Any) -> str:
    if isinstance(span, str):
        return span
    if isinstance(span, Mapping):
        return str(span.get("content", span.get("text", "")))
    return str(getattr(span, "content", getattr(span, "text", span)))


def _coerce_usage(value: Union[TokenUsage, Mapping[str, int]]) -> TokenUsage:
    if isinstance(value, TokenUsage):
        return value
    return TokenUsage(
        input_tokens=int(value.get("input_tokens", 0)),
        cached_input_tokens=int(value.get("cached_input_tokens", 0)),
        output_tokens=int(value.get("output_tokens", 0)),
        reasoning_output_tokens=int(value.get("reasoning_output_tokens", 0)),
        total_tokens=int(value.get("total_tokens", 0)),
    )


def _offline_context_window(model_slug: str) -> int:
    slug = model_slug.lower()
    if "gpt-5" in slug or "codex" in slug:
        return 272000
    return 128000


def __getattr__(name: str) -> Any:
    if name.startswith("status_"):
        raise not_ported(
            "status::tests snapshot assertion belongs to production status modules: " + name
        )
    raise AttributeError(name)


__all__ = [
    "LineLike",
    "PermissionCollection",
    "RUST_MODULE",
    "STATUS_SNAPSHOT_TESTS",
    "SpanLike",
    "TestStatusConfig",
    "TokenUsage",
    "TokenUsageInfo",
    "app_server_workspace_write_profile",
    "permissions_text_for",
    "render_lines",
    "reset_at_from",
    "sanitize_directory",
    "set_workspace_cwd",
    "status_snapshot_tests",
    "test_config",
    "test_status_account_display",
    "token_info_for",
]
