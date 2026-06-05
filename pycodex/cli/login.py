"""Helpers for login/logout/status authentication persistence."""

from __future__ import annotations

import json
import base64
import secrets
from dataclasses import dataclass, field
import errno
import os
import socket
from datetime import datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import webbrowser
import time
from typing import Any, Mapping

from pycodex.utils.home_dir import find_codex_home

AUTH_FILE = "auth.json"

AUTH_MODE_API_KEY = "apiKey"
AUTH_MODE_CHATGPT = "chatgpt"
AUTH_MODE_CHATGPT_AUTH_TOKENS = "chatgptAuthTokens"
AUTH_MODE_AGENT_IDENTITY = "agentIdentity"

_CHATGPT_LOGIN_BASE = "https://auth.openai.com"
_CHATGPT_LOGIN_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_CHATGPT_LOGIN_SCOPE = (
    "openid profile email offline_access api.connectors.read api.connectors.invoke"
)
_CHATGPT_LOGIN_CALLBACK_PATH = "/auth/callback"
_CHATGPT_LOGIN_WAIT_SECONDS = 5
_CHATGPT_LOGIN_DEFAULT_PORT = 1455
_CHATGPT_LOGIN_FALLBACK_PORT = 1457


def _base64url_bytes(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _build_pkce() -> tuple[str, str]:
    verifier = _base64url_bytes(secrets.token_bytes(64))[:128]
    challenge = _base64url_bytes(sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def _build_login_authorize_url(
    *,
    issuer: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    state: str,
) -> str:
    query = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": _CHATGPT_LOGIN_SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "state": state,
        "originator": "codex_cli_python",
    }
    return f"{issuer.rstrip('/')}/oauth/authorize?{urlencode(query)}"


@dataclass
class _ChatgptCallbackState:
    expected_state: str
    code: str | None = None
    error: str | None = None
    error_description: str | None = None
    error_message: str | None = None
    done: threading.Event = field(default_factory=threading.Event)


def _oauth_callback_error_message(error_code: str, error_description: str | None) -> str:
    if (
        error_code == "access_denied"
        and error_description is not None
        and "missing_codex_entitlement" in error_description.lower()
    ):
        return (
            "Codex is not enabled for your workspace. "
            "Contact your workspace administrator to request access to Codex."
        )

    if error_description is not None and error_description.strip():
        return f"Sign-in failed: {error_description.strip()}"
    return f"Sign-in failed: {error_code}"


def _exchange_authorization_code(
    *,
    issuer: str,
    client_id: str,
    redirect_uri: str,
    code_verifier: str,
    code: str,
) -> dict[str, str]:
    payload = urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier,
        }
    ).encode("utf-8")
    request = Request(
        url=f"{issuer.rstrip('/')}/oauth/token",
        data=payload,
        method="POST",
    )
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    request.add_header("User-Agent", "pycodex")

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        _drain_http_error(exc)
        raise RuntimeError(f"token exchange failed with status {exc.code}: {body.strip() or exc.reason}")
    except URLError as exc:
        raise RuntimeError(f"token exchange failed: {exc}")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"token exchange returned invalid JSON: {exc}")

    if not isinstance(payload, dict):
        raise RuntimeError("token exchange returned an unexpected response.")

    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise RuntimeError("token exchange did not return an access token.")

    tokens: dict[str, str] = {"access_token": access_token.strip()}
    if isinstance(payload.get("id_token"), str) and payload["id_token"].strip():
        tokens["id_token"] = payload["id_token"].strip()
    if isinstance(payload.get("refresh_token"), str) and payload["refresh_token"].strip():
        tokens["refresh_token"] = payload["refresh_token"].strip()
    return tokens


def _drain_http_error(error: HTTPError) -> None:
    fp = getattr(error, "fp", None)
    if fp is None:
        return
    closer = getattr(fp, "close", None)
    if callable(closer):
        try:
            closer()
        except OSError:
            pass
        except Exception:
            pass
    setattr(error, "fp", None)


def _extract_auth_claims_from_jwt(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        return {}

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + padding)
    except Exception:
        return {}

    try:
        raw_claims = json.loads(decoded.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, ValueError):
        return {}

    if not isinstance(raw_claims, dict):
        return {}
    nested = raw_claims.get("https://api.openai.com/auth")
    if isinstance(nested, dict):
        return nested
    return {}


