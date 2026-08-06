"""End-to-end coverage for the real app-server stdio command boundary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support.app_test_support import McpProcess


pytestmark = pytest.mark.e2e


def test_app_server_command_serves_initialize_over_stdio(tmp_path: Path) -> None:
    request = {
        "id": 1,
        "method": "initialize",
        "params": {
            "clientInfo": {
                "name": "pycodex-integration-test",
                "title": "PyCodex integration test",
                "version": "1.0.0",
            },
            "capabilities": {},
        },
    }
    env = os.environ.copy()
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    env["CODEX_HOME"] = str(codex_home)

    completed = subprocess.run(
        [sys.executable, "-m", "pycodex", "app-server"],
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        env=env,
        timeout=15,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    messages = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    response = next(message for message in messages if message.get("id") == 1)
    assert response["result"]["codexHome"] == str(tmp_path / "codex-home")
    assert response["result"]["userAgent"]


@pytest.mark.asyncio
async def test_app_test_support_mcp_process_serves_initialize_over_stdio(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "support-codex-home"
    process = await McpProcess.new(codex_home)
    try:
        response = await process.initialize(client_name="pycodex-e2e-app-test-support")
    finally:
        await process.close()

    assert response["result"]["codexHome"] == str(codex_home)
    assert response["result"]["userAgent"]


@pytest.mark.asyncio
async def test_hooks_list_discovers_user_config_hook_over_stdio(
    tmp_path: Path,
) -> None:
    """Rust ``hooks_list_shows_discovered_hook`` app-server contract.

    A hook declared in the user-level ``CODEX_HOME/config.toml`` must be
    returned by the real ``hooks/list`` stdio request. The TUI derives its
    Installed count from this response, so an unhandled request or empty hook
    list reproduces the user-visible ``Installed = 0`` regression.
    """

    codex_home = tmp_path / "codex-home"
    cwd = tmp_path / "worktree"
    hook_script = cwd / ".codex" / "hooks" / "audit_hook.py"
    hook_script.parent.mkdir(parents=True)
    hook_script.write_text("print('{}')\n", encoding="utf-8")
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        """
[features]
hooks = true
plugins = false

[[hooks.UserPromptSubmit]]

[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = "python .codex/hooks/audit_hook.py"
commandWindows = "python .codex/hooks/audit_hook.py"
timeout = 5
statusMessage = "Auditing prompt submission"
""".lstrip(),
        encoding="utf-8",
    )

    process = await McpProcess.new(codex_home)
    try:
        await process.initialize(client_name="pycodex-e2e-hooks-list")
        response = await process.send_request(
            "hooks/list",
            {"cwds": [str(cwd)]},
        )
    finally:
        await process.close()

    assert "error" not in response, (
        "app-server did not route hooks/list; the TUI falls back to an empty "
        f"hook entry and renders every Installed count as 0: {response}"
    )
    data = response["result"]["data"]
    assert len(data) == 1, (
        "hooks/list omitted the requested cwd; /hooks will render every "
        f"Installed count as 0: {response}"
    )
    entry = data[0]
    assert Path(entry["cwd"]).resolve() == cwd.resolve()
    assert entry["errors"] == []
    assert len(entry["hooks"]) == 1, (
        "hooks/list did not discover the user-configured hook; /hooks will "
        f"render UserPromptSubmit Installed as 0: {entry}"
    )
    hook = entry["hooks"][0]
    assert hook["eventName"] == "userPromptSubmit"
    assert hook["handlerType"] == "command"
    assert hook["source"] == "user"
    assert hook["enabled"] is True
    assert hook["trustStatus"] == "untrusted"
