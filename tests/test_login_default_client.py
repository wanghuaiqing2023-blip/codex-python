"""Parity tests for Rust ``codex-login::auth::default_client``.

Rust source:
- ``codex/codex-rs/login/src/auth/default_client.rs``
- ``codex/codex-rs/login/src/auth/default_client_tests.rs``
"""

from __future__ import annotations

import pytest

import pycodex.login as login
import pycodex.login.auth as login_auth
from pycodex.config import ResidencyRequirement
from pycodex.login.auth import default_client


@pytest.fixture(autouse=True)
def reset_default_client_state(monkeypatch: pytest.MonkeyPatch):
    default_client._reset_for_tests()
    monkeypatch.delenv(default_client.CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR, raising=False)
    monkeypatch.delenv("CODEX_SANDBOX", raising=False)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.delenv("TERM_PROGRAM_VERSION", raising=False)
    yield
    default_client._reset_for_tests()


def test_get_codex_user_agent_starts_with_originator_prefix() -> None:
    user_agent = default_client.get_codex_user_agent()
    originator = default_client.originator().value

    assert user_agent.startswith(f"{originator}/")


def test_default_client_module_is_reexported_from_login_surfaces() -> None:
    assert login_auth.default_client is default_client
    assert login.default_client is default_client


def test_is_first_party_originator_matches_known_values() -> None:
    assert default_client.is_first_party_originator(default_client.DEFAULT_ORIGINATOR) is True
    assert default_client.is_first_party_originator("codex-tui") is True
    assert default_client.is_first_party_originator("codex_vscode") is True
    assert default_client.is_first_party_originator("Codex Something Else") is True
    assert default_client.is_first_party_originator("codex_cli") is False
    assert default_client.is_first_party_originator("Other") is False


def test_is_first_party_chat_originator_matches_known_values() -> None:
    assert default_client.is_first_party_chat_originator("codex_atlas") is True
    assert default_client.is_first_party_chat_originator("codex_chatgpt_desktop") is True
    assert default_client.is_first_party_chat_originator(default_client.DEFAULT_ORIGINATOR) is False
    assert default_client.is_first_party_chat_originator("codex_vscode") is False


def test_invalid_suffix_is_sanitized() -> None:
    prefix = "codex_cli_rs/0.0.0"

    assert (
        default_client.sanitize_user_agent(f"{prefix} (bad\rsuffix)", prefix)
        == "codex_cli_rs/0.0.0 (bad_suffix)"
    )
    assert (
        default_client.sanitize_user_agent(f"{prefix} (bad\0suffix)", prefix)
        == "codex_cli_rs/0.0.0 (bad_suffix)"
    )


def test_originator_prefers_env_override_and_caches_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(default_client.CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR, "codex_env")

    assert default_client.originator().value == "codex_env"
    monkeypatch.setenv(default_client.CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR, "codex_later")
    assert default_client.originator().value == "codex_env"


def test_set_default_originator_uses_provided_value_and_rejects_second_init() -> None:
    default_client.set_default_originator("codex_custom")

    assert default_client.originator().value == "codex_custom"
    with pytest.raises(default_client.SetOriginatorError, match="AlreadyInitialized"):
        default_client.set_default_originator("codex_other")


def test_set_default_originator_rejects_invalid_header_value() -> None:
    with pytest.raises(default_client.SetOriginatorError, match="InvalidHeaderValue"):
        default_client.set_default_originator("bad\rvalue")


def test_env_originator_override_wins_over_provided_originator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(default_client.CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR, "codex_env")

    default_client.set_default_originator("codex_custom")

    assert default_client.originator().value == "codex_env"


def test_default_headers_include_originator_user_agent_and_residency() -> None:
    default_client.set_default_originator("codex_custom")
    default_client.set_default_client_residency_requirement(ResidencyRequirement.US)

    headers = default_client.default_headers()

    assert headers["originator"] == "codex_custom"
    assert headers["user-agent"].startswith("codex_custom/")
    assert headers[default_client.RESIDENCY_HEADER_NAME] == "us"


def test_create_client_sets_default_headers_and_sandbox_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_SANDBOX", "seatbelt")
    default_client.set_default_client_residency_requirement("us")

    client = default_client.create_client()
    request = client.get("https://example.test")

    assert client.no_proxy is True
    assert client.default_headers[default_client.RESIDENCY_HEADER_NAME] == "us"
    assert request.client is client
    assert request.method == "GET"
    assert request.url == "https://example.test"
