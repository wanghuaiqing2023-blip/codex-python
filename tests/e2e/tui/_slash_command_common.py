"""Shared process harness for one-command-per-file slash E2E scenarios."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tests.e2e.tui._common import (
    RUN_EXPERIMENTAL_CONPTY_ENV,
    RUN_NATIVE_COMPARISON_ENV,
    RUN_VERIFIED_CONPTY_ENV,
    RUN_VERIFIED_CONPTY_TUI_ENV,
    SESSION_CONFIGURED_COMPOSER_PATTERN,
    ConptyInputStep,
    TerminalSize,
    TuiComparisonCommand,
    TuiProcessTranscript,
    _completed_text_response,
    _isolated_codex_home_env_with_config,
    _repo_root,
    _seed_windows_sandbox_setup,
    _SseFixtureServer,
    build_rust_python_inline_pair,
    interactive_tui_comparison_capability,
    native_codex_exe_from_env,
    run_windows_conpty_tui_command,
)


def require_native_slash_comparison() -> Path:
    for variable in (
        RUN_NATIVE_COMPARISON_ENV,
        RUN_EXPERIMENTAL_CONPTY_ENV,
        RUN_VERIFIED_CONPTY_ENV,
        RUN_VERIFIED_CONPTY_TUI_ENV,
    ):
        if os.environ.get(variable) != "1":
            pytest.skip(f"set {variable}=1 to run native ConPTY comparison")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)
    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.fail(
            "native Rust comparison was explicitly enabled, but the executable "
            f"was not found: {native_exe}"
        )
    return native_exe


def slash_candidate_pair(
    native_exe: Path,
    *,
    disable_apps: bool = True,
    disable_plugins: bool = True,
) -> tuple[TuiComparisonCommand, TuiComparisonCommand]:
    extra_args: list[str] = []
    if disable_apps:
        extra_args.extend(("--disable", "apps"))
    if disable_plugins:
        extra_args.extend(("--disable", "plugins"))
    return build_rust_python_inline_pair(
        repo_root=_repo_root(),
        native_exe=native_exe,
        extra_args=tuple(extra_args),
        sandbox_mode="read-only",
        approval_policy="never",
    )


def run_local_slash_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    slash_text: str,
    stop_pattern: str,
    artifact_dir: Path,
    feature_config_lines: tuple[str, ...] = (),
    apps_enabled: bool = False,
    plugins_enabled: bool = False,
    chatgpt_auth: bool = False,
    provider_requires_openai_auth: bool = False,
) -> tuple[TuiProcessTranscript, int]:
    repo_root = _repo_root()
    fixture_body = _completed_text_response(
        f"resp-{label}-slash-must-not-run",
        f"msg-{label}-slash-must-not-run",
        "LOCAL_SLASH_COMMAND_MUST_NOT_REACH_THE_MODEL",
    )
    with _SseFixtureServer(fixture_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            "[features]\n"
            f"apps = {'true' if apps_enabled else 'false'}\n"
            f"plugins = {'true' if plugins_enabled else 'false'}\n"
            + "".join(f"{line}\n" for line in feature_config_lines)
            + "\n"
            "[model_providers.pycodex_mock]\n"
            f'name = "Mock provider that {slash_text} must not call"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            f"requires_openai_auth = {'true' if provider_requires_openai_auth else 'false'}\n"
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        if chatgpt_auth:
            from tests.support.app_test_support import (
                ChatGptAuthFixture,
                write_chatgpt_auth,
            )

            write_chatgpt_auth(
                Path(temp_home.name),
                ChatGptAuthFixture("dummy-access-token")
                .account_id("test-account")
                .plan_type("plus")
                .email("apps-e2e@example.com"),
            )
            env.pop("OPENAI_API_KEY", None)
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        slash_text,
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text=slash_text,
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                ),
                env=env,
                timeout=3,
                stop_pattern=stop_pattern,
                stop_timeout=10,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=32, cols=120),
            )
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-{slash_text.lstrip('/').replace(' ', '-')}",
        rows=32,
        cols=120,
    )
    return transcript, request_count


def run_copy_after_response_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    response_markdown: str,
    response_ready_text: str,
    artifact_dir: Path,
) -> tuple[TuiProcessTranscript, int]:
    """Produce a real assistant response, then invoke ``/copy`` locally."""

    repo_root = _repo_root()
    fixture_body = _completed_text_response(
        f"resp-{label}-copy-source",
        f"msg-{label}-copy-source",
        response_markdown,
    )
    result_pattern = re.compile(
        r"(?:Copied last message to clipboard|No agent response to copy|Copy failed:)"
    )
    with _SseFixtureServer(fixture_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            "[features]\n"
            "apps = false\n"
            "plugins = false\n\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider for /copy response lifecycle"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = false\n'
            'request_max_retries = 0\n'
            'stream_max_retries = 0\n'
            'supports_websockets = false\n\n'
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "Create the exact copy probe response.",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="Create the exact copy probe response.",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "/copy",
                        ready_screen_text=response_ready_text,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/copy",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "",
                        ready_screen_pattern=result_pattern.pattern,
                        ready_timeout=15.0,
                        ready_quiet_period=0.3,
                        capture_name="copy-result",
                    ),
                ),
                env=env,
                timeout=3,
                stop_pattern=result_pattern.pattern,
                stop_timeout=15,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=32, cols=120),
            )
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-copy-after-response",
        rows=32,
        cols=120,
    )
    return transcript, request_count


def run_raw_markdown_toggle_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    response_markdown: str,
    response_ready_text: str,
    artifact_dir: Path,
    rows: int = 52,
    cols: int = 150,
    theme_name: str = "monokai-extended",
) -> tuple[TuiProcessTranscript, int]:
    """Render one response and capture Rich -> Raw -> Rich screen states.

    Rust owners:
    - ``history_cell::HistoryRenderMode`` selects rendered or source lines.
    - ``app::input::apply_raw_output_mode`` immediately reflows history.
    - ``streaming::controller`` applies the same mode to active responses.

    The response is fetched exactly once. Both slash commands are local and
    must only re-render the already completed transcript.
    """

    repo_root = _repo_root()
    fixture_body = _completed_text_response(
        f"resp-{label}-raw-markdown",
        f"msg-{label}-raw-markdown",
        response_markdown,
    )
    with _SseFixtureServer(fixture_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            '[tui]\n'
            f'theme = "{theme_name}"\n\n'
            '[features]\n'
            'apps = false\n'
            'plugins = false\n\n'
            '[model_providers.pycodex_mock]\n'
            'name = "Mock provider for /raw Markdown reflow"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = false\n'
            'request_max_retries = 0\n'
            'stream_max_retries = 0\n'
            'supports_websockets = false\n\n'
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "Render the fixed Markdown format probe.",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="Render the fixed Markdown format probe.",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "/raw on",
                        ready_screen_text=response_ready_text,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                        capture_name="rich-before",
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/raw on",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "/raw off",
                        ready_screen_text=(
                            "Raw output mode on: transcript text is shown for "
                            "clean terminal selection."
                        ),
                        ready_timeout=15.0,
                        ready_quiet_period=0.4,
                        atomic_write=True,
                        capture_name="raw-on",
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/raw off",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "",
                        ready_screen_text=(
                            "Raw output mode off: rich transcript rendering restored."
                        ),
                        ready_timeout=15.0,
                        ready_quiet_period=0.4,
                        capture_name="rich-after",
                    ),
                ),
                env=env,
                timeout=3,
                stop_pattern=re.escape(
                    "Raw output mode off: rich transcript rendering restored."
                ),
                stop_timeout=10,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=rows, cols=cols),
            )
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-raw-markdown-toggle",
        rows=rows,
        cols=cols,
    )
    return transcript, request_count


def run_theme_slash_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    theme_name: str,
    artifact_dir: Path,
    rows: int = 40,
    cols: int = 160,
    preview_ready_text: str | None = None,
) -> tuple[TuiProcessTranscript, int]:
    """Capture the real styled ``/theme`` preview for one configured theme."""

    repo_root = _repo_root()
    fixture_body = _completed_text_response(
        f"resp-{label}-theme-must-not-run",
        f"msg-{label}-theme-must-not-run",
        "THEME_SLASH_COMMAND_MUST_NOT_REACH_THE_MODEL",
    )
    with _SseFixtureServer(fixture_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            '[tui]\n'
            f'theme = "{theme_name}"\n\n'
            '[features]\n'
            'apps = false\n'
            'plugins = false\n\n'
            '[model_providers.pycodex_mock]\n'
            'name = "Mock provider that /theme must not call"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = false\n'
            'request_max_retries = 0\n'
            'stream_max_retries = 0\n'
            'supports_websockets = false\n\n'
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "/theme",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/theme",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "",
                        ready_screen_text=preview_ready_text or (
                            "fn summarize" if cols >= 120 else "fn greet"
                        ),
                        ready_timeout=15.0,
                        ready_quiet_period=0.5,
                        capture_name="preview",
                    ),
                ),
                env=env,
                timeout=3,
                stop_pattern="Select Syntax Theme",
                stop_timeout=10,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=rows, cols=cols),
            )
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-theme-{theme_name}",
        rows=rows,
        cols=cols,
    )
    return transcript, request_count


def run_theme_interaction_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    input_steps: tuple[ConptyInputStep, ...],
    artifact_dir: Path,
    initial_theme: str = "catppuccin-mocha",
    rows: int = 40,
    cols: int = 160,
) -> tuple[TuiProcessTranscript, dict[str, object], int]:
    """Drive a real theme-picker interaction and return persisted config."""

    from pycodex.core.config.edit import read_toml_mapping

    repo_root = _repo_root()
    fixture_body = _completed_text_response(
        f"resp-{label}-theme-interaction-must-not-run",
        f"msg-{label}-theme-interaction-must-not-run",
        "THEME_INTERACTION_MUST_NOT_REACH_THE_MODEL",
    )
    with _SseFixtureServer(fixture_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            '[tui]\n'
            f'theme = "{initial_theme}"\n\n'
            '[features]\n'
            'apps = false\n'
            'plugins = false\n\n'
            '[model_providers.pycodex_mock]\n'
            'name = "Mock provider that /theme must not call"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = false\n'
            'request_max_retries = 0\n'
            'stream_max_retries = 0\n'
            'supports_websockets = false\n\n'
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        config_path = Path(env["CODEX_HOME"]) / "config.toml"
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=input_steps,
                env=env,
                timeout=2,
                stop_pattern=r"Select Syntax Theme",
                stop_timeout=2,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=rows, cols=cols),
            )
            persisted = read_toml_mapping(config_path)
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-theme-interaction",
        rows=rows,
        cols=cols,
    )
    return transcript, persisted, request_count


def run_theme_applied_code_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    theme_name: str,
    artifact_dir: Path,
    rows: int = 40,
    cols: int = 160,
) -> tuple[TuiProcessTranscript, dict[str, object], int]:
    """Select a theme, then render a real model-produced Rust code block."""

    from pycodex.core.config.edit import read_toml_mapping
    from pycodex.tui.render.highlight import BUILTIN_THEME_NAMES

    repo_root = _repo_root()
    theme_index = BUILTIN_THEME_NAMES.index(theme_name)
    last_theme_index = len(BUILTIN_THEME_NAMES) - 1
    if theme_index <= last_theme_index - theme_index:
        list_anchor = "\x1b[H"
        list_navigation = "\x1b[B" * theme_index
    else:
        list_anchor = "\x1b[F"
        list_navigation = "\x1b[A" * (last_theme_index - theme_index)
    response_markdown = (
        "Selected theme application probe.\n\n"
        "```rust\n"
        "fn applied_theme() -> usize { 42 }\n"
        "```"
    )
    fixture_body = _completed_text_response(
        f"resp-{label}-theme-applied",
        f"msg-{label}-theme-applied",
        response_markdown,
    )
    with _SseFixtureServer(fixture_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            '[tui]\n'
            'theme = "catppuccin-mocha"\n\n'
            '[features]\n'
            'apps = false\n'
            'plugins = false\n\n'
            '[model_providers.pycodex_mock]\n'
            'name = "Mock provider for applied /theme code rendering"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = false\n'
            'request_max_retries = 0\n'
            'stream_max_retries = 0\n'
            'supports_websockets = false\n\n'
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        config_path = Path(env["CODEX_HOME"]) / "config.toml"
        steps = (
            ConptyInputStep(
                "/theme",
                ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                ready_timeout=30.0,
                ready_quiet_period=0.5,
                atomic_write=True,
            ),
            ConptyInputStep(
                "\r",
                ready_screen_text="/theme",
                ready_timeout=10.0,
                ready_quiet_period=0.3,
            ),
            ConptyInputStep(
                list_anchor,
                ready_screen_text="fn summarize",
                ready_timeout=15.0,
                ready_quiet_period=0.4,
            ),
            # Search ranking is intentionally covered by a separate scenario.
            # Navigate from the nearest canonical list edge so similarly named
            # themes resolve identically without flooding either event loop.
            ConptyInputStep("", ready_timeout=0.5),
            ConptyInputStep(
                list_navigation,
                ready_timeout=0.0,
                chunk_delay=0.08,
            ),
            ConptyInputStep(
                "",
                ready_screen_pattern=(
                    rf"(?:›|>)\s*{re.escape(theme_name)}"
                    r"(?:\s+\(current\))?"
                ),
                ready_timeout=15.0,
                ready_quiet_period=0.4,
            ),
            ConptyInputStep(
                "\r",
                ready_timeout=0.0,
            ),
            ConptyInputStep(
                "\x15render the theme application probe",
                ready_timeout=1.0,
                atomic_write=True,
            ),
            ConptyInputStep(
                "\r",
                ready_screen_text="render the theme application probe",
                ready_timeout=10.0,
                ready_quiet_period=0.3,
            ),
            ConptyInputStep(
                "",
                ready_screen_text="fn applied_theme",
                ready_timeout=30.0,
                ready_quiet_period=0.5,
                capture_name="applied-code",
            ),
            # Rust persists SyntaxThemeSelected asynchronously.  Keep the
            # process alive briefly after the rendered-response checkpoint so
            # reading config.toml cannot race the edit task.
            ConptyInputStep("", ready_timeout=1.0),
        )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=steps,
                env=env,
                timeout=3,
                stop_pattern="fn applied_theme",
                stop_timeout=10,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=rows, cols=cols),
            )
            persisted = read_toml_mapping(config_path)
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-theme-applied-{theme_name}",
        rows=rows,
        cols=cols,
    )
    return transcript, persisted, request_count


def run_clean_exit_slash_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    slash_text: str,
    artifact_dir: Path,
) -> tuple[TuiProcessTranscript, int]:
    """Run a slash command that should complete the TUI shutdown sequence."""

    repo_root = _repo_root()
    fixture_body = _completed_text_response(
        f"resp-{label}-exit-must-not-run",
        f"msg-{label}-exit-must-not-run",
        "EXIT_SLASH_COMMAND_MUST_NOT_REACH_THE_MODEL",
    )
    with _SseFixtureServer(fixture_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            "[features]\n"
            "apps = false\n"
            "plugins = false\n\n"
            "[model_providers.pycodex_mock]\n"
            f'name = "Mock provider that {slash_text} must not call"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        slash_text,
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_text=slash_text,
                        ready_timeout=10.0,
                        ready_quiet_period=0.5,
                    ),
                ),
                env=env,
                timeout=35,
                size=TerminalSize(rows=32, cols=120),
            )
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-{slash_text.lstrip('/')}",
        rows=32,
        cols=120,
    )
    return transcript, request_count


def run_repeated_local_slash_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    commands_and_effects: tuple[tuple[str, str], ...],
    artifact_dir: Path,
) -> tuple[TuiProcessTranscript, int]:
    """Run stateful local slash effects in one TUI without model requests."""

    if not commands_and_effects:
        raise ValueError("commands_and_effects must not be empty")
    repo_root = _repo_root()
    fixture_body = _completed_text_response(
        f"resp-{label}-repeated-slash-must-not-run",
        f"msg-{label}-repeated-slash-must-not-run",
        "LOCAL_SLASH_COMMAND_MUST_NOT_REACH_THE_MODEL",
    )
    with _SseFixtureServer(fixture_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            "[features]\n"
            "apps = false\n"
            "plugins = false\n\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider that repeated local slash commands must not call"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        input_steps: list[ConptyInputStep] = []
        previous_effect: str | None = None
        for slash_text, effect_text in commands_and_effects:
            input_steps.append(
                ConptyInputStep(
                    slash_text,
                    ready_pattern=(
                        SESSION_CONFIGURED_COMPOSER_PATTERN
                        if previous_effect is None
                        else None
                    ),
                    ready_text=previous_effect,
                    ready_timeout=30.0 if previous_effect is None else 10.0,
                    ready_quiet_period=0.3,
                    atomic_write=True,
                )
            )
            input_steps.append(
                ConptyInputStep(
                    "\r",
                    ready_screen_text=slash_text,
                    ready_timeout=10.0,
                    ready_quiet_period=0.2,
                )
            )
            previous_effect = effect_text

        env, temp_home = _isolated_codex_home_env_with_config(config)
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=tuple(input_steps),
                env=env,
                timeout=3,
                stop_pattern=commands_and_effects[-1][1],
                stop_timeout=10,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=32, cols=120),
            )
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-{commands_and_effects[0][0].lstrip('/')}-repeated",
        rows=32,
        cols=120,
    )
    return transcript, request_count


def run_session_transition_slash_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    slash_text: str,
    artifact_dir: Path,
) -> tuple[TuiProcessTranscript, int]:
    """Run a local session transition, then prove the new composer is live."""

    repo_root = _repo_root()
    fixture_body = _completed_text_response(
        f"resp-{label}-session-slash-must-not-run",
        f"msg-{label}-session-slash-must-not-run",
        "SESSION_SLASH_MUST_NOT_REACH_THE_MODEL",
    )
    with _SseFixtureServer(fixture_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            "[features]\n"
            "apps = false\n"
            "plugins = false\n\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider that session slash commands must not call"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        slash_text,
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text=slash_text,
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    # Session replacement is asynchronous in Rust. Give both
                    # products the same bounded handoff window before probing
                    # the replacement composer with another local command.
                    ConptyInputStep(
                        "/status",
                        ready_timeout=2.0,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/status",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                ),
                env=env,
                timeout=35,
                stop_pattern="Session:",
                stop_timeout=15,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=36, cols=120),
            )
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-{slash_text.lstrip('/')}-session",
        rows=36,
        cols=120,
    )
    return transcript, request_count


def run_compact_slash_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
) -> tuple[TuiProcessTranscript, int]:
    """Run manual compaction, then probe the recovered composer with /status."""

    repo_root = _repo_root()
    fixture_body = _completed_text_response(
        f"resp-{label}-compact",
        f"msg-{label}-compact",
        "Compacted conversation summary.",
    )
    with _SseFixtureServer(fixture_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            "[features]\n"
            "apps = false\n"
            "plugins = false\n\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider for manual compaction"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "/compact",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/compact",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "/status",
                        ready_timeout=5.0,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/status",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                ),
                env=env,
                timeout=45,
                stop_pattern="Session:",
                stop_timeout=15,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=36, cols=120),
            )
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-compact",
        rows=36,
        cols=120,
    )
    return transcript, request_count


def run_side_slash_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
    inline_text: str | None = None,
    slash_command: str = "side",
) -> tuple[TuiProcessTranscript, tuple[bytes, ...]]:
    """Start a real side fork after seeding the parent conversation."""

    repo_root = _repo_root()
    main_reply = "MAIN_SESSION_READY"
    side_reply = "SIDE_REPLY_READY"
    bodies = (
        _completed_text_response(
            f"resp-{label}-side-main",
            f"msg-{label}-side-main",
            main_reply,
        ),
        _completed_text_response(
            f"resp-{label}-side-child",
            f"msg-{label}-side-child",
            side_reply,
        ),
    )
    slash_text = (
        f"/{slash_command} {inline_text}"
        if inline_text is not None
        else f"/{slash_command}"
    )
    config = (
        'model = "mock-model"\n'
        'model_provider = "pycodex_mock"\n'
        'approval_policy = "never"\n'
        'sandbox_mode = "read-only"\n'
        'suppress_unstable_features_warning = true\n\n'
        "[features]\n"
        "apps = false\n"
        "plugins = false\n\n"
        "[model_providers.pycodex_mock]\n"
        'name = "Mock provider for side-conversation slash coverage"\n'
        f'base_url = "{{base_url}}"\n'
        'wire_api = "responses"\n'
        "request_max_retries = 0\n"
        "stream_max_retries = 0\n"
        "supports_websockets = false\n\n"
        f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
        'trust_level = "trusted"\n'
    )
    with _SseFixtureServer(bodies) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            config.format(base_url=server.base_url)
        )
        input_steps = [
            ConptyInputStep(
                "Seed the main conversation.",
                ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                ready_timeout=30.0,
                ready_quiet_period=0.5,
                atomic_write=True,
            ),
            ConptyInputStep(
                "\r",
                ready_screen_text="Seed the main conversation.",
                ready_timeout=10.0,
                ready_quiet_period=0.2,
            ),
            ConptyInputStep(
                slash_text,
                ready_text=main_reply,
                ready_timeout=30.0,
                ready_quiet_period=0.5,
                atomic_write=True,
            ),
            ConptyInputStep(
                "\r",
                ready_screen_text=slash_text,
                ready_timeout=10.0,
                ready_quiet_period=0.2,
            ),
        ]
        if inline_text is None:
            input_steps.extend(
                (
                    ConptyInputStep(
                        # Rust accepts both Ctrl+C and Ctrl+D for returning
                        # from a side thread. Ctrl+D is delivered as an input
                        # byte by Windows ConPTY instead of a host signal.
                        "\x04",
                        ready_text="Ctrl+C to return",
                        ready_timeout=20.0,
                        ready_quiet_period=0.5,
                    ),
                    ConptyInputStep(
                        "/status",
                        ready_timeout=3.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/status",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                )
            )
            stop_pattern = "Session:"
        else:
            stop_pattern = side_reply
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=tuple(input_steps),
                env=env,
                timeout=45,
                stop_pattern=stop_pattern,
                stop_timeout=30,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=38, cols=120),
            )
        request_bodies = tuple(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=(
            f"{label}-{slash_command}-inline"
            if inline_text is not None
            else f"{label}-{slash_command}-bare"
        ),
        rows=38,
        cols=120,
    )
    return transcript, request_bodies


def run_diff_slash_pair(
    native_exe: Path,
    *,
    artifact_dir: Path,
) -> tuple[
    tuple[TuiProcessTranscript, int],
    tuple[TuiProcessTranscript, int],
]:
    """Run `/diff` against one real dirty Git repository in both products."""

    git_probe = subprocess.run(
        ["git", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if git_probe.returncode != 0:
        pytest.skip("git executable is required for /diff native comparison")

    repo_root = _repo_root()
    top_marker = "PYCODEX_DIFF_TOP_MARKER"
    middle_marker = "PYCODEX_DIFF_MIDDLE_MARKER"
    bottom_marker = "PYCODEX_DIFF_BOTTOM_MARKER"
    fixture_body = _completed_text_response(
        "resp-diff-must-not-run",
        "msg-diff-must-not-run",
        "DIFF_SLASH_MUST_NOT_REACH_THE_MODEL",
    )
    with tempfile.TemporaryDirectory(
        prefix="pycodex-diff-native-"
    ) as repo_dir_text:
        target_repo = Path(repo_dir_text)
        subprocess.run(
            ["git", "init"],
            cwd=target_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        tracked = target_repo / "tracked.txt"
        baseline = [f"baseline line {index:03d}" for index in range(1, 81)]
        tracked.write_text("\n".join(baseline) + "\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "tracked.txt"],
            cwd=target_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=pycodex@example.invalid",
                "-c",
                "user.name=PyCodex Test",
                "commit",
                "-m",
                "initial",
            ],
            cwd=target_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        changed = list(baseline)
        changed[1] = f"replacement line 002 {top_marker}"
        additions = [f"added pager line {index:03d}" for index in range(1, 91)]
        additions[34] += f" {middle_marker}"
        additions[-1] += f" {bottom_marker}"
        tracked.write_text(
            "\n".join([*changed, *additions]) + "\n",
            encoding="utf-8",
        )

        with _SseFixtureServer(fixture_body) as server:
            trust_key = str(target_repo.resolve(strict=False)).lower()
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                "[features]\n"
                "apps = false\n"
                "plugins = false\n\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider that /diff must not call"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{trust_key}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            env["PYTHONPATH"] = str(repo_root)
            common = (
                "-C",
                str(target_repo),
                "-s",
                "read-only",
                "-a",
                "never",
                "--disable",
                "apps",
                "--disable",
                "plugins",
            )
            rust = TuiComparisonCommand(
                kind="rust",
                argv=(str(native_exe), *common),
                cwd=repo_root,
            )
            python = TuiComparisonCommand(
                kind="python",
                argv=(sys.executable, "-m", "pycodex", *common),
                cwd=repo_root,
            )
            configured_repo_ready_pattern = (
                rf"(?ms)directory:.*{re.escape(target_repo.name)}.*"
                rf"(?:^>\s*$|^\s*\u203a\s+.+$)"
            )
            input_steps = (
                ConptyInputStep(
                    "/diff",
                    ready_pattern=configured_repo_ready_pattern,
                    ready_timeout=30.0,
                    ready_quiet_period=0.5,
                    atomic_write=True,
                ),
                ConptyInputStep(
                    "\r",
                    ready_screen_text="/diff",
                    ready_timeout=10.0,
                    ready_quiet_period=0.2,
                ),
                ConptyInputStep(
                    "\x1b[6~",
                    ready_text=top_marker,
                    ready_timeout=15.0,
                    ready_quiet_period=0.75,
                    atomic_write=True,
                    capture_name="initial",
                ),
                ConptyInputStep(
                    "\x1b[F",
                    ready_screen_text=middle_marker,
                    ready_timeout=10.0,
                    ready_quiet_period=0.3,
                    atomic_write=True,
                    capture_name="page_down",
                ),
                ConptyInputStep(
                    "\x1b[H",
                    ready_screen_text=bottom_marker,
                    ready_timeout=10.0,
                    ready_quiet_period=0.3,
                    atomic_write=True,
                    capture_name="bottom",
                ),
                ConptyInputStep(
                    "q",
                    ready_screen_text=top_marker,
                    ready_timeout=10.0,
                    ready_quiet_period=0.3,
                    atomic_write=True,
                    capture_name="home",
                ),
                ConptyInputStep(
                    "/quit",
                    ready_screen_text="directory:",
                    ready_timeout=10.0,
                    ready_quiet_period=0.3,
                    atomic_write=True,
                    capture_name="restored",
                ),
                ConptyInputStep(
                    "\r",
                    ready_screen_text="/quit",
                    ready_timeout=10.0,
                    ready_quiet_period=0.2,
                ),
            )
            with temp_home:
                rust_transcript = run_windows_conpty_tui_command(
                    rust,
                    input_steps=input_steps,
                    env=env,
                    timeout=20,
                    size=TerminalSize(rows=32, cols=120),
                )
                rust_requests = len(server.request_bodies)
                python_transcript = run_windows_conpty_tui_command(
                    python,
                    input_steps=input_steps,
                    env=env,
                    timeout=20,
                    size=TerminalSize(rows=32, cols=120),
                )
                python_requests = len(server.request_bodies) - rust_requests

    rust_transcript.write_artifacts(
        artifact_dir,
        prefix="rust-diff-dirty-repo",
        rows=32,
        cols=120,
    )
    python_transcript.write_artifacts(
        artifact_dir,
        prefix="python-diff-dirty-repo",
        rows=32,
        cols=120,
    )
    return (
        (rust_transcript, rust_requests),
        (python_transcript, python_requests),
    )


def run_seeded_windows_sandbox_setup_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
) -> tuple[TuiProcessTranscript, int, str]:
    """Run `/setup-default-sandbox` without triggering elevation.

    Rust's setup owner skips UAC when the versioned sandbox identity files
    already exist. Copying those two machine-local identity records into the
    isolated CODEX_HOME lets both products exercise the real command/event/
    config-persistence path without modifying the host configuration.
    """

    repo_root = _repo_root()
    slash_text = "/setup-default-sandbox"
    fixture_body = _completed_text_response(
        f"resp-{label}-setup-default-sandbox-must-not-run",
        f"msg-{label}-setup-default-sandbox-must-not-run",
        "SETUP_DEFAULT_SANDBOX_MUST_NOT_REACH_THE_MODEL",
    )
    with _SseFixtureServer(fixture_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            "[windows]\n"
            'sandbox = "unelevated"\n\n'
            "[features]\n"
            "apps = false\n"
            "plugins = false\n\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider that sandbox setup must not call"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        home_path = Path(temp_home.name)
        _seed_windows_sandbox_setup(home_path)
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        slash_text,
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text=slash_text,
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                ),
                env=env,
                timeout=8,
                stop_pattern="Sandbox ready",
                stop_timeout=20,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=32, cols=120),
            )
            persisted_config = (home_path / "config.toml").read_text(
                encoding="utf-8"
            )
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-setup-default-sandbox",
        rows=32,
        cols=120,
    )
    return transcript, request_count, persisted_config


def run_saved_view_slash_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    slash_text: str,
    view_markers: tuple[str, ...],
    artifact_dir: Path,
    feature_config_lines: tuple[str, ...] = (),
) -> tuple[TuiProcessTranscript, int, str]:
    """Open a view command, accept/save it, and exit without a model turn."""

    if not view_markers:
        raise ValueError("view_markers must not be empty")
    repo_root = _repo_root()
    fixture_body = _completed_text_response(
        f"resp-{label}-saved-view-must-not-run",
        f"msg-{label}-saved-view-must-not-run",
        "SAVED_VIEW_SLASH_MUST_NOT_REACH_THE_MODEL",
    )
    with _SseFixtureServer(fixture_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            "[features]\n"
            "apps = false\n"
            "plugins = false\n"
            + "".join(f"{line}\n" for line in feature_config_lines)
            + "\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider that saved views must not call"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        home_path = Path(temp_home.name)
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        slash_text,
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text=slash_text,
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_text_sequence=view_markers,
                        ready_timeout=15.0,
                        ready_quiet_period=0.3,
                    ),
                    ConptyInputStep(
                        "/quit",
                        ready_timeout=1.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/quit",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                ),
                env=env,
                timeout=35,
                size=TerminalSize(rows=36, cols=120),
            )
            persisted_config = (home_path / "config.toml").read_text(
                encoding="utf-8"
            )
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-{slash_text.lstrip('/')}-saved-view",
        rows=36,
        cols=120,
    )
    return transcript, request_count, persisted_config


def run_view_slash_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    slash_text: str,
    view_markers: tuple[str, ...],
    artifact_dir: Path,
    feature_config_lines: tuple[str, ...] = (),
) -> tuple[TuiProcessTranscript, int]:
    """Open and cancel a slash-command view without creating a model turn."""

    if not view_markers:
        raise ValueError("view_markers must not be empty")
    repo_root = _repo_root()
    fixture_body = _completed_text_response(
        f"resp-{label}-view-must-not-run",
        f"msg-{label}-view-must-not-run",
        "VIEW_SLASH_MUST_NOT_REACH_THE_MODEL",
    )
    with _SseFixtureServer(fixture_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            "[features]\n"
            "apps = false\n"
            "plugins = false\n"
            + "".join(f"{line}\n" for line in feature_config_lines)
            + "\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider that views must not call"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        slash_text,
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text=slash_text,
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "\x1b",
                        ready_text_sequence=view_markers,
                        ready_timeout=15.0,
                        ready_quiet_period=0.3,
                    ),
                    ConptyInputStep(
                        "/quit",
                        ready_timeout=2.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/quit",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                ),
                env=env,
                timeout=35,
                size=TerminalSize(rows=36, cols=120),
            )
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-{slash_text.lstrip('/')}-view",
        rows=36,
        cols=120,
    )
    return transcript, request_count


def assert_local_slash_candidate(
    label: str,
    transcript: TuiProcessTranscript,
    request_count: int,
) -> None:
    detail = (
        f"{label}: requests={request_count}; "
        f"stderr={transcript.normalized_stderr()!r}; "
        f"screen={transcript.screen_stdout(rows=32, cols=120)!r}"
    )
    assert request_count == 0, detail
    assert (
        "LOCAL_SLASH_COMMAND_MUST_NOT_REACH_THE_MODEL"
        not in transcript.normalized_stdout()
    ), detail
    assert "product effect is not yet available" not in transcript.normalized_stdout(), detail
    assert (
        "ConPTY command terminated after stop pattern"
        in transcript.normalized_stderr()
    ), detail


__all__ = [
    "assert_local_slash_candidate",
    "require_native_slash_comparison",
    "run_clean_exit_slash_candidate",
    "run_compact_slash_candidate",
    "run_copy_after_response_candidate",
    "run_diff_slash_pair",
    "run_local_slash_candidate",
    "run_repeated_local_slash_candidate",
    "run_raw_markdown_toggle_candidate",
    "run_session_transition_slash_candidate",
    "run_side_slash_candidate",
    "run_theme_slash_candidate",
    "slash_candidate_pair",
    "run_view_slash_candidate",
]
