from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.app_test_support import (
    ChatGptAuthFixture,
    ChatGptIdTokenClaims,
    create_final_assistant_message_sse_response,
    create_shell_command_sse_response,
    encode_id_token,
    rollout_path,
    to_response,
    write_chatgpt_auth,
    write_mock_responses_config_toml,
    write_models_cache_with_models,
)


def test_auth_fixture_matches_rust_claims_and_auth_json(tmp_path: Path) -> None:
    claims = (
        ChatGptIdTokenClaims()
        .with_email("person@example.com")
        .with_plan_type("pro")
        .with_chatgpt_user_id("user-1")
        .with_chatgpt_account_id("account-1")
    )
    token = encode_id_token(claims)
    payload = json.loads(_decode_jwt_part(token.split(".")[1]))
    assert payload["email"] == "person@example.com"
    assert payload["https://api.openai.com/auth"]["chatgpt_plan_type"] == "pro"

    fixture = (
        ChatGptAuthFixture("access-token")
        .with_refresh_token("refresh-token-2")
        .with_account_id("account-1")
        .with_claims(claims)
    )
    write_chatgpt_auth(tmp_path, fixture)
    auth = json.loads((tmp_path / "auth.json").read_text(encoding="utf-8"))
    assert auth["auth_mode"] == "chatgpt"
    assert auth["tokens"]["access_token"] == "access-token"
    assert auth["tokens"]["refresh_token"] == "refresh-token-2"


def test_config_models_cache_and_response_helpers_match_rust(tmp_path: Path) -> None:
    write_mock_responses_config_toml(
        tmp_path,
        "http://127.0.0.1:4321",
        {"unified_exec": True},
        1234,
        True,
        "openai",
        "compact",
    )
    config = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert 'base_url = "http://127.0.0.1:4321/v1"' in config
    assert "model_auto_compact_token_limit = 1234" in config
    assert "requires_openai_auth = true" in config

    write_models_cache_with_models(tmp_path, [{"slug": "model-a"}])
    cache = json.loads((tmp_path / "models_cache.json").read_text(encoding="utf-8"))
    assert cache["models"] == [{"slug": "model-a"}]
    assert cache["etag"] is None

    final = create_final_assistant_message_sse_response("complete")
    assert "response.created" in final
    assert '"text":"complete"' in final
    shell = create_shell_command_sse_response(
        ["echo", "hello world"],
        tmp_path,
        500,
        "call-1",
    )
    assert '"name":"shell_command"' in shell
    assert "call-1" in shell


def test_rollout_path_and_to_response_match_rust(tmp_path: Path) -> None:
    path = rollout_path(
        tmp_path,
        "2026-07-28T12-34-56",
        "019f0000-0000-7000-8000-000000000001",
    )
    assert path == (
        tmp_path
        / "sessions"
        / "2026"
        / "07"
        / "28"
        / "rollout-2026-07-28T12-34-56-019f0000-0000-7000-8000-000000000001.jsonl"
    )
    assert to_response({"result": {"value": 7}}) == {"value": 7}


def _decode_jwt_part(value: str) -> str:
    import base64

    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()


@pytest.mark.asyncio
async def test_mcp_process_drives_real_app_server_stdio(tmp_path: Path) -> None:
    from tests.support.app_test_support import McpProcess

    process = await McpProcess.new(tmp_path)
    try:
        response = await process.initialize()
        assert response["result"]["codexHome"] == str(tmp_path)
        assert response["result"]["userAgent"]
    finally:
        await process.close()
