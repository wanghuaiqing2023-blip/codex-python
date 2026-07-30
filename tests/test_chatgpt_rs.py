"""Rust-derived tests for ``codex-rs/chatgpt``.

Rust sources:
- ``chatgpt/src/chatgpt_client.rs``
- ``chatgpt/src/get_task.rs``
- ``chatgpt/src/apply_command.rs``
- ``chatgpt/src/workspace_settings.rs``
- ``chatgpt/src/connectors.rs``
- ``chatgpt/tests/suite/apply_command_e2e.rs``
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.app_server_protocol.apps import AppInfo
from pycodex.chatgpt.apply_command import apply_diff_from_task
from pycodex.chatgpt.chatgpt_client import chatgpt_get_request
from pycodex.chatgpt.connectors import (
    connectors_for_plugin_apps,
    merge_connectors_with_accessible,
)
from pycodex.chatgpt.get_task import GetTaskResponse
from pycodex.chatgpt.workspace_settings import (
    WorkspaceSettingsCache,
    codex_plugins_enabled_for_workspace,
    encode_path_segment,
)


RUST_FIXTURE = (
    Path(__file__).parents[1]
    / "codex"
    / "codex-rs"
    / "chatgpt"
    / "tests"
    / "task_turn_fixture.json"
)


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            "PATH": __import__("os").environ.get("PATH", ""),
            "GIT_CONFIG_GLOBAL": "NUL",
            "GIT_CONFIG_NOSYSTEM": "1",
        },
    )


def _git_repo(tmp_path: Path) -> Path:
    _run_git(tmp_path, "init")
    _run_git(tmp_path, "config", "user.email", "test@example.com")
    _run_git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    _run_git(tmp_path, "add", "README.md")
    _run_git(tmp_path, "commit", "-m", "Initial commit")
    return tmp_path


def _app(app_id: str) -> AppInfo:
    return AppInfo(id=app_id, name=app_id)


def test_get_task_deserializes_rust_fixture_and_apply_creates_fibonacci(tmp_path: Path) -> None:
    response = GetTaskResponse.from_mapping(json.loads(RUST_FIXTURE.read_text(encoding="utf-8")))
    output = StringIO()

    asyncio.run(apply_diff_from_task(response, _git_repo(tmp_path), stdout=output))

    fibonacci = tmp_path / "scripts" / "fibonacci.js"
    contents = fibonacci.read_text(encoding="utf-8")
    assert "function fibonacci(n)" in contents
    assert "#!/usr/bin/env node" in contents
    assert "module.exports = fibonacci;" in contents
    assert len(contents.splitlines()) == 31
    assert output.getvalue() == "Successfully applied diff\n"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"current_diff_task_turn": None}, "No diff turn found"),
        (
            {"current_diff_task_turn": {"output_items": [{"type": "message"}]}},
            "No PR output item found",
        ),
    ],
)
def test_apply_diff_from_task_preserves_rust_errors(
    payload: dict[str, object],
    message: str,
    tmp_path: Path,
) -> None:
    response = GetTaskResponse.from_mapping(payload)
    with pytest.raises(RuntimeError, match=message):
        asyncio.run(apply_diff_from_task(response, tmp_path))


def test_workspace_settings_path_encoding_matches_rust() -> None:
    assert encode_path_segment("account-123_ABC.~") == "account-123_ABC.~"
    assert encode_path_segment("account/123 with space") == "account%2F123%20with%20space"


@dataclass(frozen=True)
class _IdToken:
    workspace: bool

    def is_workspace_account(self) -> bool:
        return self.workspace


@dataclass(frozen=True)
class _TokenData:
    account_id: str | None
    id_token: _IdToken


class _Auth:
    def __init__(
        self,
        *,
        chatgpt: bool = True,
        workspace: bool = True,
        account_id: str | None = "account/123",
    ) -> None:
        self._chatgpt = chatgpt
        self._token_data = _TokenData(account_id, _IdToken(workspace))

    def is_chatgpt_auth(self) -> bool:
        return self._chatgpt

    def get_token_data(self) -> _TokenData:
        return self._token_data


def test_workspace_settings_defaults_true_and_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, float | None]] = []

    async def fake_get(config: object, path: str, timeout: float | None = None) -> dict[str, object]:
        del config
        calls.append((path, timeout))
        return {"beta_settings": {}}

    monkeypatch.setattr(
        "pycodex.chatgpt.workspace_settings.chatgpt_get_request_with_timeout",
        fake_get,
    )
    config = SimpleNamespace(chatgpt_base_url="https://chatgpt.test/backend-api")
    cache = WorkspaceSettingsCache()
    auth = _Auth()

    assert asyncio.run(codex_plugins_enabled_for_workspace(config, auth, cache)) is True
    assert asyncio.run(codex_plugins_enabled_for_workspace(config, auth, cache)) is True
    assert calls == [("/accounts/account%2F123/settings", 10.0)]


@pytest.mark.parametrize(
    "auth",
    [None, _Auth(chatgpt=False), _Auth(workspace=False), _Auth(account_id="")],
)
def test_workspace_settings_skips_non_workspace_auth(
    auth: _Auth | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected(*args: object, **kwargs: object) -> object:
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(
        "pycodex.chatgpt.workspace_settings.chatgpt_get_request_with_timeout",
        unexpected,
    )
    config = SimpleNamespace(chatgpt_base_url="https://chatgpt.test/backend-api")
    assert asyncio.run(codex_plugins_enabled_for_workspace(config, auth, None)) is True


def test_chatgpt_get_request_builds_rust_url_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[tuple[str, dict[str, str], float | None]] = []

    class Auth:
        def uses_codex_backend(self) -> bool:
            return True

        def get_account_id(self) -> str:
            return "account-1"

        def get_token(self) -> str:
            return "access-token"

        def is_fedramp_account(self) -> bool:
            return False

    class Manager:
        async def auth(self) -> Auth:
            return Auth()

    async def auth_manager_from_config(config: object) -> Manager:
        del config
        return Manager()

    async def send(url: str, headers: dict[str, str], timeout: float | None) -> dict[str, bool]:
        requests.append((url, headers, timeout))
        return {"ok": True}

    monkeypatch.setattr(
        "pycodex.chatgpt.chatgpt_client._auth_manager_from_config",
        auth_manager_from_config,
    )
    monkeypatch.setattr("pycodex.chatgpt.chatgpt_client._send_get_json", send)
    config = SimpleNamespace(chatgpt_base_url="https://chatgpt.test/backend-api/")

    assert asyncio.run(chatgpt_get_request(config, "/wham/tasks/task-1")) == {"ok": True}
    assert requests == [
        (
            "https://chatgpt.test/backend-api/wham/tasks/task-1",
            {
                "Authorization": "Bearer access-token",
                "ChatGPT-Account-ID": "account-1",
                "OAI-Product-Sku": "codex",
                "Content-Type": "application/json",
            },
            None,
        )
    ]


def test_merge_connectors_matches_rust_loaded_and_loading_rules() -> None:
    loaded = merge_connectors_with_accessible(
        [_app("alpha")],
        [_app("alpha"), _app("beta")],
        all_connectors_loaded=True,
    )
    loading = merge_connectors_with_accessible(
        [_app("alpha")],
        [_app("alpha"), _app("beta")],
        all_connectors_loaded=False,
    )

    assert [(app.id, app.is_accessible) for app in loaded] == [("alpha", True)]
    assert [(app.id, app.is_accessible) for app in loading] == [
        ("alpha", True),
        ("beta", True),
    ]


def test_connectors_for_plugin_apps_adds_missing_and_filters_disallowed() -> None:
    connectors = connectors_for_plugin_apps(
        [_app("alpha"), _app("beta")],
        ["alpha", "gmail", "asdk_app_6938a94a61d881918ef32cb999ff937c"],
    )
    assert [app.id for app in connectors] == ["alpha", "gmail"]
