"""Port of Rust ``codex-login::server``.

Rust source:
- ``codex/codex-rs/login/src/server.rs``
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping

from pycodex.login.auth.revoke import revoke_auth_tokens, should_revoke_auth_tokens
from pycodex.login.auth.storage import AuthDotJson, create_auth_storage
from pycodex.login.pkce import PkceCodes, generate_pkce
from pycodex.login.token_data import TokenData, parse_chatgpt_jwt_claims


DEFAULT_ISSUER = "https://auth.openai.com"
DEFAULT_PORT = 1455
FALLBACK_PORT = 1457
CLIENT_SCOPE = "openid profile email offline_access api.connectors.read api.connectors.invoke"
REDACTED_URL_VALUE = "<redacted>"
SENSITIVE_URL_QUERY_KEYS = {
    "access_token",
    "api_key",
    "client_secret",
    "code",
    "code_verifier",
    "id_token",
    "key",
    "refresh_token",
    "requested_token",
    "state",
    "subject_token",
    "token",
}


@dataclass(frozen=True)
class ServerOptions:
    codex_home: Path | None = None
    client_id: str = ""
    issuer: str = DEFAULT_ISSUER
    port: int = DEFAULT_PORT
    open_browser: bool = True
    force_state: str | None = None
    forced_chatgpt_workspace_id: list[str] | str | None = None
    codex_streamlined_login: bool = False
    cli_auth_credentials_store_mode: str = "file"

    @classmethod
    def new(
        cls,
        codex_home: str | Path,
        client_id: str,
        forced_chatgpt_workspace_id: list[str] | None,
        cli_auth_credentials_store_mode: str,
    ) -> "ServerOptions":
        return cls(
            codex_home=Path(codex_home),
            client_id=client_id,
            forced_chatgpt_workspace_id=forced_chatgpt_workspace_id,
            cli_auth_credentials_store_mode=cli_auth_credentials_store_mode,
        )


@dataclass(frozen=True)
class ExchangedTokens:
    id_token: str
    access_token: str
    refresh_token: str


@dataclass(frozen=True)
class TokenEndpointErrorDetail:
    error_code: str | None
    error_message: str | None
    display_message: str

    def __str__(self) -> str:
        return self.display_message


class ShutdownHandle:
    def __init__(self, server: ThreadingHTTPServer | None = None) -> None:
        self._server = server
        self._event = threading.Event()

    def shutdown(self) -> None:
        self._event.set()
        if self._server is not None:
            self._server.shutdown()

    @property
    def is_shutdown(self) -> bool:
        return self._event.is_set()


@dataclass
class LoginServer:
    auth_url: str
    actual_port: int
    server_handle: threading.Thread | None
    shutdown_handle: ShutdownHandle
    result_event: threading.Event
    result_error: BaseException | None = None

    async def block_until_done(self) -> None:
        while not self.result_event.wait(0.05):
            await asyncio.sleep(0)
        if self.result_error is not None:
            raise OSError(self.result_error)

    def cancel(self) -> None:
        self.shutdown_handle.shutdown()

    def cancel_handle(self) -> ShutdownHandle:
        return self.shutdown_handle


def build_authorize_url(
    issuer: str,
    client_id: str,
    redirect_uri: str,
    pkce: PkceCodes,
    state: str,
    forced_chatgpt_workspace_ids: list[str] | tuple[str, ...] | str | None = None,
    *,
    originator: str = "codex_cli_python",
) -> str:
    query = [
        ("response_type", "code"),
        ("client_id", client_id),
        ("redirect_uri", redirect_uri),
        ("scope", CLIENT_SCOPE),
        ("code_challenge", pkce.code_challenge),
        ("code_challenge_method", "S256"),
        ("id_token_add_organizations", "true"),
        ("codex_cli_simplified_flow", "true"),
        ("state", state),
        ("originator", originator),
    ]
    workspace_ids = _workspace_ids(forced_chatgpt_workspace_ids)
    if workspace_ids:
        query.append(("allowed_workspace_id", ",".join(workspace_ids)))
    return f"{issuer.rstrip('/')}/oauth/authorize?{urllib.parse.urlencode(query)}"


def generate_state() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


def run_login_server(opts: ServerOptions) -> LoginServer:
    pkce = generate_pkce()
    state = opts.force_state or generate_state()
    server = _bind_http_server(opts.port)
    actual_port = int(server.server_address[1])
    redirect_uri = f"http://localhost:{actual_port}/auth/callback"
    auth_url = build_authorize_url(
        opts.issuer,
        opts.client_id,
        redirect_uri,
        pkce,
        state,
        opts.forced_chatgpt_workspace_id,
    )
    result_event = threading.Event()
    result_holder: dict[str, BaseException | None] = {"error": None}
    server.RequestHandlerClass = _make_callback_handler(
        opts,
        redirect_uri,
        pkce,
        actual_port,
        state,
        result_event,
        result_holder,
    )
    shutdown_handle = ShutdownHandle(server)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if opts.open_browser:
        webbrowser.open(auth_url)
    return LoginServer(auth_url, actual_port, thread, shutdown_handle, result_event, result_holder["error"])


def _bind_http_server(port: int) -> ThreadingHTTPServer:
    try:
        return ThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
    except OSError:
        if port == DEFAULT_PORT:
            return ThreadingHTTPServer(("127.0.0.1", FALLBACK_PORT), BaseHTTPRequestHandler)
        raise


def _make_callback_handler(
    opts: ServerOptions,
    redirect_uri: str,
    pkce: PkceCodes,
    actual_port: int,
    state: str,
    result_event: threading.Event,
    result_holder: dict[str, BaseException | None],
):
    class LoginCallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # type: ignore[override]
            status, headers, body, final_error = process_request_sync(
                self.path,
                opts,
                redirect_uri,
                pkce,
                actual_port,
                state,
            )
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
            if final_error is not None:
                result_holder["error"] = final_error
                result_event.set()
            elif self.path.startswith("/success"):
                result_event.set()

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    return LoginCallbackHandler


def process_request_sync(
    url_raw: str,
    opts: ServerOptions,
    redirect_uri: str,
    pkce: PkceCodes,
    actual_port: int,
    state: str,
) -> tuple[int, dict[str, str], bytes, BaseException | None]:
    parsed = urllib.parse.urlsplit(f"http://localhost{url_raw}")
    if parsed.path == "/cancel":
        return 200, {}, b"Login cancelled", InterruptedError("Login cancelled")
    if parsed.path == "/success":
        return 200, {"Content-Type": "text/html; charset=utf-8", "Connection": "close"}, b"Login complete", None
    if parsed.path != "/auth/callback":
        return 404, {}, b"Not Found", None

    params = {key: values[-1] for key, values in urllib.parse.parse_qs(parsed.query, keep_blank_values=True).items()}
    if params.get("state") != state:
        return 400, {}, b"State mismatch", None
    if error_code := params.get("error"):
        message = oauth_callback_error_message(error_code, params.get("error_description"))
        return login_error_response(message, PermissionError, error_code, params.get("error_description"))
    code = params.get("code")
    if not code:
        return login_error_response(
            "Missing authorization code. Sign-in could not be completed.",
            ValueError,
            "missing_authorization_code",
            None,
        )

    try:
        tokens = asyncio.run(exchange_code_for_tokens(opts.issuer, opts.client_id, redirect_uri, pkce, code))
        workspace_error = ensure_workspace_allowed(_workspace_ids(opts.forced_chatgpt_workspace_id), tokens.id_token)
        if workspace_error:
            return login_error_response(workspace_error, PermissionError, "workspace_restriction", None)
        if opts.codex_home is not None:
            asyncio.run(
                persist_tokens_async(
                    opts.codex_home,
                    None,
                    tokens.id_token,
                    tokens.access_token,
                    tokens.refresh_token,
                    opts.cli_auth_credentials_store_mode,
                )
            )
    except BaseException as exc:
        return login_error_response(f"Token exchange failed: {exc}", OSError, "token_exchange_failed", None)

    success_url = compose_success_url(
        actual_port,
        opts.issuer,
        tokens.id_token,
        tokens.access_token,
        opts.codex_streamlined_login,
    )
    return 302, {"Location": success_url}, b"", None


async def exchange_code_for_tokens(
    issuer: str,
    client_id: str,
    redirect_uri: str,
    pkce: PkceCodes,
    code: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    timeout: float = 30.0,
) -> ExchangedTokens:
    def request() -> ExchangedTokens:
        body = urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": pkce.code_verifier,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{issuer.rstrip('/')}/oauth/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with opener(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            detail = parse_token_endpoint_error(raw)
            raise OSError(f"token endpoint returned status {exc.code}: {detail}") from exc
        except Exception as exc:
            raise OSError(exc) from exc
        payload = json.loads(raw)
        if not isinstance(payload, Mapping):
            raise OSError("token exchange returned an unexpected response.")
        return ExchangedTokens(
            id_token=_expect_str(payload.get("id_token")),
            access_token=_expect_str(payload.get("access_token")),
            refresh_token=_expect_str(payload.get("refresh_token")),
        )

    return await asyncio.to_thread(request)


async def persist_tokens_async(
    codex_home: str | Path,
    api_key: str | None,
    id_token: str,
    access_token: str,
    refresh_token: str,
    auth_credentials_store_mode: str = "file",
) -> None:
    storage = create_auth_storage(codex_home, auth_credentials_store_mode)
    try:
        previous_auth = storage.load()
    except Exception:
        previous_auth = None
    parsed_id_token = parse_chatgpt_jwt_claims(id_token)
    claims = jwt_auth_claims(id_token)
    auth = AuthDotJson(
        auth_mode="chatgpt",
        openai_api_key=api_key,
        tokens=TokenData(
            id_token=parsed_id_token,
            access_token=access_token,
            refresh_token=refresh_token,
            account_id=_optional_str(claims.get("chatgpt_account_id")),
        ),
        last_refresh=datetime.now(timezone.utc),
    )
    storage.save(auth)
    if should_revoke_auth_tokens(previous_auth, auth):
        try:
            await revoke_auth_tokens(previous_auth)
        except Exception:
            pass


def compose_success_url(
    port: int,
    issuer: str,
    id_token: str,
    access_token: str,
    codex_streamlined_login: bool = False,
) -> str:
    token_claims = jwt_auth_claims(id_token)
    access_claims = jwt_auth_claims(access_token)
    completed_onboarding = bool(token_claims.get("completed_platform_onboarding", False))
    is_org_owner = bool(token_claims.get("is_org_owner", False))
    params = {
        "id_token": id_token,
        "needs_setup": str((not completed_onboarding) and is_org_owner).lower(),
        "org_id": str(token_claims.get("organization_id") or ""),
        "project_id": str(token_claims.get("project_id") or ""),
        "plan_type": str(access_claims.get("chatgpt_plan_type") or ""),
        "platform_url": "https://platform.openai.com" if issuer == DEFAULT_ISSUER else "https://platform.api.openai.org",
    }
    if codex_streamlined_login:
        params["codex_streamlined_login"] = "true"
    return f"http://localhost:{port}/success?{urllib.parse.urlencode(params)}"


def jwt_auth_claims(jwt: str) -> dict[str, Any]:
    parts = jwt.split(".")
    if len(parts) < 3 or not all(parts[:3]):
        return {}
    padding = "=" * (-len(parts[1]) % 4)
    try:
        payload = base64.urlsafe_b64decode((parts[1] + padding).encode("ascii"))
        claims = json.loads(payload.decode("utf-8"))
    except Exception:
        return {}
    if not isinstance(claims, Mapping):
        return {}
    auth = claims.get("https://api.openai.com/auth")
    return dict(auth) if isinstance(auth, Mapping) else {}


def ensure_workspace_allowed(expected: list[str] | tuple[str, ...] | str | None, id_token: str) -> str | None:
    workspace_ids = _workspace_ids(expected)
    if workspace_ids is None:
        return None
    actual = jwt_auth_claims(id_token).get("chatgpt_account_id")
    if not isinstance(actual, str):
        return "Login is restricted to a specific workspace, but the token did not include an chatgpt_account_id claim."
    if actual in workspace_ids:
        return None
    return f"Login is restricted to workspace id(s) {', '.join(workspace_ids)}."


def login_error_response(
    message: str,
    error_type: type[BaseException],
    error_code: str | None,
    error_description: str | None,
) -> tuple[int, dict[str, str], bytes, BaseException]:
    return (
        200,
        {"Content-Type": "text/html; charset=utf-8", "Connection": "close"},
        render_login_error_page(message, error_code, error_description),
        error_type(message),
    )


def is_missing_codex_entitlement_error(error_code: str, error_description: str | None) -> bool:
    return error_code == "access_denied" and error_description is not None and "missing_codex_entitlement" in error_description.lower()


def oauth_callback_error_message(error_code: str, error_description: str | None) -> str:
    if is_missing_codex_entitlement_error(error_code, error_description):
        return "Codex is not enabled for your workspace. Contact your workspace administrator to request access to Codex."
    if error_description is not None and error_description.strip():
        return f"Sign-in failed: {error_description.strip()}"
    return f"Sign-in failed: {error_code}"


def parse_token_endpoint_error(body: str) -> TokenEndpointErrorDetail:
    trimmed = body.strip()
    if not trimmed:
        return TokenEndpointErrorDetail(None, None, "unknown error")
    try:
        parsed = json.loads(trimmed)
    except json.JSONDecodeError:
        return TokenEndpointErrorDetail(None, None, trimmed)
    if isinstance(parsed, Mapping):
        error_code = _json_error_code(parsed)
        description = parsed.get("error_description")
        if isinstance(description, str) and description.strip():
            return TokenEndpointErrorDetail(error_code, description, description)
        error_obj = parsed.get("error")
        if isinstance(error_obj, Mapping):
            message = error_obj.get("message")
            if isinstance(message, str) and message.strip():
                return TokenEndpointErrorDetail(error_code, message, message)
        if error_code is not None:
            return TokenEndpointErrorDetail(error_code, None, error_code)
    return TokenEndpointErrorDetail(None, None, trimmed)


def _json_error_code(parsed: Mapping[str, Any]) -> str | None:
    error = parsed.get("error")
    if isinstance(error, str) and error.strip():
        return error
    if isinstance(error, Mapping):
        code = error.get("code")
        if isinstance(code, str) and code.strip():
            return code
    return None


def render_login_error_page(message: str, error_code: str | None = None, error_description: str | None = None) -> bytes:
    code = error_code or "unknown_error"
    if is_missing_codex_entitlement_error(code, error_description):
        title = "You do not have access to Codex"
        display_message = "This account is not currently authorized to use Codex in this workspace."
        display_description = "Contact your workspace administrator to request access to Codex."
        help_text = "Contact your workspace administrator to get access to Codex, then return to Codex and try again."
    else:
        title = "Sign-in could not be completed"
        display_message = message
        display_description = error_description or message
        help_text = "Return to Codex to retry, switch accounts, or contact your workspace admin if access is restricted."
    body = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html_escape(title)}</title></head>
<body>
<h1>{html_escape(title)}</h1>
<p>{html_escape(display_message)}</p>
<p>{html_escape(code)}</p>
<p>{html_escape(display_description)}</p>
<p>{html_escape(help_text)}</p>
</body></html>"""
    return body.encode("utf-8")


