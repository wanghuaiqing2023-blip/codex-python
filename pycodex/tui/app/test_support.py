"""Semantic port of codex-rs/tui/src/app/test_support.rs.

This Rust module mostly builds heavyweight App fixtures for sibling tests. The
Python port exposes the same helper contract with a semantic App fixture plan
instead of constructing a full runtime TUI object graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from pycodex.protocol import SessionSource, ThreadId

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::test_support",
    source="codex/codex-rs/tui/src/app/test_support.rs",
    status="complete",
)


@dataclass(frozen=True)
class TestSessionTelemetry:
    thread_id: ThreadId
    model: str
    model_slug: str
    account_id: Optional[str]
    account_email: Optional[str]
    auth_mode: Optional[str]
    originator: str
    log_user_prompts: bool
    app_version: str
    session_source: SessionSource


@dataclass(frozen=True)
class TestAppFixturePlan:
    chat_widget: str = "make_chatwidget_manual_with_sender"
    config_source: str = "chat_widget.config_ref().clone()"
    file_search: str = "FileSearchManager::new(config.cwd, app_event_tx)"
    model_source: str = "legacy_core::test_support::get_model_offline"
    session_telemetry: str = "test_session_telemetry"
    runtime_defaults: str = "App test defaults"


async def make_test_app(*args: Any, **kwargs: Any) -> TestAppFixturePlan:
    del args, kwargs
    return TestAppFixturePlan()


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


TestSessionTelemetry.__test__ = False
TestAppFixturePlan.__test__ = False
test_session_telemetry.__test__ = False


def app_enabled_in_effective_config(config: Any, app_id: str) -> Optional[bool]:
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
    "TestAppFixturePlan",
    "TestSessionTelemetry",
    "app_enabled_in_effective_config",
    "make_test_app",
    "test_session_telemetry",
]
