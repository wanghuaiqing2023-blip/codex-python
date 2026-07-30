"""Real CLI, auth-file, HTTP, and Git coverage for ``codex apply``."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from pycodex.tui.local_chatgpt_auth import fake_jwt

pytestmark = pytest.mark.e2e

RUST_FIXTURE = (
    Path(__file__).parents[3]
    / "codex"
    / "codex-rs"
    / "chatgpt"
    / "tests"
    / "task_turn_fixture.json"
)


class _TaskServer:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body
        self.requests: list[tuple[str, dict[str, str]]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner.requests.append((self.path, dict(self.headers.items())))
                self.send_response(owner.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(owner.body)))
                self.end_headers()
                self.wfile.write(owner.body)

            def log_message(self, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> "_TaskServer":
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            **os.environ,
            "GIT_CONFIG_GLOBAL": "NUL",
            "GIT_CONFIG_NOSYSTEM": "1",
        },
    )


def _prepare_repo(repo: Path) -> None:
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "Initial commit")


def _environment(codex_home: Path) -> dict[str, str]:
    id_token = fake_jwt(
        email="fixture@example.com",
        account_id="fixture-account",
        plan_type="business",
    ).rstrip(".") + ".fixture-signature"
    auth = {
        "auth_mode": "ChatGPT",
        "tokens": {
            "access_token": "fixture-access-token",
            "refresh_token": "fixture-refresh-token",
            "account_id": "fixture-account",
            "id_token": id_token,
        },
        "last_refresh": "2026-07-28T00:00:00Z",
    }
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(json.dumps(auth), encoding="utf-8")
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    project_root = str(Path(__file__).parents[3])
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        project_root
        if not existing_pythonpath
        else os.pathsep.join((project_root, existing_pythonpath))
    )
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        env.pop(key, None)
    return env


def _run_apply(repo: Path, home: Path, base_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pycodex",
            "-c",
            f'chatgpt_base_url="{base_url}"',
            "apply",
            "task-e2e",
        ],
        cwd=repo,
        env=_environment(home),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_apply_uses_real_chatgpt_auth_http_and_git_chain(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _prepare_repo(repo)
    with _TaskServer(200, RUST_FIXTURE.read_bytes()) as server:
        completed = _run_apply(repo, tmp_path / "codex-home", server.base_url)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "Successfully applied diff\n"
    contents = (repo / "scripts" / "fibonacci.js").read_text(encoding="utf-8")
    assert "function fibonacci(n)" in contents
    assert len(contents.splitlines()) == 31
    assert len(server.requests) == 1
    path, headers = server.requests[0]
    assert path == "/wham/tasks/task-e2e"
    assert headers["Authorization"] == "Bearer fixture-access-token"
    assert headers["Chatgpt-Account-Id"] == "fixture-account"
    assert headers["Oai-Product-Sku"] == "codex"


def test_apply_reports_chatgpt_http_error_without_mutating_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _prepare_repo(repo)
    with _TaskServer(401, b'{"error":"denied"}') as server:
        completed = _run_apply(repo, tmp_path / "codex-home", server.base_url)

    assert completed.returncode == 1
    assert "Request failed with status 401" in completed.stderr
    assert not (repo / "scripts" / "fibonacci.js").exists()
