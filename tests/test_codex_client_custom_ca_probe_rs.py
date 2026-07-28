"""Rust-derived tests for ``codex-client/src/bin/custom_ca_probe.rs``."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


FIXTURES = Path("codex/codex-rs/codex-client/tests/fixtures")
TEST_CERT = FIXTURES / "test-ca.pem"


def _probe_env(**updates: str) -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "ALL_PROXY",
        "CODEX_CA_CERTIFICATE",
        "CODEX_CUSTOM_CA_PROBE_PROXY",
        "CODEX_CUSTOM_CA_PROBE_TLS13",
        "CODEX_CUSTOM_CA_PROBE_URL",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "all_proxy",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    ):
        env.pop(key, None)
    env.update(updates)
    return env


def _run_probe(**env_updates: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "-m", "pycodex.codex_client.bin.custom_ca_probe"],
        cwd=Path.cwd(),
        env=_probe_env(**env_updates),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_custom_ca_probe_uses_codex_ca_certificate() -> None:
    # Rust: ca_env.rs::uses_codex_ca_cert_env launches custom_ca_probe.
    result = _run_probe(CODEX_CA_CERTIFICATE=str(TEST_CERT.resolve()))

    assert result.returncode == 0
    assert result.stdout == "ok\n"
    assert result.stderr == ""


def test_custom_ca_probe_prefers_codex_ca_over_ssl_cert_file(tmp_path: Path) -> None:
    # Rust: ca_env.rs::prefers_codex_ca_cert_over_ssl_cert_file.
    bad_path = tmp_path / "bad.pem"
    bad_path.write_text("")

    result = _run_probe(
        CODEX_CA_CERTIFICATE=str(TEST_CERT.resolve()),
        SSL_CERT_FILE=str(bad_path),
    )

    assert result.returncode == 0
    assert result.stdout == "ok\n"


def test_custom_ca_probe_rejects_empty_pem_with_hint(tmp_path: Path) -> None:
    # Rust: ca_env.rs::rejects_empty_pem_file_with_hint.
    empty_path = tmp_path / "empty.pem"
    empty_path.write_text("")

    result = _run_probe(CODEX_CA_CERTIFICATE=str(empty_path))

    assert result.returncode == 1
    assert "no certificates found in PEM file" in result.stderr
    assert "CODEX_CA_CERTIFICATE" in result.stderr
    assert "SSL_CERT_FILE" in result.stderr


def test_custom_ca_probe_posts_expected_token_exchange_body() -> None:
    # Rust: post_probe_request sends the OAuth token-exchange probe body.
    received: list[tuple[str, bytes, str | None]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            received.append(
                (
                    self.path,
                    self.rfile.read(length),
                    self.headers.get("Content-Type"),
                )
            )
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        result = _run_probe(
            CODEX_CUSTOM_CA_PROBE_URL=f"http://{host}:{port}/oauth/token"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.returncode == 0
    assert result.stdout == "ok\n"
    assert received == [
        (
            "/oauth/token",
            b"grant_type=authorization_code&code=test",
            "application/x-www-form-urlencoded",
        )
    ]


def test_custom_ca_probe_rejects_unexpected_response_body() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", "3")
            self.end_headers()
            self.wfile.write(b"bad")

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        result = _run_probe(
            CODEX_CUSTOM_CA_PROBE_URL=f"http://{host}:{port}/oauth/token"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.returncode == 1
    assert "probe response body mismatch: bad" in result.stderr