def _make_callback_handler(state: _ChatgptCallbackState):
    class _CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # type: ignore[override]
            parsed = urlparse(self.path)
            if parsed.path == "/cancel":
                state.error = "login_cancelled"
                state.error_description = None
                state.error_message = "Login cancelled"
                state.done.set()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<html><body><h1>Login cancelled</h1></body></html>")
                return

            if parsed.path == "/success":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<html><body><h1>Login completed</h1></body></html>")
                return

            if parsed.path != _CHATGPT_LOGIN_CALLBACK_PATH:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not Found")
                return

            params = parse_qs(parsed.query)
            received_state = (params.get("state", [""])[0] or "").strip()
            if received_state != state.expected_state:
                state.error = "state_mismatch"
                state.error_description = "OAuth callback state mismatch"
                state.error_message = "State mismatch"
                state.done.set()
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch")
                return

            error_code = (params.get("error", [""])[0] or "").strip()
            if error_code:
                state.error = error_code
                state.error_description = (params.get("error_description", [""])[0] or "").strip()
                state.error_message = _oauth_callback_error_message(
                    state.error,
                    state.error_description,
                )
                state.done.set()
                self.send_response(400)
                self.end_headers()
                message = _oauth_callback_error_message(
                    state.error,
                    state.error_description or None,
                )
                self.wfile.write(message.encode("utf-8"))
                return

            code = (params.get("code", [""])[0] or "").strip()
            if not code:
                state.error = "missing_code"
                state.error_description = "Missing authorization code"
                state.error_message = "Missing authorization code."
                state.done.set()
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing authorization code")
                return


            state.code = code
            state.done.set()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Login completed</h1><p>You may close this window.</p></body></html>",
            )

        def log_message(self, format: str, *args):  # type: ignore[override]
            return

    return _CallbackHandler


