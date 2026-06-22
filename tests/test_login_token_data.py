from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any

import pytest

from pycodex.login.token_data import (
    IdTokenInfo,
    TokenData,
    parse_chatgpt_jwt_claims,
    parse_jwt_expiration,
)
from pycodex.protocol.auth import KnownPlan, PlanType


def fake_jwt(payload: dict[str, Any]) -> str:
    def b64url_no_pad(value: Any) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{b64url_no_pad({'alg': 'none', 'typ': 'JWT'})}.{b64url_no_pad(payload)}.{base64.urlsafe_b64encode(b'sig').decode('ascii').rstrip('=')}"


def test_id_token_info_parses_email_and_plan() -> None:
    # Rust test: codex-login src/token_data_tests.rs id_token_info_parses_email_and_plan.
    jwt = fake_jwt({"email": "user@example.com", "https://api.openai.com/auth": {"chatgpt_plan_type": "pro"}})
    info = parse_chatgpt_jwt_claims(jwt)

    assert info.email == "user@example.com"
    assert info.get_chatgpt_plan_type() == "Pro"


def test_id_token_info_parses_alias_and_usage_based_workspace_plans() -> None:
    # Rust tests: id_token_info_parses_go_plan, id_token_info_parses_hc_plan_as_enterprise,
    # and id_token_info_parses_usage_based_business_plans.
    go = parse_chatgpt_jwt_claims(fake_jwt({"email": "user@example.com", "https://api.openai.com/auth": {"chatgpt_plan_type": "go"}}))
    assert go.get_chatgpt_plan_type() == "Go"

    hc = parse_chatgpt_jwt_claims(fake_jwt({"email": "user@example.com", "https://api.openai.com/auth": {"chatgpt_plan_type": "hc"}}))
    assert hc.get_chatgpt_plan_type() == "Enterprise"
    assert hc.is_workspace_account() is True

    self_serve = parse_chatgpt_jwt_claims(
        fake_jwt({"email": "user@example.com", "https://api.openai.com/auth": {"chatgpt_plan_type": "self_serve_business_usage_based"}})
    )
    assert self_serve.get_chatgpt_plan_type() == "Self Serve Business Usage Based"
    assert self_serve.get_chatgpt_plan_type_raw() == "self_serve_business_usage_based"
    assert self_serve.is_workspace_account() is True

    enterprise_cbp = parse_chatgpt_jwt_claims(
        fake_jwt({"email": "user@example.com", "https://api.openai.com/auth": {"chatgpt_plan_type": "enterprise_cbp_usage_based"}})
    )
    assert enterprise_cbp.get_chatgpt_plan_type() == "Enterprise CBP Usage Based"
    assert enterprise_cbp.get_chatgpt_plan_type_raw() == "enterprise_cbp_usage_based"
    assert enterprise_cbp.is_workspace_account() is True


def test_id_token_info_handles_missing_fields_and_profile_email() -> None:
    # Rust test: codex-login src/token_data_tests.rs id_token_info_handles_missing_fields.
    info = parse_chatgpt_jwt_claims(fake_jwt({"sub": "123"}))
    assert info.email is None
    assert info.get_chatgpt_plan_type() is None
    assert info.is_fedramp_account() is False

    profile_info = parse_chatgpt_jwt_claims(fake_jwt({"https://api.openai.com/profile": {"email": "profile@example.com"}}))
    assert profile_info.email == "profile@example.com"


def test_id_token_info_parses_user_account_and_fedramp_claims() -> None:
    # Rust test: codex-login src/token_data_tests.rs id_token_info_parses_fedramp_account_claim.
    info = parse_chatgpt_jwt_claims(
        fake_jwt(
            {
                "email": "user@example.com",
                "https://api.openai.com/auth": {
                    "chatgpt_user_id": "chatgpt-user",
                    "user_id": "fallback-user",
                    "chatgpt_account_id": "account-fed",
                    "chatgpt_account_is_fedramp": True,
                },
            }
        )
    )

    assert info.chatgpt_user_id == "chatgpt-user"
    assert info.chatgpt_account_id == "account-fed"
    assert info.is_fedramp_account() is True


def test_jwt_expiration_parses_exp_and_missing_exp() -> None:
    # Rust tests: jwt_expiration_parses_exp_claim and jwt_expiration_handles_missing_exp.
    assert parse_jwt_expiration(fake_jwt({"exp": 1_700_000_000})) == datetime.fromtimestamp(1_700_000_000, timezone.utc)
    assert parse_jwt_expiration(fake_jwt({"sub": "123"})) is None


def test_jwt_expiration_rejects_malformed_jwt() -> None:
    # Rust test: codex-login src/token_data_tests.rs jwt_expiration_rejects_malformed_jwt.
    with pytest.raises(ValueError, match="invalid ID token format"):
        parse_jwt_expiration("not-a-jwt")


def test_workspace_account_detection_matches_workspace_plans() -> None:
    # Rust test: codex-login src/token_data_tests.rs workspace_account_detection_matches_workspace_plans.
    workspace = IdTokenInfo(chatgpt_plan_type=PlanType.known_plan(KnownPlan.BUSINESS))
    assert workspace.is_workspace_account() is True

    personal = IdTokenInfo(chatgpt_plan_type=PlanType.known_plan(KnownPlan.PRO))
    assert personal.is_workspace_account() is False

    pro_lite = IdTokenInfo(chatgpt_plan_type=PlanType.known_plan(KnownPlan.PRO_LITE))
    assert pro_lite.is_workspace_account() is False


def test_token_data_mapping_serializes_id_token_as_raw_jwt() -> None:
    # Rust behavior: TokenData serde parses id_token into IdTokenInfo and serializes it back as raw JWT.
    jwt = fake_jwt({"email": "user@example.com", "https://api.openai.com/auth": {"chatgpt_plan_type": "pro"}})
    token_data = TokenData.from_mapping(
        {
            "id_token": jwt,
            "access_token": "access",
            "refresh_token": "refresh",
            "account_id": "account",
        }
    )

    assert token_data.id_token.email == "user@example.com"
    assert token_data.to_json_dict() == {
        "id_token": jwt,
        "access_token": "access",
        "refresh_token": "refresh",
        "account_id": "account",
    }
