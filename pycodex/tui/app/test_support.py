"""Semantic port of codex-rs/tui/src/app/test_support.rs.

This Rust module mostly builds heavyweight App fixtures for sibling tests.  The
Python port provides the module-local helper behavior that can be represented
without constructing the full TUI App, and keeps heavyweight App construction as
an explicit dependency boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pycodex.protocol import SessionSource, ThreadId

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::test_support",
    source="codex/codex-rs/tui/src/app/test_support.rs",
)


@dataclass(frozen=True)
class TestSessionTelemetry:
    thread_id: ThreadId
    model: str
    model_slug: str
    account_id: str | None
    account_email: str | None
    auth_mode: str | None
    originator: str
    log_user_prompts: bool
    app_version: str
    session_source: SessionSource


async def make_test_app(*args: Any, **kwargs: Any) -> Any:
    """Heavyweight App fixture boundary from Rust.

    Rust constructs a full ``App`` via ChatWidget, FileSearchManager,
    SessionTelemetry, and many runtime states.  Python should not silently fake
    that object here; callers that need it should provide a focused fixture or a
    fuller App port.
    """

    raise NotImplementedError(
        "app::test_support.make_test_app requires full App/ChatWidget fixture construction"
    )


def test_session_telemetry(config: Any, model: str) -> TestSessionTelemetry:
    model_text = str(model)
    model_slug = _model_slug(config, model_text)
    return TestSessionTelemetry(
        thread_id=ThreadId.new(),
        model=model_text,
        model_slug=model_slug,
        account_id=None,
        account_email=None,
        auth_mode=None,
        originator="test_originator",
        log_user_prompts=False,
        app_version="test",
        session_source=SessionSource.cli(),
    )


def app_enabled_in_effective_config(config: Any, app_id: str) -> bool | None:
    stack = _get(config, "config_layer_stack")
    if stack is None:
        return None
    effective = stack.effective_config() if hasattr(stack, "effective_config") else _get(stack, "effective_config")
    table = _as_table(effective)
    apps = _as_table(_get(table, "apps"))
    app = _as_table(_get(apps, app_id))
    enabled = _get(app, "enabled")
    return enabled if isinstance(enabled, bool) else None


def _model_slug(config: Any, model: str) -> str:
    models = _get(config, "model_slugs", None)
    if isinstance(models, dict) and model in models:
        return str(models[model])
    model_info = _get(config, "model_info", None)
    slug = _get(model_info, "slug", None)
    return str(slug) if slug else model


def _as_table(value: Any) -> Any:
    if value is None:
        return {}
    if hasattr(value, "as_table"):
        table = value.as_table()
        return table if table is not None else {}
    return value if isinstance(value, dict) else {}


def _get(value: Any, key: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


__all__ = [
    "RUST_MODULE",
    "TestSessionTelemetry",
    "app_enabled_in_effective_config",
    "make_test_app",
    "test_session_telemetry",
]
