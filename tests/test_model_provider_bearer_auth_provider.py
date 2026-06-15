from pycodex.model_provider import BearerAuthProvider


def test_bearer_auth_provider_new_sets_token_only() -> None:
    # Rust crate/module: codex-model-provider::bearer_auth_provider::BearerAuthProvider::new
    auth = BearerAuthProvider.new("access-token")

    assert auth.token == "access-token"
    assert auth.account_id is None
    assert auth.is_fedramp_account is False


def test_bearer_auth_provider_for_test_accepts_optional_fields() -> None:
    # Rust crate/module: codex-model-provider::bearer_auth_provider::BearerAuthProvider::for_test
    auth = BearerAuthProvider.for_test("access-token", "workspace-123")

    assert auth.token == "access-token"
    assert auth.account_id == "workspace-123"
    assert auth.is_fedramp_account is False


def test_bearer_auth_provider_adds_auth_headers() -> None:
    # Rust test: bearer_auth_provider_adds_auth_headers.
    auth = BearerAuthProvider.for_test("access-token", "workspace-123")
    headers: dict[str, str] = {}

    auth.add_auth_headers(headers)

    assert headers["Authorization"] == "Bearer access-token"
    assert headers["ChatGPT-Account-ID"] == "workspace-123"
    assert "X-OpenAI-Fedramp" not in headers


def test_bearer_auth_provider_adds_fedramp_routing_header_for_fedramp_accounts() -> None:
    # Rust test: bearer_auth_provider_adds_fedramp_routing_header_for_fedramp_accounts.
    auth = BearerAuthProvider(token="access-token", account_id="workspace-123", is_fedramp_account=True)
    headers = auth.to_auth_headers()

    assert headers["Authorization"] == "Bearer access-token"
    assert headers["ChatGPT-Account-ID"] == "workspace-123"
    assert headers["X-OpenAI-Fedramp"] == "true"


def test_bearer_auth_provider_skips_missing_token_and_account() -> None:
    # Rust behavior: optional token/account headers are inserted only when present.
    auth = BearerAuthProvider()

    assert auth.to_auth_headers() == {}
