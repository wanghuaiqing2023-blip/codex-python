"""Interactive MCP OAuth authorization-code login."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import threading
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from pycodex.config.types import OAuthCredentialsStoreMode

from .oauth import (
    OAuthTokenResponse,
    StoredOAuthTokens,
    WrappedOAuthTokenResponse,
    compute_expires_at_millis,
    save_oauth_tokens,
)
from .utils import build_default_headers


def _oauth_discovery_urls(server_url: str) -> tuple[str, ...]:
    parsed = urllib.parse.urlsplit(server_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid MCP OAuth server URL: {server_url}")
    trimmed = parsed.path.strip("/")
    canonical = "/.well-known/oauth-authorization-server"
    paths = (
        (canonical,)
        if not trimmed
        else (
            f"{canonical}/{trimmed}",
            f"/{trimmed}/.well-known/oauth-authorization-server",
            canonical,
        )
    )
    return tuple(
        urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
        for path in dict.fromkeys(paths)
    )


class OAuthProviderError(Exception):
    def __init__(
        self,
        error: str | None,
        error_description: str | None,
    ) -> None:
        self.error = error
        self.error_description = error_description
        super().__init__(self._message())

    def _message(self) -> str:
        if self.error and self.error_description:
            return f"OAuth provider returned `{self.error}`: {self.error_description}"
        if self.error:
            return f"OAuth provider returned `{self.error}`"
        if self.error_description:
            return f"OAuth error: {self.error_description}"
        return "OAuth provider returned an error"


@dataclass(frozen=True)
class CallbackOutcome:
    kind: str
    code: str | None = None
    state: str | None = None
    error: OAuthProviderError | None = None

    @classmethod
    def invalid(cls) -> "CallbackOutcome":
        return cls("invalid")


def parse_oauth_callback(path: str, expected_callback_path: str) -> CallbackOutcome:
    parsed = urllib.parse.urlsplit(path)
    if parsed.path != expected_callback_path or not parsed.query:
        return CallbackOutcome.invalid()
    values = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    code = values.get("code", [None])[-1]
    state = values.get("state", [None])[-1]
    if code is not None and state is not None:
        return CallbackOutcome("success", code=code, state=state)
    error = values.get("error", [None])[-1]
    description = values.get("error_description", [None])[-1]
    if error is not None or description is not None:
        provider_error = OAuthProviderError(error, description)
        return CallbackOutcome("error", error=provider_error)
    return CallbackOutcome.invalid()


def callback_id_from_server_url(server_url: str) -> str:
    parsed = urllib.parse.urlsplit(server_url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(f"MCP server URL `{server_url}` must include a host")
    without_fragment = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")
    )
    digest = hashlib.sha256(without_fragment.encode("utf-8")).digest()[:9]
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def append_callback_id_to_redirect_uri(
    redirect_uri: str,
    callback_id: str,
) -> str:
    parsed = urllib.parse.urlsplit(redirect_uri)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"invalid redirect URI `{redirect_uri}`")
    path = (
        f"{parsed.path}{callback_id}"
        if parsed.path.endswith("/")
        else f"{parsed.path}/{callback_id}"
    )
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment)
    )


def callback_path_from_redirect_uri(redirect_uri: str) -> str:
    return urllib.parse.urlsplit(redirect_uri).path


def append_query_param(
    url: str,
    key: str,
    value: str | None,
) -> str:
    if value is None or not value.strip():
        return str(url)
    try:
        parsed = urllib.parse.urlsplit(url)
        if not parsed.scheme:
            raise ValueError
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        query.append((str(key), value.strip()))
        return urllib.parse.urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urllib.parse.urlencode(query),
                parsed.fragment,
            )
        )
    except ValueError:
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}{key}={urllib.parse.quote(value.strip())}"


class _CallbackServer(ThreadingHTTPServer):
    expected_path: str
    event_loop: asyncio.AbstractEventLoop
    completion: asyncio.Future[CallbackOutcome]


class _CallbackHandler(BaseHTTPRequestHandler):
    server: _CallbackServer

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        outcome = parse_oauth_callback(self.path, self.server.expected_path)
        if outcome.kind == "success":
            body = b"Authentication complete. You may close this window."
            status = 200
        elif outcome.kind == "error":
            body = str(outcome.error).encode("utf-8")
            status = 400
        else:
            body = b"Invalid OAuth callback"
            status = 400
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        if outcome.kind != "invalid":
            self.server.event_loop.call_soon_threadsafe(
                self._complete,
                outcome,
            )

    def _complete(self, outcome: CallbackOutcome) -> None:
        if not self.server.completion.done():
            self.server.completion.set_result(outcome)


def _callback_bind_host(callback_url: str | None) -> str:
    if callback_url is None:
        return "127.0.0.1"
    host = urllib.parse.urlsplit(callback_url).hostname
    return "127.0.0.1" if host in {None, "localhost", "127.0.0.1", "::1"} else "0.0.0.0"


def _http_json(
    url: str,
    *,
    headers: dict[str, str],
    data: dict[str, str] | None = None,
) -> dict[str, Any]:
    body = None if data is None else urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            **headers,
            **({"Content-Type": "application/x-www-form-urlencoded"} if body else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise ValueError(f"OAuth response from {url} must be an object")
    return value


async def _discover_metadata(
    server_url: str,
    headers: dict[str, str],
) -> dict[str, Any]:
    for url in _oauth_discovery_urls(server_url):
        try:
            value = await asyncio.to_thread(_http_json, url, headers=headers)
        except Exception:
            continue
        if value.get("authorization_endpoint") and value.get("token_endpoint"):
            return value
    raise RuntimeError(f"OAuth metadata was not found for {server_url}")


@dataclass
class OauthLoginFlow:
    authorization: str
    callback_server: _CallbackServer
    callback_thread: threading.Thread
    completion: asyncio.Future[CallbackOutcome]
    server_name: str
    server_url: str
    store_mode: OAuthCredentialsStoreMode
    client_id: str
    token_endpoint: str
    redirect_uri: str
    code_verifier: str
    csrf_state: str
    headers: dict[str, str]
    timeout: float
    launch_browser: bool

    @classmethod
    async def new(
        cls,
        *,
        server_name: str,
        server_url: str,
        store_mode: OAuthCredentialsStoreMode | str,
        http_headers: dict[str, str] | None,
        env_http_headers: dict[str, str] | None,
        scopes: tuple[str, ...] | list[str],
        oauth_client_id: str | None,
        oauth_resource: str | None,
        launch_browser: bool,
        callback_port: int | None,
        callback_url: str | None,
        timeout_secs: int | None,
    ) -> "OauthLoginFlow":
        if callback_port == 0:
            raise ValueError(
                "invalid MCP OAuth callback port `0`: port must be between 1 and 65535"
            )
        headers = build_default_headers(http_headers, env_http_headers)
        metadata = await _discover_metadata(server_url, headers)
        client_id = (oauth_client_id or "").strip()
        if not client_id:
            registration_endpoint = metadata.get("registration_endpoint")
            if not registration_endpoint:
                raise RuntimeError(
                    "OAuth metadata does not provide dynamic client registration"
                )
            registered = await asyncio.to_thread(
                _http_json,
                str(registration_endpoint),
                headers=headers,
                data={"client_name": "Codex"},
            )
            client_id = str(registered["client_id"])

        loop = asyncio.get_running_loop()
        completion: asyncio.Future[CallbackOutcome] = loop.create_future()
        callback_server = _CallbackServer(
            (_callback_bind_host(callback_url), callback_port or 0),
            _CallbackHandler,
        )
        callback_server.event_loop = loop
        callback_server.completion = completion
        host, actual_port = callback_server.server_address[:2]
        redirect_uri = (
            callback_url
            if callback_url is not None
            else f"http://{host}:{actual_port}/callback"
        )
        callback_id = callback_id_from_server_url(server_url)
        redirect_uri = append_callback_id_to_redirect_uri(
            redirect_uri,
            callback_id,
        )
        callback_server.expected_path = callback_path_from_redirect_uri(redirect_uri)
        thread = threading.Thread(
            target=callback_server.serve_forever,
            daemon=True,
        )
        thread.start()

        state = secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")
        query = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        authorization = append_query_param(
            f"{metadata['authorization_endpoint']}?{urllib.parse.urlencode(query)}",
            "resource",
            oauth_resource,
        )
        return cls(
            authorization,
            callback_server,
            thread,
            completion,
            str(server_name),
            str(server_url),
            OAuthCredentialsStoreMode(store_mode),
            client_id,
            str(metadata["token_endpoint"]),
            redirect_uri,
            verifier,
            state,
            headers,
            float(max(1, timeout_secs or 300)),
            launch_browser,
        )

    async def finish(self, *, emit_browser_url: bool) -> None:
        try:
            if self.launch_browser:
                if emit_browser_url:
                    print(
                        f"Authorize `{self.server_name}` by opening this URL in your browser:\n"
                        f"{self.authorization}\n"
                    )
                webbrowser.open(self.authorization)
            outcome = await asyncio.wait_for(self.completion, self.timeout)
            if outcome.kind == "error":
                assert outcome.error is not None
                raise outcome.error
            if outcome.kind != "success" or outcome.state != self.csrf_state:
                raise RuntimeError("OAuth callback state did not match")
            token = await asyncio.to_thread(
                _http_json,
                self.token_endpoint,
                headers=self.headers,
                data={
                    "grant_type": "authorization_code",
                    "code": str(outcome.code),
                    "redirect_uri": self.redirect_uri,
                    "client_id": self.client_id,
                    "code_verifier": self.code_verifier,
                },
            )
            scope = token.get("scope", "")
            scopes = tuple(str(scope).split()) if scope else ()
            response = OAuthTokenResponse(
                access_token=str(token["access_token"]),
                token_type=str(token.get("token_type", "Bearer")),
                expires_in=(
                    None
                    if token.get("expires_in") is None
                    else int(token["expires_in"])
                ),
                refresh_token=(
                    None
                    if token.get("refresh_token") is None
                    else str(token["refresh_token"])
                ),
                scopes=scopes,
            )
            stored = StoredOAuthTokens(
                self.server_name,
                self.server_url,
                self.client_id,
                WrappedOAuthTokenResponse(response),
                compute_expires_at_millis(response),
            )
            save_oauth_tokens(self.server_name, stored, self.store_mode)
        finally:
            self.callback_server.shutdown()
            self.callback_server.server_close()
            await asyncio.to_thread(self.callback_thread.join, 2)


class OauthLoginHandle:
    def __init__(
        self,
        authorization_url: str,
        completion: asyncio.Task[None],
    ) -> None:
        self._authorization_url = authorization_url
        self._completion = completion

    def authorization_url(self) -> str:
        return self._authorization_url

    def into_parts(self) -> tuple[str, asyncio.Task[None]]:
        return self._authorization_url, self._completion

    async def wait(self) -> None:
        await self._completion


async def perform_oauth_login_return_url(
    server_name: str,
    server_url: str,
    store_mode: OAuthCredentialsStoreMode | str,
    http_headers: dict[str, str] | None,
    env_http_headers: dict[str, str] | None,
    scopes: tuple[str, ...] | list[str],
    oauth_client_id: str | None,
    oauth_resource: str | None,
    timeout_secs: int | None,
    callback_port: int | None,
    callback_url: str | None,
) -> OauthLoginHandle:
    flow = await OauthLoginFlow.new(
        server_name=server_name,
        server_url=server_url,
        store_mode=store_mode,
        http_headers=http_headers,
        env_http_headers=env_http_headers,
        scopes=scopes,
        oauth_client_id=oauth_client_id,
        oauth_resource=oauth_resource,
        launch_browser=False,
        callback_port=callback_port,
        callback_url=callback_url,
        timeout_secs=timeout_secs,
    )
    url = flow.authorization
    task = asyncio.create_task(flow.finish(emit_browser_url=False))
    return OauthLoginHandle(url, task)


async def _perform_oauth_login(
    *,
    emit_browser_url: bool,
    server_name: str,
    server_url: str,
    store_mode: OAuthCredentialsStoreMode | str,
    http_headers: dict[str, str] | None,
    env_http_headers: dict[str, str] | None,
    scopes: tuple[str, ...] | list[str],
    oauth_client_id: str | None,
    oauth_resource: str | None,
    callback_port: int | None,
    callback_url: str | None,
) -> None:
    flow = await OauthLoginFlow.new(
        server_name=server_name,
        server_url=server_url,
        store_mode=store_mode,
        http_headers=http_headers,
        env_http_headers=env_http_headers,
        scopes=scopes,
        oauth_client_id=oauth_client_id,
        oauth_resource=oauth_resource,
        launch_browser=True,
        callback_port=callback_port,
        callback_url=callback_url,
        timeout_secs=None,
    )
    await flow.finish(emit_browser_url=emit_browser_url)


async def perform_oauth_login(
    server_name: str,
    server_url: str,
    store_mode: OAuthCredentialsStoreMode | str,
    http_headers: dict[str, str] | None,
    env_http_headers: dict[str, str] | None,
    scopes: tuple[str, ...] | list[str],
    oauth_client_id: str | None,
    oauth_resource: str | None,
    callback_port: int | None,
    callback_url: str | None,
) -> None:
    await _perform_oauth_login(
        emit_browser_url=True,
        server_name=server_name,
        server_url=server_url,
        store_mode=store_mode,
        http_headers=http_headers,
        env_http_headers=env_http_headers,
        scopes=scopes,
        oauth_client_id=oauth_client_id,
        oauth_resource=oauth_resource,
        callback_port=callback_port,
        callback_url=callback_url,
    )


async def perform_oauth_login_silent(
    server_name: str,
    server_url: str,
    store_mode: OAuthCredentialsStoreMode | str,
    http_headers: dict[str, str] | None,
    env_http_headers: dict[str, str] | None,
    scopes: tuple[str, ...] | list[str],
    oauth_client_id: str | None,
    oauth_resource: str | None,
    callback_port: int | None,
    callback_url: str | None,
) -> None:
    await _perform_oauth_login(
        emit_browser_url=False,
        server_name=server_name,
        server_url=server_url,
        store_mode=store_mode,
        http_headers=http_headers,
        env_http_headers=env_http_headers,
        scopes=scopes,
        oauth_client_id=oauth_client_id,
        oauth_resource=oauth_resource,
        callback_port=callback_port,
        callback_url=callback_url,
    )


__all__ = [
    "CallbackOutcome",
    "OAuthProviderError",
    "OauthLoginFlow",
    "OauthLoginHandle",
    "append_callback_id_to_redirect_uri",
    "append_query_param",
    "callback_id_from_server_url",
    "callback_path_from_redirect_uri",
    "parse_oauth_callback",
    "perform_oauth_login",
    "perform_oauth_login_return_url",
    "perform_oauth_login_silent",
]
