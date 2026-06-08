from __future__ import annotations

from pycodex.app_server_protocol.apps import AppInfo
from pycodex.core.apps import render_apps_section
from pycodex.core.apps import render as apps_render
from pycodex.core.plugins import render as plugins_render
from pycodex.protocol import APPS_INSTRUCTIONS_CLOSE_TAG, APPS_INSTRUCTIONS_OPEN_TAG


def test_core_apps_render_coordinate_reexports_render_apps_section() -> None:
    # Rust source: codex/codex-rs/core/src/apps/mod.rs
    # Rust source: codex/codex-rs/core/src/apps/render.rs
    # Rust crate/module: codex-core::apps::render
    # Contract: the apps namespace exposes the render_apps_section helper.
    assert apps_render.render_apps_section is plugins_render.render_apps_section
    assert render_apps_section is plugins_render.render_apps_section


def test_core_apps_render_coordinate_preserves_apps_section_behavior() -> None:
    # Rust test: apps::render::tests::renders_apps_section_with_an_accessible_and_enabled_app
    rendered = render_apps_section(
        (AppInfo(id="calendar", name="calendar", is_accessible=True, is_enabled=True),)
    )

    assert rendered is not None
    assert rendered.startswith(APPS_INSTRUCTIONS_OPEN_TAG)
    assert "## Apps (Connectors)" in rendered
    assert rendered.endswith(APPS_INSTRUCTIONS_CLOSE_TAG)
