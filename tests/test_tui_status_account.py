"""Parity tests for codex-rs/tui/src/status/account.rs."""

from pycodex.tui.status.account import StatusAccountDisplay


def test_chatgpt_variant_preserves_optional_email_and_plan():
    account = StatusAccountDisplay.chat_gpt(email="user@example.com", plan="Plus")

    assert account.kind == "ChatGpt"
    assert account.email == "user@example.com"
    assert account.plan == "Plus"
    assert account.is_chat_gpt is True
    assert account.is_api_key is False
    assert account.to_wire() == {
        "ChatGpt": {"email": "user@example.com", "plan": "Plus"}
    }


def test_chatgpt_variant_allows_absent_optional_fields():
    account = StatusAccountDisplay.chat_gpt()

    assert account.email is None
    assert account.plan is None
    assert account.to_wire() == {"ChatGpt": {"email": None, "plan": None}}


def test_api_key_variant_has_no_payload():
    account = StatusAccountDisplay.api_key()

    assert account.kind == "ApiKey"
    assert account.email is None
    assert account.plan is None
    assert account.is_chat_gpt is False
    assert account.is_api_key is True
    assert account.to_wire() == "ApiKey"


def test_from_wire_accepts_semantic_variants():
    assert StatusAccountDisplay.from_wire("ApiKey") == StatusAccountDisplay.api_key()
    assert StatusAccountDisplay.from_wire({"ApiKey": None}) == StatusAccountDisplay.api_key()
    assert StatusAccountDisplay.from_wire(
        {"ChatGpt": {"email": "a@b.test", "plan": None}}
    ) == StatusAccountDisplay.chat_gpt(email="a@b.test", plan=None)


def test_from_wire_rejects_unknown_variants():
    try:
        StatusAccountDisplay.from_wire({"Other": {}})
    except ValueError as exc:
        assert "unsupported StatusAccountDisplay wire value" in str(exc)
    else:
        raise AssertionError("expected ValueError")