def html_escape(input: str) -> str:
    return html.escape(input, quote=True).replace("&#x27;", "&#39;")


async def obtain_api_key(
    issuer: str,
    client_id: str,
    id_token: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    timeout: float = 30.0,
) -> str:
    def request() -> str:
        body = urllib.parse.urlencode(
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "client_id": client_id,
                "requested_token": "openai-api-key",
                "subject_token": id_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{issuer.rstrip('/')}/oauth/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with opener(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
        token = payload.get("access_token") if isinstance(payload, Mapping) else None
        return _expect_str(token)

    return await asyncio.to_thread(request)


def redact_sensitive_query_value(key: str, value: str) -> str:
    if key.lower() in SENSITIVE_URL_QUERY_KEYS:
        return REDACTED_URL_VALUE
    return value


def sanitize_url_for_logging(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return "<invalid-url>"
    hostname = parsed.hostname or ""
    netloc = hostname
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    query = urllib.parse.urlencode(
        [
            (key, redact_sensitive_query_value(key, value))
            for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        ]
    )
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, query, ""))


def _workspace_ids(value: list[str] | tuple[str, ...] | str | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _expect_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("expected string")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise TypeError("expected optional string")


__all__ = [
    "CLIENT_SCOPE",
    "DEFAULT_ISSUER",
    "DEFAULT_PORT",
    "FALLBACK_PORT",
    "REDACTED_URL_VALUE",
    "SENSITIVE_URL_QUERY_KEYS",
    "ExchangedTokens",
    "LoginServer",
    "ServerOptions",
    "ShutdownHandle",
    "TokenEndpointErrorDetail",
    "build_authorize_url",
    "compose_success_url",
    "ensure_workspace_allowed",
    "exchange_code_for_tokens",
    "generate_state",
    "html_escape",
    "is_missing_codex_entitlement_error",
    "jwt_auth_claims",
    "login_error_response",
    "oauth_callback_error_message",
    "obtain_api_key",
    "parse_token_endpoint_error",
    "persist_tokens_async",
    "process_request_sync",
    "redact_sensitive_query_value",
    "render_login_error_page",
    "run_login_server",
    "sanitize_url_for_logging",
]
