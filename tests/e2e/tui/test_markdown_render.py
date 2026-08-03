"""Real-product Rust differential E2E coverage for Markdown rendering."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.e2e.support.vt_screen import VtScreen, VtStyle
from tests.e2e.tui._common import (
    SESSION_CONFIGURED_COMPOSER_PATTERN,
    ConptyInputStep,
    TerminalSize,
    TuiComparisonCommand,
    TuiProcessTranscript,
    _completed_text_response,
    _isolated_codex_home_env_with_config,
    _repo_root,
    _SseFixtureServer,
    run_windows_conpty_tui_command,
)
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e

THEME_NAME = "monokai-extended"
MARKDOWN_RESPONSE = r"""# MD-E2E-H1

## MD-E2E-H2

### MD-E2E-H3

#### MD-E2E-H4

##### MD-E2E-H5

###### MD-E2E-H6

**MD-E2E-STRONG-ONLY** and *MD-E2E-EMPHASIS-ONLY* and ***MD-E2E-COMBINED***

~~MD-E2E-STRIKE~~ and \*MD-E2E-ESCAPED\*

`MD-E2E-INLINE-CODE` and [MD-E2E-LINK](https://example.com/markdown-e2e)

MD-E2E-SOFT-A
MD-E2E-SOFT-B

MD-E2E-HARD-A\
MD-E2E-HARD-B

> MD-E2E-QUOTE-PLAIN with **MD-E2E-QUOTE-STRONG**

- MD-E2E-UNORDERED
  - MD-E2E-UNORDERED-NESTED

1. MD-E2E-ORDERED
   1. MD-E2E-ORDERED-NESTED

| Name | Value |
| --- | --- |
| **MD-E2E-TABLE-BOLD** | `MD-E2E-TABLE-CODE` |

```python
def markdown_probe(value: int) -> str:
    return f"MD-E2E-CODE-{value}"
```
"""


@dataclass(frozen=True)
class MarkdownCase:
    name: str
    rows: int
    cols: int


CASES = (
    MarkdownCase("wide", rows=58, cols=150),
    MarkdownCase("narrow", rows=66, cols=80),
)


def _run_markdown_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    case: MarkdownCase,
    artifact_dir: Path,
) -> tuple[TuiProcessTranscript, int]:
    repo_root = _repo_root()
    fixture_body = _completed_text_response(
        f"resp-{label}-markdown-{case.name}",
        f"msg-{label}-markdown-{case.name}",
        MARKDOWN_RESPONSE,
    )
    with _SseFixtureServer(fixture_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            '[tui]\n'
            f'theme = "{THEME_NAME}"\n\n'
            '[features]\n'
            'apps = false\n'
            'plugins = false\n\n'
            '[model_providers.pycodex_mock]\n'
            'name = "Mock provider for Markdown rendering differential"\n'
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
                        "Render the fixed Markdown E2E probe.",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="Render the fixed Markdown E2E probe.",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "",
                        ready_screen_text="MD-E2E-CODE",
                        ready_timeout=30.0,
                        ready_quiet_period=0.7,
                        capture_name="markdown-rendered",
                    ),
                    ConptyInputStep(
                        "/quit",
                        ready_screen_text="MD-E2E-CODE",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
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
                timeout=3,
                stop_pattern=re.escape("Shutting down..."),
                stop_timeout=10,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=case.rows, cols=case.cols),
            )
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-markdown-{case.name}",
        rows=case.rows,
        cols=case.cols,
    )
    return transcript, request_count


def _row_text(screen: VtScreen, row_index: int) -> str:
    return "".join(
        cell.char for cell in screen.rows[row_index] if not cell.continuation
    ).rstrip()


def _token_cells(
    screen: VtScreen,
    token: str,
) -> tuple[int, int, tuple[object, ...]]:
    matches: list[tuple[int, int, tuple[object, ...]]] = []
    for row_index, row in enumerate(screen.rows):
        text = _row_text(screen, row_index)
        start = text.find(token)
        while start >= 0:
            matches.append((row_index, start, tuple(row[start : start + len(token)])))
            start = text.find(token, start + len(token))
    assert len(matches) == 1, (
        f"expected one visible {token!r}, found {len(matches)} in:\n{screen.text()}"
    )
    return matches[0]


def _styles_for_token(screen: VtScreen, token: str) -> tuple[VtStyle, ...]:
    _, _, cells = _token_cells(screen, token)
    return tuple(cell.style for cell in cells)


def _markdown_region(
    screen: VtScreen,
) -> tuple[tuple[str, tuple[VtStyle, ...]], ...]:
    start_row, _, _ = _token_cells(screen, "MD-E2E-H1")
    end_row, _, _ = _token_cells(screen, "MD-E2E-CODE")
    result: list[tuple[str, tuple[VtStyle, ...]]] = []
    for row_index in range(start_row, end_row + 1):
        text = _row_text(screen, row_index)
        row = screen.rows[row_index]
        result.append((text, tuple(cell.style for cell in row[: len(text)])))
    return tuple(result)


def _assert_regions_equal(
    python_screen: VtScreen,
    rust_screen: VtScreen,
    *,
    case: MarkdownCase,
) -> None:
    python_region = _markdown_region(python_screen)
    rust_region = _markdown_region(rust_screen)
    assert len(python_region) == len(rust_region), (
        f"{case.name}: Markdown row count differs: "
        f"python={len(python_region)}, rust={len(rust_region)}\n"
        f"Python:\n{python_screen.text()}\nRust:\n{rust_screen.text()}"
    )
    for row_offset, (python_row, rust_row) in enumerate(
        zip(python_region, rust_region, strict=True)
    ):
        python_text, python_styles = python_row
        rust_text, rust_styles = rust_row
        assert python_text == rust_text, (
            f"{case.name}: Markdown text differs at relative row {row_offset}:\n"
            f"python={python_text!r}\nrust={rust_text!r}"
        )
        for column, (python_style, rust_style) in enumerate(
            zip(python_styles, rust_styles, strict=True)
        ):
            assert python_style == rust_style, (
                f"{case.name}: Markdown style differs at relative row "
                f"{row_offset}, column {column}, char={python_text[column]!r}:\n"
                f"python={python_style!r}\nrust={rust_style!r}\n"
                f"line={python_text!r}"
            )


def _assert_markdown_semantics(screen: VtScreen, *, label: str, case: str) -> None:
    detail = f"{label}/{case} screen:\n{screen.text()}"
    for token in (
        "MD-E2E-H1",
        "MD-E2E-H2",
        "MD-E2E-H3",
        "MD-E2E-H4",
        "MD-E2E-H5",
        "MD-E2E-H6",
        "MD-E2E-STRONG-ONLY",
        "MD-E2E-EMPHASIS-ONLY",
        "MD-E2E-COMBINED",
        "MD-E2E-STRIKE",
        "*MD-E2E-ESCAPED*",
        "MD-E2E-INLINE-CODE",
        "MD-E2E-LINK",
        "https://example.com/markdown-e2e",
        "MD-E2E-SOFT-A",
        "MD-E2E-SOFT-B",
        "MD-E2E-HARD-A",
        "MD-E2E-HARD-B",
        "MD-E2E-QUOTE-PLAIN",
        "MD-E2E-UNORDERED-NESTED",
        "MD-E2E-ORDERED-NESTED",
        "MD-E2E-TABLE-BOLD",
        "MD-E2E-TABLE-CODE",
        "def markdown_probe(value: int) -> str:",
        'return f"MD-E2E-CODE-{value}"',
    ):
        assert token in screen.text(), f"missing Markdown token {token!r}; {detail}"

    for hidden_source in (
        "**MD-E2E-STRONG-ONLY**",
        "*MD-E2E-EMPHASIS-ONLY*",
        "***MD-E2E-COMBINED***",
        "~~MD-E2E-STRIKE~~",
        "`MD-E2E-INLINE-CODE`",
        "[MD-E2E-LINK](https://example.com/markdown-e2e)",
        "| --- | --- |",
        "```python",
    ):
        assert hidden_source not in screen.text(), (
            f"Markdown source marker leaked into Rich output: {hidden_source!r}; {detail}"
        )

    assert all(
        style.bold and style.underline
        for style in _styles_for_token(screen, "MD-E2E-H1")
    ), f"H1 is not bold and underlined; {detail}"
    assert all(
        style.bold for style in _styles_for_token(screen, "MD-E2E-H2")
    ), f"H2 is not bold; {detail}"
    assert all(
        style.bold and style.italic
        for style in _styles_for_token(screen, "MD-E2E-H3")
    ), f"H3 is not bold and italic; {detail}"
    for heading in ("MD-E2E-H4", "MD-E2E-H5", "MD-E2E-H6"):
        assert all(style.italic for style in _styles_for_token(screen, heading)), (
            f"{heading} is not italic; {detail}"
        )
    assert all(style.bold for style in _styles_for_token(screen, "MD-E2E-STRONG-ONLY"))
    assert all(style.italic for style in _styles_for_token(screen, "MD-E2E-EMPHASIS-ONLY"))
    assert all(
        style.bold and style.italic
        for style in _styles_for_token(screen, "MD-E2E-COMBINED")
    )
    assert all(
        style.crossed_out for style in _styles_for_token(screen, "MD-E2E-STRIKE")
    )
    assert all(
        not style.italic
        for style in _styles_for_token(screen, "MD-E2E-ESCAPED")
    )
    assert any(
        style.fg is not None
        for style in _styles_for_token(screen, "MD-E2E-INLINE-CODE")
    )
    assert any(
        style.fg is not None and style.underline
        for style in _styles_for_token(screen, "https://example.com/markdown-e2e")
    )
    assert any(
        style.fg is not None
        for style in _styles_for_token(screen, "MD-E2E-QUOTE-PLAIN")
    )
    assert any(
        style.bold and style.fg is not None
        for style in _styles_for_token(screen, "Name")
    )
    assert any(
        style.fg is not None
        for style in _styles_for_token(screen, "markdown_probe")
    )
    assert any(
        style.fg is not None for style in _styles_for_token(screen, "MD-E2E-CODE")
    )


@pytest.fixture(scope="module")
def markdown_native_differential(tmp_path_factory):
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    artifact_root = tmp_path_factory.mktemp("markdown-native-differential")
    results: dict[str, dict[str, VtScreen]] = {}

    for case in CASES:
        case_results: dict[str, VtScreen] = {}
        for label, command in (("rust", rust), ("python", python)):
            transcript, request_count = _run_markdown_candidate(
                command,
                label=label,
                case=case,
                artifact_dir=artifact_root / case.name / label,
            )
            assert request_count == 1, (
                f"{label}/{case.name}: Markdown response must use exactly one model request"
            )
            assert "Traceback" not in transcript.normalized_combined(), (
                f"{label}/{case.name}: unexpected process error: "
                f"{transcript.normalized_combined()}"
            )
            case_results[label] = transcript.checkpoint_cells(
                "markdown-rendered",
                rows=case.rows,
                cols=case.cols,
            )
        results[case.name] = case_results
    return results


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_windows_conpty_markdown_text_layout_and_character_styles_match_live_rust(
    markdown_native_differential,
    case: MarkdownCase,
) -> None:
    screens = markdown_native_differential[case.name]
    _assert_markdown_semantics(screens["rust"], label="rust", case=case.name)
    _assert_markdown_semantics(screens["python"], label="python", case=case.name)
    _assert_regions_equal(screens["python"], screens["rust"], case=case)
