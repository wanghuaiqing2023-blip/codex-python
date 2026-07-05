from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pycodex.cli import parser
from pycodex.tui import TuiAppRuntime
from pycodex.tui.bottom_pane.status_line_setup import StatusLineItem
from pycodex.tui.runtime_projection import _runtime_status_line_item_ids, _runtime_status_line_value


def test_tui_root_config_overrides_reach_runtime_status_line(monkeypatch, tmp_path: Path) -> None:
    # Rust source/test contract:
    # - codex-tui/src/lib.rs parses root `-c` raw overrides before
    #   load_config_or_exit.
    # - codex-core/src/config/mod.rs projects cfg.tui.status_line into
    #   Config.tui_status_line.
    # - codex-tui/src/app.rs passes that Config into ChatWidget, and
    #   chatwidget/status_surfaces.rs reads configured_status_line_items().
    monkeypatch.setattr(parser, "find_codex_home", lambda: tmp_path)
    monkeypatch.setattr(parser, "read_toml_mapping", lambda _path: {})
    monkeypatch.setattr(parser, "read_auth_json", lambda: {})
    monkeypatch.setattr(parser, "maybe_migrate_personality", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(parser, "ensure_exec_trusted_directory", lambda _check: None)
    monkeypatch.setattr(parser, "_execpolicy_rules_for_local_http_exec", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(parser, "local_http_exec_max_tool_rounds", lambda: 4)
    monkeypatch.setattr(
        parser,
        "build_default_core_exec_runtime",
        lambda *_args, **_kwargs: (
            object(),
            SimpleNamespace(id="openai"),
            SimpleNamespace(id="gpt-test", name="gpt-test"),
            None,
        ),
    )

    parsed = parser.parse_args(
        [
            "--no-alt-screen",
            "-C",
            str(tmp_path),
            "-s",
            "read-only",
            "-a",
            "never",
            "-c",
            'tui.status_line=["model-name","context-used"]',
            "-c",
            "tui.status_line_use_colors=false",
        ]
    )

    runtime = parser._build_tui_core_active_thread_runtime(parsed, stderr=SimpleNamespace(write=lambda *_: None))
    app_runtime = TuiAppRuntime(runtime)

    assert runtime.session_config.tui_status_line == ("model-name", "context-used")
    assert runtime.session_config.tui_status_line_use_colors is False
    assert _runtime_status_line_item_ids(app_runtime) == ("model-name", "context-used")
    assert _runtime_status_line_value(app_runtime, StatusLineItem.CONTEXT_USED, "Ready") == "Context 0% used"
