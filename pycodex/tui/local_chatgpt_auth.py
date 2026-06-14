from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

_AUTH_FILE = "auth.json"
_OPENAI_AUTH_CLAIMS_KEY = "https://api.openai.com/auth"


@dataclass(frozen=True)
class LocalChatgptAuth:
    """Semantic mirror of tui::local_chatgpt_auth::LocalChatgptAuth."""

    access_token: str
    chatgpt_account_id: str
    chatgpt_plan_type: str | None = None


@dataclass(frozen=True)
class Header:
    alg: str = "none"
    typ: str = "JWT"


def _b64url_json(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def fake_jwt(
    email: str = "user@example.com",
    account_id: str = "workspace-1",
    plan_type: str | None = "business",
) -> str:
    """Build an unsigned JWT-shaped token matching the Rust test helper shape."""

    auth_claims: dict[str, Any] = {"chatgpt_account_id": account_id}
    if plan_type is not None:
        auth_claims["chatgpt_plan_type"] = plan_type
    payload = {
        "email": email,
        _OPENAI_AUTH_CLAIMS_KEY: auth_claims,
    }
    return f"{_b64url_json(Header().__dict__)}.{_b64url_json(payload)}."


def write_chatgpt_auth(
    codex_home: str | Path,
    plan_type: str | None = "business",
    account_id: str = "workspace-1",
    email: str = "user@example.com",
) -> Path:
    """Write a local managed ChatGPT auth fixture for parity tests."""

    codex_home_path = Path(codex_home)
    codex_home_path.mkdir(parents=True, exist_ok=True)
    token = fake_jwt(email=email, account_id=account_id, plan_type=plan_type)
    auth_path = codex_home_path / _AUTH_FILE
    auth_path.write_text(
        json.dumps(
            {
                "auth_mode": "ChatGPT",
                "tokens": {
                    "access_token": token,
                    "refresh_token": "refresh-token",
                    "account_id": account_id,
                    "id_token": token,
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return auth_path


def _decode_jwt_claims(token: Any) -> dict[str, Any]:
    if isinstance(token, Mapping):
        return dict(token)
    if not isinstance(token, str):
        return {}
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode((payload + padding).encode("ascii"))
        claims = json.loads(decoded.decode("utf-8"))
    except Exception:
        return {}
    return dict(claims) if isinstance(claims, Mapping) else {}


def _auth_claims(claims: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = claims.get(_OPENAI_AUTH_CLAIMS_KEY)
    if isinstance(nested, Mapping):
        return nested
    return claims


def _first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _rust_debug_strings(values: Iterable[str]) -> str:
    return "[" + ", ".join(json.dumps(value) for value in values) + "]"


def load_local_chatgpt_auth(
    codex_home: str | Path,
    auth_credentials_store_mode: Any | None = None,
    forced_chatgpt_workspace_id: Iterable[str] | None = None,
) -> LocalChatgptAuth:
    """Load local ChatGPT auth with Rust-compatible error boundaries.

    ``auth_credentials_store_mode`` is accepted for signature parity. Python reads the
    managed ``auth.json`` fixture directly; external ephemeral token stores are not
    consulted, matching the selected module's managed-auth precedence tests.
    """

    _ = auth_credentials_store_mode
    auth_path = Path(codex_home) / _AUTH_FILE
    if not auth_path.exists():
        raise ValueError("no local auth available")

    try:
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"failed to load local auth: {exc}") from exc

    if not isinstance(auth, Mapping):
        raise ValueError("failed to load local auth: auth.json must contain an object")

    auth_mode = auth.get("auth_mode")
    auth_mode_text = str(auth_mode).lower() if auth_mode is not None else ""
    if auth.get("openai_api_key") is not None or auth_mode_text in {"apikey", "api_key", "api-key"}:
        raise ValueError("local auth is not a ChatGPT login")

    tokens = auth.get("tokens")
    if not isinstance(tokens, Mapping):
        raise ValueError("local ChatGPT auth is missing token data")

    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ValueError("local ChatGPT auth is missing token data")

    id_claims = _decode_jwt_claims(tokens.get("id_token"))
    nested_claims = _auth_claims(id_claims)
    chatgpt_account_id = _first_string(
        tokens.get("account_id"),
        tokens.get("chatgpt_account_id"),
        nested_claims.get("chatgpt_account_id"),
        id_claims.get("chatgpt_account_id"),
    )
    if chatgpt_account_id is None:
        raise ValueError("local ChatGPT auth is missing chatgpt account id")

    expected_workspaces = list(forced_chatgpt_workspace_id or [])
    if expected_workspaces and chatgpt_account_id not in expected_workspaces:
        raise ValueError(
            "local ChatGPT auth must use one of workspace(s) "
            f"{_rust_debug_strings(expected_workspaces)}, but found {json.dumps(chatgpt_account_id)}"
        )

    plan_type = _first_string(
        tokens.get("chatgpt_plan_type"),
        nested_claims.get("chatgpt_plan_type"),
        id_claims.get("chatgpt_plan_type"),
    )
    if plan_type is not None:
        plan_type = plan_type.lower()

    return LocalChatgptAuth(
        access_token=access_token,
        chatgpt_account_id=chatgpt_account_id,
        chatgpt_plan_type=plan_type,
    )


__all__ = [
    "Header",
    "LocalChatgptAuth",
    "fake_jwt",
    "load_local_chatgpt_auth",
    "write_chatgpt_auth",
]
