"""End-to-end coverage for the Rust-owned ``/skills`` slash command.

Rust owners:
- ``chatwidget::slash_dispatch`` opens the two-action skills menu.
- ``chatwidget::skills`` routes ``OpenSkillsList`` and
  ``OpenManageSkillsPopup`` into the composer and toggle view.
- ``bottom_pane::skill_popup`` owns filtering, selection, and insertion.
- ``bottom_pane::skills_toggle_view`` owns search, toggling, and close.
- ``app::event_dispatch`` persists skill state and refreshes the skills list.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import sys
import tomllib

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_view_slash_candidate,
    slash_candidate_pair,
)
from tests.e2e.tui._common import (
    ConptyInputStep,
    SESSION_CONFIGURED_COMPOSER_PATTERN,
    TerminalSize,
    TuiComparisonCommand,
    _completed_text_response,
    _isolated_codex_home_env_with_config,
    _SseFixtureServer,
    build_rust_python_inline_pair,
    run_windows_conpty_tui_command,
)
from tests.e2e.support.responses_fixture import _responses_sse

pytestmark = pytest.mark.e2e

ROWS = 40
COLS = 140
ALPHA_SKILL = "probe-alpha"
BETA_SKILL = "probe-beta"
ALPHA_BODY_MARKER = "SKILLS_ALPHA_BODY_MARKER_20260804"
BETA_BODY_MARKER = "SKILLS_BETA_BODY_MARKER_20260804"
ALPHA_PLUGIN_ID = "alpha-workflows@openai-curated"
BETA_PLUGIN_ID = "beta-tools@openai-curated"
ALPHA_PLUGIN_NAME = "Alpha Workflows"
BETA_PLUGIN_NAME = "Beta Tools"
ALPHA_PLUGIN_DESCRIPTION = "Run deterministic alpha workflows."
BETA_PLUGIN_DESCRIPTION = "Use deterministic beta tools."
ALPHA_PLUGIN_SKILL_DISPLAY = "alpha-workflows-skill (al..."
MENU_MARKERS = (
    "Skills",
    "Choose an action",
    "List skills",
    "Tip: press $ to open this list directly.",
    "Enable/Disable Skills",
    "Enable or disable skills.",
)
OPENAI_DOCS_SKILL = "openai-docs"
OPENAI_DOCS_QUERY = "Responses API function calling"
OPENAI_DOCS_RESULT_MARKER = "OPENAI_DOCS_E2E_RESULT"
PDF_SKILL = "pdf:pdf"
PDF_ARTIFACT_NAME = "pdf-skill-e2e.pdf"
PDF_ARTIFACT_MARKER = "PDF_SKILL_E2E_ARTIFACT"


def _skills_config(base_url: str, label: str, *, plugins: bool = False) -> str:
    project = str(Path.cwd().resolve(strict=False)).lower()
    return (
        'model = "mock-model"\n'
        'model_provider = "pycodex_mock"\n'
        'approval_policy = "never"\n'
        'sandbox_mode = "read-only"\n'
        'suppress_unstable_features_warning = true\n\n'
        '[features]\n'
        'apps = false\n'
        f'plugins = {str(bool(plugins)).lower()}\n'
        'mentions_v2 = false\n\n'
        '[model_providers.pycodex_mock]\n'
        f'name = "Mock provider for /skills {label}"\n'
        f'base_url = "{base_url}"\n'
        'wire_api = "responses"\n'
        'requires_openai_auth = false\n'
        'request_max_retries = 0\n'
        'stream_max_retries = 0\n'
        'supports_websockets = false\n\n'
        f"[projects.'{project}']\n"
        'trust_level = "trusted"\n'
        + (
            '\n[plugins."alpha-workflows@openai-curated"]\n'
            'enabled = true\n\n'
            '[plugins."beta-tools@openai-curated"]\n'
            'enabled = true\n'
            if plugins
            else ""
        )
    )


def _skill_execution_config(
    base_url: str,
    label: str,
    *,
    docs_call_log: Path | None = None,
    pdf_plugin: bool = False,
) -> str:
    repo_root = Path(__file__).resolve().parents[3]
    config = (
        'model = "mock-model"\n'
        'model_provider = "pycodex_mock"\n'
        'approval_policy = "never"\n'
        'sandbox_mode = "danger-full-access"\n'
        'suppress_unstable_features_warning = true\n\n'
        '[features]\n'
        'apps = false\n'
        f'plugins = {str(pdf_plugin).lower()}\n'
        'mentions_v2 = false\n\n'
        'unified_exec = true\n'
        'skill_mcp_dependency_install = false\n\n'
        '[model_providers.pycodex_mock]\n'
        f'name = "Mock provider for {label} skill execution"\n'
        f'base_url = "{base_url}"\n'
        'wire_api = "responses"\n'
        'requires_openai_auth = false\n'
        'request_max_retries = 0\n'
        'stream_max_retries = 0\n'
        'supports_websockets = false\n\n'
    )
    if docs_call_log is not None:
        server_env = ", ".join(
            (
                'PYCODEX_TEST_MCP_PROFILE = "openai_docs"',
                "PYCODEX_TEST_MCP_CALL_LOG = " + json.dumps(str(docs_call_log)),
            )
        )
        config += (
            '[mcp_servers.openaiDeveloperDocs]\n'
            f'command = {json.dumps(sys.executable)}\n'
            'args = ["-B", "-m", "pycodex.rmcp_client.bin.test_stdio_server"]\n'
            f'cwd = {json.dumps(str(repo_root))}\n'
            f'env = {{ {server_env} }}\n'
            'startup_timeout_sec = 120\n'
            'required = true\n\n'
        )
    if pdf_plugin:
        config += (
            '[plugins."pdf@openai-primary-runtime"]\n'
            'enabled = true\n\n'
        )
    return (
        config
        + f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
        + 'trust_level = "trusted"\n'
    )


def _function_call_response(
    *,
    response_id: str,
    item_id: str,
    call_id: str,
    name: str,
    arguments: dict[str, object],
    namespace: str | None = None,
) -> bytes:
    item: dict[str, object] = {
        "id": item_id,
        "type": "function_call",
        "call_id": call_id,
        "name": name,
        "arguments": json.dumps(arguments, separators=(",", ":")),
    }
    if namespace is not None:
        item["namespace"] = namespace
    return _responses_sse(
        {"type": "response.created", "response": {"id": response_id}},
        {"type": "response.output_item.done", "item": item},
        {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 1,
                    "output_tokens_details": None,
                    "total_tokens": 2,
                },
            },
        },
    )


def _write_skill(codex_home: Path, name: str, description: str, marker: str) -> Path:
    path = codex_home / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "---\n\n"
        f"When this skill is selected, preserve the marker {marker}.\n",
        encoding="utf-8",
    )
    return path


def _seed_skills(codex_home: Path) -> tuple[Path, Path]:
    return (
        _write_skill(
            codex_home,
            ALPHA_SKILL,
            "Alpha deterministic E2E workflow.",
            ALPHA_BODY_MARKER,
        ),
        _write_skill(
            codex_home,
            BETA_SKILL,
            "Beta deterministic E2E workflow.",
            BETA_BODY_MARKER,
        ),
    )


def _write_plugin_fixture(
    root: Path,
    *,
    plugin_name: str,
    display_name: str,
    description: str,
) -> Path:
    plugin_root = root / "plugins" / plugin_name
    manifest = plugin_root / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "name": plugin_name,
                "version": "1.0.0",
                "description": description,
                "interface": {
                    "displayName": display_name,
                    "shortDescription": description,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    skill = plugin_root / "skills" / f"{plugin_name}-skill" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(
        "---\n"
        f"name: {plugin_name}-skill\n"
        f"description: Skill owned by {display_name}.\n"
        "---\n\n"
        f"Selected through plugin {plugin_name}.\n",
        encoding="utf-8",
    )
    return plugin_root


def _seed_plugins(codex_home: Path) -> None:
    marketplace_root = codex_home / ".tmp" / "plugins"
    plugins = (
        (
            "alpha-workflows",
            ALPHA_PLUGIN_NAME,
            ALPHA_PLUGIN_DESCRIPTION,
        ),
        (
            "beta-tools",
            BETA_PLUGIN_NAME,
            BETA_PLUGIN_DESCRIPTION,
        ),
    )
    marketplace_entries = []
    for plugin_name, display_name, description in plugins:
        source = _write_plugin_fixture(
            marketplace_root,
            plugin_name=plugin_name,
            display_name=display_name,
            description=description,
        )
        marketplace_entries.append(
            {"name": plugin_name, "source": {"source": "local", "path": f"./plugins/{plugin_name}"}}
        )
        cache = codex_home / "plugins" / "cache" / "openai-curated" / plugin_name / "local"
        cache.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, cache)
    marketplace_manifest = marketplace_root / ".agents" / "plugins" / "marketplace.json"
    marketplace_manifest.parent.mkdir(parents=True, exist_ok=True)
    marketplace_manifest.write_text(
        json.dumps(
            {"name": "openai-curated", "plugins": marketplace_entries},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    sha = codex_home / ".tmp" / "plugins.sha"
    sha.parent.mkdir(parents=True, exist_ok=True)
    sha.write_text("0123456789abcdef0123456789abcdef01234567\n", encoding="utf-8")


def _installed_pdf_plugin() -> Path:
    versions_root = Path.home() / ".codex" / "plugins" / "cache" / "openai-primary-runtime" / "pdf"
    candidates = sorted(
        (
            path
            for path in versions_root.iterdir()
            if (path / ".codex-plugin" / "plugin.json").is_file()
            and (path / "skills" / "pdf" / "SKILL.md").is_file()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ) if versions_root.is_dir() else []
    if not candidates:
        pytest.skip(
            "the installed pdf@openai-primary-runtime plugin is required for this E2E"
        )
    return candidates[0]


def _seed_installed_pdf_plugin(codex_home: Path) -> Path:
    source = _installed_pdf_plugin()
    marketplace_root = codex_home / ".tmp" / "plugins"
    marketplace_plugin = marketplace_root / "plugins" / "pdf"
    marketplace_plugin.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, marketplace_plugin)

    marketplace_manifest = marketplace_root / ".agents" / "plugins" / "marketplace.json"
    marketplace_manifest.parent.mkdir(parents=True, exist_ok=True)
    marketplace_manifest.write_text(
        json.dumps(
            {
                "name": "openai-primary-runtime",
                "plugins": [
                    {
                        "name": "pdf",
                        "source": {"source": "local", "path": "./plugins/pdf"},
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    cache = codex_home / "plugins" / "cache" / "openai-primary-runtime" / "pdf" / "local"
    cache.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, cache)
    sha = codex_home / ".tmp" / "plugins.sha"
    sha.parent.mkdir(parents=True, exist_ok=True)
    sha.write_text("fedcba9876543210fedcba9876543210fedcba98\n", encoding="utf-8")
    return cache / "skills" / "pdf" / "SKILL.md"


def _style_signature(style: object) -> tuple[object, ...]:
    def color_signature(color: object | None) -> tuple[object, object] | None:
        if color is None:
            return None
        return (getattr(color, "kind", None), getattr(color, "value", None))

    return (
        color_signature(getattr(style, "fg", None)),
        color_signature(getattr(style, "bg", None)),
        bool(getattr(style, "bold", False)),
        bool(getattr(style, "dim", False)),
        bool(getattr(style, "italic", False)),
        bool(getattr(style, "underline", False)),
        bool(getattr(style, "reverse", False)),
    )


def _token_styles(transcript, checkpoint: str, token: str) -> tuple[tuple[object, ...], ...]:
    screen = transcript.checkpoint_cells(checkpoint, rows=ROWS, cols=COLS)
    for row in screen.rows:
        text = "".join(cell.char for cell in row)
        start = text.find(token)
        if start >= 0:
            return tuple(
                _style_signature(row[index].style)
                for index in range(start, start + len(token))
            )
    raise AssertionError(f"{token!r} missing from checkpoint {checkpoint!r}")


def _row_contract(
    transcript,
    checkpoint: str,
    token: str,
    *,
    rows: int = ROWS,
    cols: int = COLS,
) -> tuple[str, tuple[tuple[object, ...], ...]]:
    screen = transcript.checkpoint_cells(checkpoint, rows=rows, cols=cols)
    for row in screen.rows:
        text = "".join(cell.char for cell in row).rstrip()
        if token not in text:
            continue
        start = len(text) - len(text.lstrip())
        return (
            text[start:],
            tuple(_style_signature(cell.style) for cell in row[start : len(text)]),
        )
    raise AssertionError(f"{token!r} missing from checkpoint {checkpoint!r}")


def _candidate_row_contracts(
    transcript,
    checkpoint: str,
    *,
    rows: int = ROWS,
    cols: int = COLS,
) -> tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]:
    screen = transcript.checkpoint_cells(checkpoint, rows=rows, cols=cols)
    candidates = []
    for row in screen.rows:
        text = "".join(cell.char for cell in row).rstrip()
        if "[Plugin]" not in text and "[Skill]" not in text:
            continue
        start = len(text) - len(text.lstrip())
        candidates.append(
            (
                text[start:],
                tuple(_style_signature(cell.style) for cell in row[start : len(text)]),
            )
        )
    return tuple(candidates)


def _run_plugin_skill_catalog(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
    rows: int = ROWS,
    cols: int = COLS,
):
    fixture = _completed_text_response(
        f"resp-{label}-plugin-catalog-unused",
        f"msg-{label}-plugin-catalog-unused",
        "PLUGIN_CATALOG_MUST_NOT_REACH_MODEL",
    )
    with _SseFixtureServer(fixture) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _skills_config(server.base_url, label, plugins=True)
        )
        with temp_home:
            codex_home = Path(env["CODEX_HOME"])
            _seed_skills(codex_home)
            _seed_plugins(codex_home)
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "/skills",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=1.0,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\x1b",
                        ready_screen_text="/skills",
                        ready_timeout=10.0,
                        ready_quiet_period=0.5,
                    ),
                    ConptyInputStep("\r", ready_timeout=0.5),
                    ConptyInputStep(
                        "\r",
                        ready_text_sequence=MENU_MARKERS,
                        ready_timeout=15.0,
                        ready_quiet_period=0.3,
                    ),
                    ConptyInputStep(
                        "alpha",
                        ready_screen_text=ALPHA_PLUGIN_NAME,
                        ready_timeout=20.0,
                        ready_quiet_period=0.5,
                        capture_name="plugin-catalog",
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\x1b",
                        ready_timeout=1.0,
                        capture_name="plugin-filtered",
                    ),
                    ConptyInputStep(
                        "",
                        ready_timeout=1.0,
                        capture_name="plugin-escaped",
                    ),
                ),
                env=env,
                timeout=2,
                size=TerminalSize(rows=rows, cols=cols),
            )
        requests = list(server.request_bodies)
    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-plugin-skill-catalog-{cols}x{rows}",
        rows=rows,
        cols=cols,
    )
    return transcript, requests


def _run_plugin_selection(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
):
    response_marker = f"PLUGIN_SELECTION_RESPONSE_{label.upper()}"
    fixture = _completed_text_response(
        f"resp-{label}-plugin-selection",
        f"msg-{label}-plugin-selection",
        response_marker,
    )
    with _SseFixtureServer(fixture) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _skills_config(server.base_url, label, plugins=True)
        )
        with temp_home:
            codex_home = Path(env["CODEX_HOME"])
            _seed_skills(codex_home)
            _seed_plugins(codex_home)
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "/skills",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=1.0,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\x1b",
                        ready_screen_text="/skills",
                        ready_timeout=10.0,
                        ready_quiet_period=0.5,
                    ),
                    ConptyInputStep("\r", ready_timeout=0.5),
                    ConptyInputStep(
                        "\r",
                        ready_text_sequence=MENU_MARKERS,
                        ready_timeout=15.0,
                        ready_quiet_period=0.3,
                    ),
                    ConptyInputStep(
                        "alpha",
                        ready_screen_text=ALPHA_PLUGIN_NAME,
                        ready_timeout=20.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep("\r", ready_timeout=1.0, capture_name="plugin-filtered"),
                    ConptyInputStep(
                        "execute plugin reference",
                        ready_screen_text="$alpha-workflows",
                        ready_timeout=10.0,
                        ready_quiet_period=0.3,
                        capture_name="plugin-selected",
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="execute plugin reference",
                        ready_timeout=10.0,
                        ready_quiet_period=0.3,
                        capture_name="plugin-draft",
                    ),
                ),
                env=env,
                timeout=4,
                stop_pattern=response_marker,
                stop_timeout=30,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
        requests = list(server.request_bodies)
    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-plugin-selection",
        rows=ROWS,
        cols=COLS,
    )
    return transcript, requests


def _run_skills_list_selection(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
):
    response_marker = f"SKILLS_SELECTION_RESPONSE_{label.upper()}"
    fixture = _completed_text_response(
        f"resp-{label}-skills-selection",
        f"msg-{label}-skills-selection",
        response_marker,
    )
    with _SseFixtureServer(fixture) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _skills_config(server.base_url, label)
        )
        with temp_home:
            _seed_skills(Path(env["CODEX_HOME"]))
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "/skills",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=1.0,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/skills",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    # The first row is List skills. Enter must dispatch the
                    # Rust OpenSkillsList event after the menu is popped.
                    ConptyInputStep(
                        "\r",
                        ready_text_sequence=MENU_MARKERS,
                        ready_timeout=15.0,
                        ready_quiet_period=0.3,
                        capture_name="skills-menu",
                    ),
                    ConptyInputStep(
                        "probe",
                        ready_screen_pattern=r"(?m)^.*\$\s*$",
                        ready_timeout=15.0,
                        ready_quiet_period=0.3,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\x1b[B",
                        ready_screen_text=ALPHA_SKILL,
                        ready_timeout=15.0,
                        ready_quiet_period=0.4,
                        capture_name="filtered",
                    ),
                    ConptyInputStep(
                        "\x1b[A",
                        ready_screen_text=BETA_SKILL,
                        ready_timeout=10.0,
                        ready_quiet_period=0.3,
                        capture_name="moved-down",
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text=ALPHA_SKILL,
                        ready_timeout=10.0,
                        ready_quiet_period=0.3,
                        capture_name="moved-up",
                    ),
                    ConptyInputStep(
                        " execute the selected skill",
                        ready_screen_pattern=rf"(?m)^.*\${ALPHA_SKILL}\s*$",
                        ready_timeout=10.0,
                        ready_quiet_period=0.3,
                        capture_name="selected-skill",
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="execute the selected skill",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                ),
                env=env,
                timeout=4,
                stop_pattern=response_marker,
                stop_timeout=30,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
        requests = list(server.request_bodies)
    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-skills-list-selection",
        rows=ROWS,
        cols=COLS,
    )
    return transcript, requests


def _run_openai_docs_skill_execution(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
):
    response_marker = f"OPENAI_DOCS_SKILL_COMPLETE_{label.upper()}"
    tool_response = _function_call_response(
        response_id=f"resp-{label}-openai-docs-tool",
        item_id=f"fc-{label}-openai-docs-tool",
        call_id=f"call-{label}-openai-docs-tool",
        namespace="mcp__openaiDeveloperDocs",
        name="search_openai_docs",
        arguments={"query": OPENAI_DOCS_QUERY},
    )
    final_response = _completed_text_response(
        f"resp-{label}-openai-docs-final",
        f"msg-{label}-openai-docs-final",
        response_marker,
    )
    with _SseFixtureServer((tool_response, final_response)) as server:
        env, temp_home = _isolated_codex_home_env_with_config("")
        with temp_home:
            codex_home = Path(env["CODEX_HOME"])
            call_log = codex_home / "openai-docs-mcp-calls.jsonl"
            (codex_home / "config.toml").write_text(
                _skill_execution_config(
                    server.base_url,
                    label,
                    docs_call_log=call_log,
                ),
                encoding="utf-8",
            )
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "/skills",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=40.0,
                        ready_quiet_period=1.0,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/skills",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_text_sequence=MENU_MARKERS,
                        ready_timeout=15.0,
                        ready_quiet_period=0.3,
                    ),
                    ConptyInputStep(
                        OPENAI_DOCS_SKILL,
                        ready_screen_pattern=r"(?i)openai(?:-|\s+)docs",
                        ready_timeout=20.0,
                        ready_quiet_period=0.4,
                        atomic_write=True,
                    ),
                    ConptyInputStep("\r", ready_timeout=1.0),
                    ConptyInputStep(
                        " explain Responses API function calling",
                        ready_screen_text=f"${OPENAI_DOCS_SKILL}",
                        ready_timeout=10.0,
                        ready_quiet_period=0.3,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="explain Responses API function calling",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                ),
                env=env,
                timeout=5,
                stop_pattern=response_marker,
                stop_timeout=45,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
            calls = (
                tuple(json.loads(line) for line in call_log.read_text(encoding="utf-8").splitlines())
                if call_log.exists()
                else ()
            )
        requests = tuple(server.request_bodies)
    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-openai-docs-skill-execution",
        rows=ROWS,
        cols=COLS,
    )
    return transcript, requests, calls


def _minimal_pdf_bytes() -> bytes:
    stream = b"BT /F1 18 Tf 72 720 Td (PDF_SKILL_E2E_ARTIFACT) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)


def _pdf_generation_command(target: Path) -> str:
    target_literal = str(target).replace("'", "''")
    payload = base64.b64encode(_minimal_pdf_bytes()).decode("ascii")
    script = (
        f"$target='{target_literal}'; "
        "$parent=[IO.Path]::GetDirectoryName($target); "
        "[IO.Directory]::CreateDirectory($parent) | Out-Null; "
        f"[IO.File]::WriteAllBytes($target,[Convert]::FromBase64String('{payload}')); "
        "Write-Output $target"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return f"powershell.exe -NoLogo -NoProfile -NonInteractive -EncodedCommand {encoded}"


def _run_pdf_skill_execution(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
):
    response_marker = f"PDF_SKILL_COMPLETE_{label.upper()}"
    artifact = artifact_dir / f"{label}-{PDF_ARTIFACT_NAME}"
    tool_response = _function_call_response(
        response_id=f"resp-{label}-pdf-tool",
        item_id=f"fc-{label}-pdf-tool",
        call_id=f"call-{label}-pdf-tool",
        name="exec_command",
        arguments={"cmd": _pdf_generation_command(artifact)},
    )
    final_response = _completed_text_response(
        f"resp-{label}-pdf-final",
        f"msg-{label}-pdf-final",
        response_marker,
    )
    with _SseFixtureServer((tool_response, final_response)) as server:
        env, temp_home = _isolated_codex_home_env_with_config("")
        with temp_home:
            codex_home = Path(env["CODEX_HOME"])
            (codex_home / "config.toml").write_text(
                _skill_execution_config(server.base_url, label, pdf_plugin=True),
                encoding="utf-8",
            )
            skill_path = _seed_installed_pdf_plugin(codex_home)
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "/skills",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=40.0,
                        ready_quiet_period=1.0,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/skills",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_text_sequence=MENU_MARKERS,
                        ready_timeout=15.0,
                        ready_quiet_period=0.3,
                    ),
                    ConptyInputStep(
                        PDF_SKILL,
                        ready_screen_text="PDF",
                        ready_timeout=20.0,
                        ready_quiet_period=0.4,
                        atomic_write=True,
                    ),
                    ConptyInputStep("\r", ready_timeout=1.0),
                    ConptyInputStep(
                        " create a one-page PDF smoke artifact",
                        ready_screen_text=f"${PDF_SKILL}",
                        ready_timeout=10.0,
                        ready_quiet_period=0.3,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="create a one-page PDF smoke artifact",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                ),
                env=env,
                timeout=8,
                stop_pattern=response_marker,
                stop_timeout=45,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
            artifact_bytes = artifact.read_bytes() if artifact.exists() else b""
            skill_body = skill_path.read_text(encoding="utf-8")
        requests = tuple(server.request_bodies)
    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-pdf-skill-execution",
        rows=ROWS,
        cols=COLS,
    )
    return transcript, requests, artifact_bytes, skill_body


def _run_pdf_skill_view_image_execution(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
):
    response_marker = f"PDF_VIEW_IMAGE_COMPLETE_{label.upper()}"
    image_path = artifact_dir / f"{label}-pdf-render-preview.png"
    image_path.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/"
            "iZk9HQAAAABJRU5ErkJggg=="
        )
    )
    tool_response = _function_call_response(
        response_id=f"resp-{label}-pdf-view-image-tool",
        item_id=f"fc-{label}-pdf-view-image-tool",
        call_id=f"call-{label}-pdf-view-image-tool",
        name="view_image",
        arguments={"path": str(image_path)},
    )
    final_response = _completed_text_response(
        f"resp-{label}-pdf-view-image-final",
        f"msg-{label}-pdf-view-image-final",
        response_marker,
    )
    with _SseFixtureServer((tool_response, final_response)) as server:
        env, temp_home = _isolated_codex_home_env_with_config("")
        with temp_home:
            codex_home = Path(env["CODEX_HOME"])
            (codex_home / "config.toml").write_text(
                _skill_execution_config(server.base_url, label, pdf_plugin=True),
                encoding="utf-8",
            )
            _seed_installed_pdf_plugin(codex_home)
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        f"${PDF_SKILL} inspect the rendered PDF page preview",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=40.0,
                        ready_quiet_period=1.0,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="inspect the rendered PDF page preview",
                        ready_timeout=10.0,
                    ),
                ),
                env=env,
                timeout=5,
                stop_pattern=(
                    rf"{response_marker}|"
                    r"replay target does not implement on_view_image_tool_call\(\)"
                ),
                stop_timeout=45,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
        requests = tuple(server.request_bodies)
    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-pdf-skill-view-image",
        rows=ROWS,
        cols=COLS,
    )
    return transcript, requests, image_path


def _run_manage_skills_toggle(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
):
    fixture = _completed_text_response(
        f"resp-{label}-skills-manage-unused",
        f"msg-{label}-skills-manage-unused",
        "SKILLS_MANAGE_MUST_NOT_REACH_MODEL",
    )
    with _SseFixtureServer(fixture) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _skills_config(server.base_url, label)
        )
        with temp_home:
            alpha_path, _beta_path = _seed_skills(Path(env["CODEX_HOME"]))
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "/skills",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=1.0,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\x1b",
                        ready_screen_text="/skills",
                        ready_timeout=10.0,
                        ready_quiet_period=0.5,
                    ),
                    ConptyInputStep("\r", ready_timeout=0.5),
                    ConptyInputStep(
                        "\x1b[B",
                        ready_text_sequence=MENU_MARKERS,
                        ready_timeout=15.0,
                        ready_quiet_period=0.3,
                    ),
                    ConptyInputStep("\r", ready_timeout=0.4),
                    ConptyInputStep(
                        "alpha",
                        ready_text_sequence=(
                            "Enable/Disable Skills",
                            "Turn skills on or off. Your changes are saved automatically.",
                            "Type to search skills",
                            ALPHA_SKILL,
                            BETA_SKILL,
                        ),
                        ready_timeout=15.0,
                        ready_quiet_period=0.4,
                        capture_name="manage-open",
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        " ",
                        ready_screen_pattern=rf"(?m)^.*>\s*alpha\s*$",
                        ready_timeout=10.0,
                        ready_quiet_period=0.3,
                        capture_name="manage-filtered",
                    ),
                    ConptyInputStep(
                        "\x1b",
                        ready_screen_pattern=rf"(?m)^.*\[ \]\s+{ALPHA_SKILL}.*$",
                        ready_timeout=10.0,
                        ready_quiet_period=0.3,
                        capture_name="manage-disabled",
                    ),
                    ConptyInputStep(
                        "/skills",
                        ready_screen_text="0 skills enabled, 1 skills disabled",
                        ready_timeout=15.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\x1b",
                        ready_screen_text="/skills",
                        ready_timeout=10.0,
                        ready_quiet_period=0.5,
                    ),
                    ConptyInputStep("\r", ready_timeout=0.5),
                    ConptyInputStep(
                        "\x1b[B",
                        ready_text_sequence=MENU_MARKERS,
                        ready_timeout=15.0,
                        ready_quiet_period=0.3,
                    ),
                    ConptyInputStep("\r", ready_timeout=0.4),
                    ConptyInputStep(
                        "alpha",
                        ready_screen_text="Type to search skills",
                        ready_timeout=15.0,
                        ready_quiet_period=0.4,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\x1b",
                        ready_screen_pattern=rf"(?m)^.*\[ \]\s+{ALPHA_SKILL}.*$",
                        ready_timeout=10.0,
                        ready_quiet_period=0.3,
                        capture_name="manage-reopened-disabled",
                    ),
                    ConptyInputStep("/quit", ready_timeout=0.5, atomic_write=True),
                    ConptyInputStep("\r", ready_screen_text="/quit", ready_timeout=10.0),
                ),
                env=env,
                timeout=5,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
            persisted_config = Path(env["CODEX_HOME"]) / "config.toml"
            config_text = persisted_config.read_text(encoding="utf-8")
        requests = list(server.request_bodies)
    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-skills-manage-toggle",
        rows=ROWS,
        cols=COLS,
    )
    return transcript, requests, config_text, alpha_path


def _run_skills_list_escape(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
):
    fixture = _completed_text_response(
        f"resp-{label}-skills-escape-unused",
        f"msg-{label}-skills-escape-unused",
        "SKILLS_ESCAPE_MUST_NOT_REACH_MODEL",
    )
    with _SseFixtureServer(fixture) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _skills_config(server.base_url, label)
        )
        with temp_home:
            _seed_skills(Path(env["CODEX_HOME"]))
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "/skills",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=1.0,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\x1b",
                        ready_screen_text="/skills",
                        ready_timeout=10.0,
                        ready_quiet_period=0.5,
                    ),
                    ConptyInputStep("\r", ready_timeout=0.5),
                    ConptyInputStep(
                        "\r",
                        ready_text_sequence=MENU_MARKERS,
                        ready_timeout=15.0,
                        ready_quiet_period=0.3,
                    ),
                    ConptyInputStep(
                        "probe",
                        ready_screen_pattern=r"(?m)^.*\$\s*$",
                        ready_timeout=15.0,
                        ready_quiet_period=0.3,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\x1b",
                        ready_screen_text=ALPHA_SKILL,
                        ready_timeout=15.0,
                        ready_quiet_period=0.4,
                        capture_name="popup-before-escape",
                    ),
                    ConptyInputStep(
                        "",
                        ready_screen_pattern=r"(?m)^.*\$probe\s*$",
                        ready_timeout=10.0,
                        ready_quiet_period=0.5,
                        capture_name="popup-escaped",
                    ),
                ),
                env=env,
                timeout=2,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
        requests = list(server.request_bodies)
    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-skills-list-escape",
        rows=ROWS,
        cols=COLS,
    )
    return transcript, requests


def test_skills_registry_contract() -> None:
    # Rust owners:
    # - slash_dispatch delegates /skills to chatwidget::skills.
    # - chatwidget::skills builds the action menu and its AppEvents.
    # - selected management actions route through active BottomPaneView state.
    route = terminal_slash_command_routes()[SlashCommand.SKILLS]

    assert SlashCommand.SKILLS.command() == "skills"
    assert SlashCommand.SKILLS.supports_inline_args() is False
    assert SlashCommand.SKILLS.available_during_task() is True
    assert SlashCommand.SKILLS.available_in_side_conversation() is False
    assert route.outcome == "view"
    assert route.python_owner == "pycodex.tui.chatwidget.skills"


def test_windows_conpty_native_and_python_skills_menu_is_local(tmp_path: Path) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_view_slash_candidate(
            command,
            label=label,
            slash_text="/skills",
            view_markers=MENU_MARKERS,
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        assert request_count == 0, (
            f"{label} unexpectedly sent a model request\n"
            f"stdout={output}\n"
            f"stderr={transcript.normalized_stderr()}"
        )
        assert MENU_MARKERS in transcript.observed_ready_sequences
        assert "VIEW_SLASH_MUST_NOT_REACH_THE_MODEL" not in output
        assert "extension area is not enabled" not in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_skills_catalog_has_complete_plugin_and_skill_rows(
    tmp_path: Path,
) -> None:
    """Compare the real empty-``$`` plugin/skill catalog, not token fragments."""

    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe, disable_plugins=False)
    results = {
        label: _run_plugin_skill_catalog(command, label=label, artifact_dir=tmp_path)
        for label, command in (("rust", rust), ("python", python))
    }

    for label, (transcript, requests) in results.items():
        screen = transcript.checkpoint_screen("plugin-catalog", rows=ROWS, cols=COLS)
        assert requests == [], f"{label} catalog unexpectedly called the model: {requests!r}"
        assert ALPHA_PLUGIN_NAME in screen
        assert BETA_PLUGIN_NAME in screen
        assert f"[Plugin] {ALPHA_PLUGIN_DESCRIPTION}" in screen
        assert f"[Plugin] {BETA_PLUGIN_DESCRIPTION}" in screen
        assert "alpha-workflows@openai-curated" not in screen
        assert "beta-tools@openai-curated" not in screen
        assert "[Skill] [Skill]" not in screen
        assert not any(line.lstrip().startswith(">") for line in screen.splitlines())
        filtered = transcript.checkpoint_screen("plugin-filtered", rows=ROWS, cols=COLS)
        assert ALPHA_PLUGIN_NAME in filtered
        assert BETA_PLUGIN_NAME not in filtered
        escaped = transcript.checkpoint_screen("plugin-escaped", rows=ROWS, cols=COLS)
        assert "$alpha" in escaped
        assert ALPHA_PLUGIN_NAME not in escaped

    for token in (ALPHA_PLUGIN_NAME, BETA_PLUGIN_NAME):
        rust_row = _row_contract(results["rust"][0], "plugin-catalog", token)
        python_row = _row_contract(results["python"][0], "plugin-catalog", token)
        assert python_row == rust_row, f"complete row/style mismatch for {token}: {python_row!r} != {rust_row!r}"

    # Querying ``alpha`` creates a deterministic three-row catalog spanning
    # all three Rust-owned source classes: plugin capability, plugin-owned
    # skill, and user skill. Compare every character and style, not fragments.
    for token in (ALPHA_PLUGIN_NAME, ALPHA_PLUGIN_SKILL_DISPLAY, ALPHA_SKILL):
        rust_row = _row_contract(results["rust"][0], "plugin-filtered", token)
        python_row = _row_contract(results["python"][0], "plugin-filtered", token)
        assert python_row == rust_row, (
            f"filtered complete row/style mismatch for {token}: "
            f"{python_row!r} != {rust_row!r}"
        )
    rust_candidates = _candidate_row_contracts(results["rust"][0], "plugin-filtered")
    python_candidates = _candidate_row_contracts(results["python"][0], "plugin-filtered")
    assert len(rust_candidates) == len(python_candidates) == 3
    assert python_candidates == rust_candidates
    assert _row_contract(
        results["python"][0], "plugin-filtered", "Press enter to insert"
    ) == _row_contract(
        results["rust"][0], "plugin-filtered", "Press enter to insert"
    )


def test_windows_conpty_native_and_python_skills_catalog_matches_at_narrow_width(
    tmp_path: Path,
) -> None:
    """The complete deterministic catalog also matches at 80 columns."""

    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe, disable_plugins=False)
    rows, cols = 35, 80
    results = {
        label: _run_plugin_skill_catalog(
            command,
            label=f"{label}-narrow",
            artifact_dir=tmp_path,
            rows=rows,
            cols=cols,
        )
        for label, command in (("rust", rust), ("python", python))
    }

    for label, (transcript, requests) in results.items():
        assert requests == [], f"{label} narrow catalog called model: {requests!r}"
        screen = transcript.checkpoint_screen("plugin-filtered", rows=rows, cols=cols)
        assert "$alpha" in screen
        assert ALPHA_PLUGIN_NAME in screen
        assert ALPHA_SKILL in screen
    for token in (ALPHA_PLUGIN_NAME, ALPHA_PLUGIN_SKILL_DISPLAY, ALPHA_SKILL):
        assert _row_contract(
            results["python"][0],
            "plugin-filtered",
            token,
            rows=rows,
            cols=cols,
        ) == _row_contract(
            results["rust"][0],
            "plugin-filtered",
            token,
            rows=rows,
            cols=cols,
        )
    assert _candidate_row_contracts(
        results["python"][0],
        "plugin-filtered",
        rows=rows,
        cols=cols,
    ) == _candidate_row_contracts(
        results["rust"][0],
        "plugin-filtered",
        rows=rows,
        cols=cols,
    )


def test_windows_conpty_native_and_python_skills_plugin_selection_submits_exact_reference(
    tmp_path: Path,
) -> None:
    """A selected Plugin is an atomic bound mention, not merely typed text."""

    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe, disable_plugins=False)
    results = {
        label: _run_plugin_selection(command, label=label, artifact_dir=tmp_path)
        for label, command in (("rust", rust), ("python", python))
    }
    for label, (transcript, requests) in results.items():
        output = transcript.normalized_stdout()
        assert f"PLUGIN_SELECTION_RESPONSE_{label.upper()}" in output
        assert len(requests) == 1, f"{label} requests={requests!r}"
        request_text = (
            requests[0].decode("utf-8")
            if isinstance(requests[0], bytes)
            else json.dumps(requests[0], ensure_ascii=False, sort_keys=True)
        )
        assert "$alpha-workflows execute plugin reference" in request_text
        assert ALPHA_PLUGIN_NAME in request_text
        assert "Capabilities from the `Alpha Workflows` plugin" in request_text
        assert BETA_PLUGIN_ID not in request_text
        assert '"/skills"' not in request_text
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()

    assert _row_contract(results["python"][0], "plugin-filtered", ALPHA_PLUGIN_NAME) == _row_contract(
        results["rust"][0], "plugin-filtered", ALPHA_PLUGIN_NAME
    )


def test_windows_conpty_native_and_python_skills_list_selects_exact_skill_and_submits_it(
    tmp_path: Path,
) -> None:
    """Port the real OpenSkillsList -> SkillPopup -> UserInput::Skill path."""

    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    results = {
        label: _run_skills_list_selection(
            command,
            label=label,
            artifact_dir=tmp_path,
        )
        for label, command in (("rust", rust), ("python", python))
    }

    for label, (transcript, requests) in results.items():
        output = transcript.normalized_stdout()
        assert f"SKILLS_SELECTION_RESPONSE_{label.upper()}" in output, (
            f"{label} did not complete the selected-skill turn: {output}"
        )
        assert len(requests) == 1, f"{label} requests={requests!r}"
        request_body = requests[0]
        request_text = (
            request_body.decode("utf-8")
            if isinstance(request_body, bytes)
            else json.dumps(request_body, ensure_ascii=False, sort_keys=True)
        )
        assert "execute the selected skill" in request_text
        assert ALPHA_BODY_MARKER in request_text
        assert BETA_BODY_MARKER not in request_text
        # Skill paths legitimately contain ``/skills/``.  What must not be
        # present is the slash command itself as a standalone model input.
        assert '"/skills"' not in request_text
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()

    for checkpoint in ("filtered", "moved-down", "moved-up"):
        for token in (ALPHA_SKILL, BETA_SKILL):
            assert _token_styles(results["python"][0], checkpoint, token) == _token_styles(
                results["rust"][0], checkpoint, token
            ), f"{checkpoint} style mismatch for {token}"


def test_windows_conpty_native_and_python_skills_list_escape_preserves_draft_without_model_turn(
    tmp_path: Path,
) -> None:
    """Esc closes only SkillPopup and keeps the typed tool-mention draft."""

    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, requests = _run_skills_list_escape(
            command,
            label=label,
            artifact_dir=tmp_path,
        )
        checkpoint_names = {name for name, _raw in transcript.screen_checkpoints}
        assert {"popup-before-escape", "popup-escaped"} <= checkpoint_names, (
            f"{label} did not open and escape the SkillPopup; "
            f"checkpoints={sorted(checkpoint_names)!r}\n"
            f"stdout={transcript.normalized_stdout()}\n"
            f"stderr={transcript.normalized_stderr()}"
        )
        before = transcript.checkpoint_screen(
            "popup-before-escape", rows=ROWS, cols=COLS
        )
        escaped = transcript.checkpoint_screen("popup-escaped", rows=ROWS, cols=COLS)
        assert ALPHA_SKILL in before
        assert "press enter to insert or esc to close" in before.lower()
        assert "$probe" in escaped
        assert ALPHA_SKILL not in escaped
        assert "press enter to insert or esc to close" not in escaped.lower()
        assert requests == [], f"{label} escape unexpectedly called model: {requests!r}"
        assert "SKILLS_ESCAPE_MUST_NOT_REACH_MODEL" not in transcript.normalized_stdout()


def test_windows_conpty_native_and_python_manage_skills_toggle_persists_without_model_turn(
    tmp_path: Path,
) -> None:
    """Port SkillsToggleView search/toggle/close and app persistence behavior."""

    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, requests, config_text, alpha_path = _run_manage_skills_toggle(
            command,
            label=label,
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        assert transcript.returncode == 0, (
            f"{label} /skills management failed\nstdout={output}\n"
            f"stderr={transcript.normalized_stderr()}"
        )
        assert requests == [], f"{label} management unexpectedly called model: {requests!r}"
        assert "0 skills enabled, 1 skills disabled" in output
        persisted = tomllib.loads(config_text)
        skill_rules = persisted.get("skills", {}).get("config", [])
        assert any(
            Path(str(rule.get("path"))).resolve(strict=False)
            == alpha_path.resolve(strict=False)
            and rule.get("enabled") is False
            for rule in skill_rules
        ), f"{label} did not persist the disabled skill rule: {skill_rules!r}"
        assert "SKILLS_MANAGE_MUST_NOT_REACH_MODEL" not in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_openai_docs_skill_calls_docs_mcp(
    tmp_path: Path,
) -> None:
    """The real bundled skill must drive a real official-docs MCP tool call."""

    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    for label, command in (("rust", rust), ("python", python)):
        transcript, requests, calls = _run_openai_docs_skill_execution(
            command,
            label=label,
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        assert f"OPENAI_DOCS_SKILL_COMPLETE_{label.upper()}" in output, (
            f"{label} did not finish the openai-docs tool loop\n"
            f"stdout={output}\nstderr={transcript.normalized_stderr()}"
        )
        assert len(requests) == 2, f"{label} model requests={requests!r}"
        request_texts = tuple(
            body.decode("utf-8") if isinstance(body, bytes) else json.dumps(body)
            for body in requests
        )
        assert "Always prioritize the developer docs MCP tools" in request_texts[0]
        assert "mcp__openaiDeveloperDocs" in request_texts[0]
        assert "search_openai_docs" in request_texts[0]
        assert OPENAI_DOCS_RESULT_MARKER in request_texts[1]
        assert calls == (
            {
                "name": "search_openai_docs",
                "arguments": {"query": OPENAI_DOCS_QUERY},
            },
        )
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_pdf_skill_creates_pdf_artifact(
    tmp_path: Path,
) -> None:
    """The installed PDF plugin skill must complete the local tool/artifact loop."""

    native_exe = require_native_slash_comparison()
    rust, python = build_rust_python_inline_pair(
        repo_root=Path.cwd(),
        native_exe=native_exe,
        extra_args=("--disable", "apps"),
        sandbox_mode="danger-full-access",
        approval_policy="never",
    )
    for label, command in (("rust", rust), ("python", python)):
        transcript, requests, artifact_bytes, skill_body = _run_pdf_skill_execution(
            command,
            label=label,
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        assert f"PDF_SKILL_COMPLETE_{label.upper()}" in output, (
            f"{label} did not finish the PDF tool loop\n"
            f"stdout={output}\nstderr={transcript.normalized_stderr()}"
        )
        assert len(requests) == 2, f"{label} model requests={requests!r}"
        first_request = requests[0].decode("utf-8")
        assert "Prefer visual review" in skill_body
        assert "Write final artifacts under `output/pdf/`" in skill_body
        assert "Prefer visual review" in first_request
        assert "output/pdf/" in first_request
        second_request = json.loads(requests[1])
        tool_outputs = [
            item.get("output")
            for item in second_request.get("input", [])
            if isinstance(item, dict) and item.get("type") == "function_call_output"
        ]
        assert artifact_bytes.startswith(b"%PDF-1.4"), tool_outputs[-1] if tool_outputs else None
        assert PDF_ARTIFACT_MARKER.encode("ascii") in artifact_bytes
        assert artifact_bytes.rstrip().endswith(b"%%EOF")
        assert len(artifact_bytes) > 500
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_pdf_skill_visually_inspects_rendered_page(
    tmp_path: Path,
) -> None:
    """PDF render QA must survive the ImageView replay lifecycle."""

    native_exe = require_native_slash_comparison()
    rust, python = build_rust_python_inline_pair(
        repo_root=Path.cwd(),
        native_exe=native_exe,
        extra_args=("--disable", "apps"),
        sandbox_mode="danger-full-access",
        approval_policy="never",
    )
    for label, command in (("rust", rust), ("python", python)):
        transcript, requests, image_path = _run_pdf_skill_view_image_execution(
            command,
            label=label,
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        assert f"PDF_VIEW_IMAGE_COMPLETE_{label.upper()}" in output, (
            f"{label} did not complete PDF visual inspection\n"
            f"stdout={output}\nstderr={transcript.normalized_stderr()}"
        )
        assert len(requests) == 2, f"{label} model requests={requests!r}"
        first_request = requests[0].decode("utf-8")
        second_request = json.loads(requests[1])
        assert "Prefer visual review" in first_request
        assert any(tool.get("name") == "view_image" for tool in second_request.get("tools", []))
        assert any(
            item.get("type") == "function_call_output"
            and item.get("call_id") == f"call-{label}-pdf-view-image-tool"
            and isinstance(item.get("output"), list)
            and item["output"][0].get("type") == "input_image"
            for item in second_request.get("input", [])
            if isinstance(item, dict)
        )
        assert image_path.exists()
        assert "Viewed Image" in output
        assert "replay target does not implement on_view_image_tool_call()" not in output
        assert "Conversation interrupted" not in output
