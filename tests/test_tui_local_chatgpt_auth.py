# Parity source: codex-rs/tui/src/local_chatgpt_auth.rs

import json

import pytest

from pycodex.tui.local_chatgpt_auth import (
    fake_jwt,
    load_local_chatgpt_auth,
    write_chatgpt_auth,
)


def test_loads_local_chatgpt_auth_from_managed_auth_matches_rust(tmp_path):
    write_chatgpt_auth(tmp_path, plan_type="business", account_id="workspace-1")

    auth = load_local_chatgpt_auth(tmp_path, forced_chatgpt_workspace_id=["workspace-1"])

    assert auth.access_token
    assert auth.chatgpt_account_id == "workspace-1"
    assert auth.chatgpt_plan_type == "business"


def test_rejects_missing_local_auth_matches_rust(tmp_path):
    with pytest.raises(ValueError, match="no local auth available"):
        load_local_chatgpt_auth(tmp_path)


def test_rejects_api_key_auth_matches_rust(tmp_path):
    (tmp_path / "auth.json").write_text(
        json.dumps({"auth_mode": "ApiKey", "openai_api_key": "sk-test"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="local auth is not a ChatGPT login"):
        load_local_chatgpt_auth(tmp_path)


def test_rejects_openai_api_key_even_without_api_key_mode_matches_rust(tmp_path):
    (tmp_path / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "ChatGPT",
                "openai_api_key": "sk-test",
                "tokens": {
                    "access_token": "access-token",
                    "account_id": "workspace-1",
                    "id_token": fake_jwt(account_id="workspace-1"),
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="local auth is not a ChatGPT login"):
        load_local_chatgpt_auth(tmp_path)


def test_prefers_managed_auth_over_external_ephemeral_tokens_matches_rust(tmp_path):
    write_chatgpt_auth(tmp_path, plan_type="business", account_id="workspace-1")
    (tmp_path / "external_auth.json").write_text(
        json.dumps(
            {
                "tokens": {
                    "access_token": fake_jwt(account_id="workspace-2"),
                    "account_id": "workspace-2",
                    "id_token": fake_jwt(account_id="workspace-2"),
                }
            }
        ),
        encoding="utf-8",
    )

    auth = load_local_chatgpt_auth(tmp_path, forced_chatgpt_workspace_id=["workspace-1"])

    assert auth.chatgpt_account_id == "workspace-1"


def test_preserves_usage_based_plan_type_wire_name_matches_rust(tmp_path):
    write_chatgpt_auth(
        tmp_path,
        plan_type="self_serve_business_usage_based",
        account_id="workspace-1",
    )

    auth = load_local_chatgpt_auth(tmp_path)

    assert auth.chatgpt_plan_type == "self_serve_business_usage_based"


def test_falls_back_to_id_token_account_id_from_rust_contract(tmp_path):
    token = fake_jwt(account_id="workspace-from-id-token", plan_type="Enterprise")
    (tmp_path / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "ChatGPT",
                "tokens": {
                    "access_token": "access-token",
                    "id_token": token,
                },
            }
        ),
        encoding="utf-8",
    )

    auth = load_local_chatgpt_auth(tmp_path)

    assert auth.chatgpt_account_id == "workspace-from-id-token"
    assert auth.chatgpt_plan_type == "enterprise"


def test_rejects_forced_workspace_mismatch_from_rust_contract(tmp_path):
    write_chatgpt_auth(tmp_path, account_id="workspace-1")

    with pytest.raises(ValueError, match="must use one of workspace"):
        load_local_chatgpt_auth(tmp_path, forced_chatgpt_workspace_id=["workspace-2"])


def test_rejects_missing_token_data_from_rust_contract(tmp_path):
    (tmp_path / "auth.json").write_text(
        json.dumps({"auth_mode": "ChatGPT"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing token data"):
        load_local_chatgpt_auth(tmp_path)


def test_rejects_missing_chatgpt_account_id_from_rust_contract(tmp_path):
    (tmp_path / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "ChatGPT",
                "tokens": {
                    "access_token": "access-token",
                    "id_token": fake_jwt(account_id="", plan_type="business"),
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing chatgpt account id"):
        load_local_chatgpt_auth(tmp_path)