@dataclass(frozen=True)
class AuthDotJson:
    auth_mode: str | None = None
    openai_api_key: str | None = None
    tokens: dict[str, Any] | None = None
    last_refresh: str | None = None
    agent_identity: str | None = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "AuthDotJson":
        return cls(
            auth_mode=_as_optional_str(raw.get("auth_mode")),
            openai_api_key=_as_optional_str(raw.get("OPENAI_API_KEY")),
            tokens=raw.get("tokens") if isinstance(raw.get("tokens"), dict) else None,
            last_refresh=_as_optional_str(raw.get("last_refresh")),
            agent_identity=_as_optional_str(raw.get("agent_identity")),
        )

    def to_mapping(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.auth_mode is not None:
            payload["auth_mode"] = self.auth_mode
        if self.openai_api_key is not None:
            payload["OPENAI_API_KEY"] = self.openai_api_key
        if self.tokens is not None:
            payload["tokens"] = self.tokens
        if self.last_refresh is not None:
            payload["last_refresh"] = self.last_refresh
        if self.agent_identity is not None:
            payload["agent_identity"] = self.agent_identity
        return payload


def auth_file_path(*, codex_home: Path | None = None) -> Path:
    home = find_codex_home() if codex_home is None else Path(codex_home)
    return home / AUTH_FILE


def read_auth_json(*, codex_home: Path | None = None) -> AuthDotJson | None:
    path = auth_file_path(codex_home=codex_home)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid auth file format.") from exc
    if not isinstance(raw, dict):
        raise ValueError("Invalid auth file format.")
    return AuthDotJson.from_mapping(raw)


def write_auth_json(auth: AuthDotJson, *, codex_home: Path | None = None) -> None:
    path = auth_file_path(codex_home=codex_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(auth.to_mapping(), indent=2), encoding="utf-8")
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def delete_auth_file(*, codex_home: Path | None = None) -> bool:
    path = auth_file_path(codex_home=codex_home)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def safe_format_key(key: str) -> str:
    if len(key) <= 13:
        return "***"
    return f"{key[:8]}***{key[-5:]}"


def resolve_auth_mode(auth: AuthDotJson) -> str:
    if auth.auth_mode is not None:
        mode = auth.auth_mode.replace("-", "").replace("_", "").lower()
        if mode == "apikey":
            return AUTH_MODE_API_KEY
        if mode == "chatgptauthtokens":
            return AUTH_MODE_CHATGPT_AUTH_TOKENS
        if mode == "agentidentity":
            return AUTH_MODE_AGENT_IDENTITY
        if mode == "chatgpt":
            return AUTH_MODE_CHATGPT
        raise ValueError(f"Unknown auth_mode value: {auth.auth_mode}")

    if auth.openai_api_key is not None:
        return AUTH_MODE_API_KEY
    return AUTH_MODE_CHATGPT


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    value = value.strip()
    return value if value else None


def run_chatgpt_login(
    *,
    stdout,
    stderr,
    issuer: str | None = None,
    client_id: str | None = None,
    login_ports: tuple[int, int] = (_CHATGPT_LOGIN_DEFAULT_PORT, _CHATGPT_LOGIN_FALLBACK_PORT),
) -> int:
    _issuer = _CHATGPT_LOGIN_BASE if issuer is None else issuer
    _client_id = _CHATGPT_LOGIN_CLIENT_ID if client_id is None else client_id
    callback_state = _ChatgptCallbackState(expected_state=_base64url_bytes(secrets.token_bytes(32)))
    verifier, challenge = _build_pkce()
    pkce = {
        "code_verifier": verifier,
        "code_challenge": challenge,
    }

    server: ThreadingHTTPServer | None = None
    server_thread = None
    try:
        for candidate_port in login_ports:
            try:
                server = ThreadingHTTPServer(("127.0.0.1", candidate_port), _make_callback_handler(callback_state))
                port = candidate_port
                break
            except OSError as exc:
                if exc.errno == errno.EADDRINUSE:
                    if candidate_port == _CHATGPT_LOGIN_DEFAULT_PORT:
                        try:
                            with socket.create_connection(("127.0.0.1", candidate_port), timeout=1) as sock:
                                sock.sendall(b"GET /cancel HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
                        except Exception:
                            print(f"Warning: failed to cancel stale login server on port {candidate_port}", file=stderr)
                        time.sleep(0.2)
                        continue
                    print(f"Error logging in: port {candidate_port} is already in use.", file=stderr)
                    return 64
                raise
        else:
            print("Error logging in: could not bind local login server port.", file=stderr)
            return 64
        port = server.server_address[1]
        redirect_uri = f"http://127.0.0.1:{port}{_CHATGPT_LOGIN_CALLBACK_PATH}"
        auth_url = _build_login_authorize_url(
            issuer=_issuer,
            client_id=_client_id,
            redirect_uri=redirect_uri,
            code_challenge=challenge,
            state=callback_state.expected_state,
        )

        print(
            f"Starting local login server on http://localhost:{port}.",
            file=stderr,
        )
        print("If your browser did not open, navigate to this URL to authenticate:", file=stderr)
        print()
        print(auth_url, file=stderr)
        print(
            "\nOn a remote or headless machine? Use `codex login --device-auth` instead.",
            file=stderr,
        )

        server_thread = threading.Thread(daemon=True)
        serve_forever = getattr(server, "serve_forever", None)
        if callable(serve_forever):
            server_thread = threading.Thread(target=serve_forever, daemon=True)
        server_thread.start()

        try:
            webbrowser.open(auth_url)
        except Exception as exc:
            print(f"Browser did not open automatically: {exc}", file=stderr)

        if not server or not server_thread:
            return 64

        if not server_thread.is_alive():
            print("Error logging in: local login server stopped unexpectedly.", file=stderr)
            return 64

        if not _wait_for_callback(callback_state, _CHATGPT_LOGIN_WAIT_SECONDS):
            print("Error logging in: login callback was not completed in time.", file=stderr)
            return 64

        if callback_state.error:
            if callback_state.error_message:
                message = callback_state.error_message
            elif callback_state.error and callback_state.error_description:
                message = f"{callback_state.error}: {callback_state.error_description}"
            else:
                message = callback_state.error
            print(f"Error logging in: {message}", file=stderr)
            return 64

        if not callback_state.code:
            print("Error logging in: missing authorization code from callback.", file=stderr)
            return 64

        tokens = _exchange_authorization_code(
            issuer=_issuer,
            client_id=_client_id,
            redirect_uri=redirect_uri,
            code_verifier=pkce["code_verifier"],
            code=callback_state.code,
        )
        id_token = tokens.get("id_token")
        if isinstance(id_token, str):
            claims = _extract_auth_claims_from_jwt(id_token)
            account_id = claims.get("chatgpt_account_id")
            if isinstance(account_id, str) and account_id:
                tokens["account_id"] = account_id
        now = datetime.now(timezone.utc).isoformat()
        write_auth_json(
            AuthDotJson(
                auth_mode=AUTH_MODE_CHATGPT,
                tokens=tokens,
                last_refresh=now,
            )
        )
        print("Successfully logged in", file=stderr)
        return 0
    except RuntimeError as exc:
        print(f"Error logging in: {exc}", file=stderr)
        return 64
    except Exception as exc:
        print(f"Error logging in: {exc}", file=stderr)
        return 64
    finally:
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        if server_thread is not None and server_thread.is_alive():
            server_thread.join(timeout=1)


def _wait_for_callback(callback_state: _ChatgptCallbackState, timeout_seconds: int) -> bool:
    return callback_state.done.wait(timeout_seconds)
