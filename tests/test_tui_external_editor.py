import os
import sys
from pathlib import Path

import pytest

from pycodex.tui.external_editor import (
    EditorError,
    EnvGuard,
    ExternalEditorError,
    drop,
    resolve_editor_command,
    restore_env,
    run_editor,
)


def test_resolve_editor_prefers_visual() -> None:
    # Rust source: external_editor.rs::tests::resolve_editor_prefers_visual.
    cmd = resolve_editor_command({"VISUAL": "vis", "EDITOR": "ed"})
    assert cmd == ["vis"]


def test_resolve_editor_errors_when_unset() -> None:
    # Rust source: external_editor.rs::tests::resolve_editor_errors_when_unset.
    with pytest.raises(ExternalEditorError) as exc:
        resolve_editor_command({})
    assert str(exc.value) == EditorError.MISSING_EDITOR.value


def test_resolve_editor_command_splits_and_rejects_empty() -> None:
    assert resolve_editor_command({"EDITOR": "code --wait"}) == ["code", "--wait"]
    with pytest.raises(ExternalEditorError) as exc:
        resolve_editor_command({"EDITOR": ""})
    assert str(exc.value) == EditorError.EMPTY_COMMAND.value


def test_resolve_editor_command_reports_parse_failed() -> None:
    with pytest.raises(ExternalEditorError) as exc:
        resolve_editor_command({"EDITOR": '"unterminated'})
    assert str(exc.value) == EditorError.PARSE_FAILED.value


@pytest.mark.asyncio
async def test_run_editor_returns_updated_content(tmp_path: Path) -> None:
    # Rust source: external_editor.rs::tests::run_editor_returns_updated_content.
    script_path = tmp_path / ("edit.py")
    script_path.write_text(
        "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('edited', encoding='utf-8')\n",
        encoding="utf-8",
    )

    result = await run_editor("seed", [sys.executable, str(script_path)])
    assert result == "edited"


@pytest.mark.asyncio
async def test_run_editor_rejects_empty_and_nonzero_exit(tmp_path: Path) -> None:
    with pytest.raises(ExternalEditorError) as exc:
        await run_editor("seed", [])
    assert str(exc.value) == "editor command is empty"

    script_path = tmp_path / "fail.py"
    script_path.write_text("import sys\nsys.exit(7)\n", encoding="utf-8")
    with pytest.raises(ExternalEditorError) as exc:
        await run_editor("seed", [sys.executable, str(script_path)])
    assert str(exc.value) == "editor exited with status 7"


def test_env_guard_and_restore_env_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VISUAL", "before-vis")
    monkeypatch.delenv("EDITOR", raising=False)
    guard = EnvGuard.new()
    os.environ["VISUAL"] = "after-vis"
    os.environ["EDITOR"] = "after-ed"
    drop(guard)
    assert os.environ.get("VISUAL") == "before-vis"
    assert "EDITOR" not in os.environ

    restore_env("EDITOR", "ed")
    assert os.environ["EDITOR"] == "ed"
    restore_env("EDITOR", None)
    assert "EDITOR" not in os.environ
