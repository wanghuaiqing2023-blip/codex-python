import asyncio
import io
from types import SimpleNamespace

from pycodex.protocol import TokenUsage
from pycodex.tui import AppExitInfo, ExitReason, ExitReasonPayload
from pycodex.tui.main import (
    CliConfigOverrides,
    TopCli,
    format_exit_messages,
    handle_exit_info,
    main,
    merge_top_cli_overrides,
    run_top_cli,
)

THREAD_ID = "123e4567-e89b-12d3-a456-426614174000"


def test_format_exit_messages_matches_tui_main_resume_and_usage_order() -> None:
    # Rust: codex-tui/src/main.rs::format_exit_messages.
    info = AppExitInfo(
        token_usage=TokenUsage(input_tokens=1, output_tokens=2, total_tokens=3),
        thread_id=THREAD_ID,
    )
    lines = format_exit_messages(info)
    assert lines[0] == "Token usage: total=3 input=1 output=2"
    assert lines[1] == f"To continue this session, run codex resume {THREAD_ID}"


def test_format_exit_messages_colors_resume_command_when_enabled() -> None:
    # Rust wraps only the resume command in cyan when color is enabled.
    info = AppExitInfo(thread_id=THREAD_ID)
    assert format_exit_messages(info, color_enabled=True) == [
        f"To continue this session, run \x1b[36mcodex resume {THREAD_ID}\x1b[39m"
    ]


def test_merge_top_cli_overrides_prepend_root_overrides() -> None:
    # Rust: TopCli flattens top-level config overrides and splices them before
    # inner TUI-local overrides.
    inner = SimpleNamespace(config_overrides=SimpleNamespace(raw_overrides=("inner=2",)))
    merged = merge_top_cli_overrides(TopCli(CliConfigOverrides(("root=1",)), inner))
    assert merged.config_overrides.raw_overrides == ("root=1", "inner=2")


def test_run_top_cli_passes_merged_inner_to_run_main() -> None:
    seen = {}

    async def fake_run_main(inner, arg0_paths, loader_overrides, *, explicit_remote_endpoint=None):
        seen["inner"] = inner
        seen["arg0_paths"] = arg0_paths
        seen["loader_overrides"] = loader_overrides
        seen["explicit_remote_endpoint"] = explicit_remote_endpoint
        return AppExitInfo(thread_id=THREAD_ID)

    inner = SimpleNamespace(config_overrides=SimpleNamespace(raw_overrides=("inner=2",)))
    result = asyncio.run(
        run_top_cli(
            TopCli(CliConfigOverrides(("root=1",)), inner),
            arg0_paths="arg0",
            loader_overrides="loader",
            explicit_remote_endpoint="endpoint",
            run_main_fn=fake_run_main,
        )
    )
    assert result.thread_id == THREAD_ID
    assert seen["inner"].config_overrides.raw_overrides == ("root=1", "inner=2")
    assert seen["arg0_paths"] == "arg0"
    assert seen["loader_overrides"] == "loader"
    assert seen["explicit_remote_endpoint"] == "endpoint"


def test_handle_exit_info_prints_messages_or_fatal_error() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    assert handle_exit_info(AppExitInfo(thread_id=THREAD_ID), stdout=stdout, stderr=stderr) == 0
    assert stdout.getvalue() == f"To continue this session, run codex resume {THREAD_ID}\n"
    assert stderr.getvalue() == ""

    fatal_stderr = io.StringIO()
    code = handle_exit_info(
        AppExitInfo(exit_reason=ExitReasonPayload(ExitReason.FATAL, "boom")),
        stdout=io.StringIO(),
        stderr=fatal_stderr,
    )
    assert code == 1
    assert fatal_stderr.getvalue() == "ERROR: boom\n"


def test_main_delegates_to_run_main_and_formats_exit_messages() -> None:
    async def fake_run_main(*_args, **_kwargs):
        return AppExitInfo(thread_id=THREAD_ID)

    stdout = io.StringIO()
    assert main([], stdout=stdout, stderr=io.StringIO(), run_main_fn=fake_run_main) == 0
    assert stdout.getvalue() == f"To continue this session, run codex resume {THREAD_ID}\n"
