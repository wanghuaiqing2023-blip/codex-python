from __future__ import annotations

import base64
import hashlib
import json

import pytest

from pycodex.agent_identity import (
    AGENT_IDENTITY_JWT_AUDIENCE,
    AGENT_IDENTITY_JWT_ISSUER,
    AgentIdentityKey,
    AgentIdentityJwtClaims,
    AgentTaskAuthorizationTarget,
    agent_identity_jwks_url,
    authorization_header_for_agent_task,
    build_abom,
    decode_agent_identity_jwt,
    decode_agent_identity_jwt_payload,
    generate_agent_key_material,
    public_key_ssh_from_private_key_pkcs8_base64,
    serialize_agent_assertion,
    sign_task_registration_payload,
    task_id_from_register_task_response,
)
from pycodex.agent_identity import (
    _sealed_box_seal_for_test,
    _x25519_base as _x25519_base_for_test,
    curve25519_secret_key_from_private_key_pkcs8_base64,
)


def _key() -> AgentIdentityKey:
    material = generate_agent_key_material(seed=bytes([7]) * 32)
    return AgentIdentityKey("agent-123", material.private_key_pkcs8_base64)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _jwt_with_payload(payload: dict[str, object], *, kid: str | None = None) -> str:
    header: dict[str, object] = {"alg": "none", "typ": "JWT"}
    if kid is not None:
        header["kid"] = kid
    return ".".join(
        [
            _b64url(json.dumps(header, separators=(",", ":")).encode()),
            _b64url(json.dumps(payload, separators=(",", ":")).encode()),
            _b64url(b"sig"),
        ]
    )


def _claims_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "iss": AGENT_IDENTITY_JWT_ISSUER,
        "aud": AGENT_IDENTITY_JWT_AUDIENCE,
        "iat": 1_700_000_000,
        "exp": 4_000_000_000,
        "agent_runtime_id": "agent-runtime-id",
        "agent_private_key": "private-key",
        "account_id": "account-id",
        "chatgpt_user_id": "user-id",
        "email": "user@example.com",
        "plan_type": "pro",
        "chatgpt_account_is_fedramp": False,
    }
    payload.update(overrides)
    return payload


def test_authorization_header_for_agent_task_serializes_signed_agent_assertion():
    # Rust crate/module: codex-agent-identity src/lib.rs,
    # test authorization_header_for_agent_task_serializes_signed_agent_assertion.
    key = _key()
    header = authorization_header_for_agent_task(
        key,
        AgentTaskAuthorizationTarget("agent-123", "task-123"),
        timestamp="2023-11-14T22:13:20Z",
    )

    token = header.removeprefix("AgentAssertion ")
    payload = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    envelope = json.loads(payload)

    assert envelope["agent_runtime_id"] == "agent-123"
    assert envelope["task_id"] == "task-123"
    assert envelope["timestamp"] == "2023-11-14T22:13:20Z"
    assert isinstance(base64.b64decode(envelope["signature"]), bytes)
    assert len(base64.b64decode(envelope["signature"])) == 64


def test_authorization_header_for_agent_task_rejects_mismatched_runtime():
    with pytest.raises(
        ValueError,
        match="agent task runtime agent-456 does not match stored agent identity agent-123",
    ):
        authorization_header_for_agent_task(
            _key(),
            AgentTaskAuthorizationTarget("agent-456", "task-123"),
        )


def test_decode_agent_identity_jwt_reads_claims():
    jwt = _jwt_with_payload(_claims_payload())

    assert decode_agent_identity_jwt(jwt) == AgentIdentityJwtClaims(
        iss=AGENT_IDENTITY_JWT_ISSUER,
        aud=AGENT_IDENTITY_JWT_AUDIENCE,
        iat=1_700_000_000,
        exp=4_000_000_000,
        agent_runtime_id="agent-runtime-id",
        agent_private_key="private-key",
        account_id="account-id",
        chatgpt_user_id="user-id",
        email="user@example.com",
        plan_type="pro",
        chatgpt_account_is_fedramp=False,
    )


def test_decode_agent_identity_jwt_maps_raw_plan_aliases():
    claims = decode_agent_identity_jwt(_jwt_with_payload(_claims_payload(plan_type="hc")))

    assert claims.plan_type == "enterprise"


def test_decode_agent_identity_jwt_verifies_when_jwks_is_present():
    jwt, jwks = _signed_rs256_jwt(_claims_payload(), kid="test-key")

    claims = decode_agent_identity_jwt(jwt, jwks, now=1_800_000_000)

    assert claims.agent_runtime_id == "agent-runtime-id"
    assert claims.plan_type == "pro"


def test_decode_agent_identity_jwt_rejects_untrusted_kid():
    jwt, _jwks = _signed_rs256_jwt(_claims_payload(), kid="test-key")

    with pytest.raises(ValueError, match="kid test-key is not trusted"):
        decode_agent_identity_jwt(jwt, {"keys": [{"kid": "other-key"}]}, now=1_800_000_000)


def test_decode_agent_identity_jwt_requires_issuer_and_audience():
    jwt, jwks = _signed_rs256_jwt(
        _claims_payload(iss="https://wrong.example", aud="wrong"),
        kid="test-key",
    )

    with pytest.raises(ValueError, match="failed to verify agent identity JWT"):
        decode_agent_identity_jwt(jwt, jwks, now=1_800_000_000)


def test_agent_identity_jwks_url_uses_backend_api_base_url():
    assert (
        agent_identity_jwks_url("https://chatgpt.com/backend-api")
        == "https://chatgpt.com/backend-api/wham/agent-identities/jwks"
    )
    assert (
        agent_identity_jwks_url("https://chatgpt.com/backend-api/")
        == "https://chatgpt.com/backend-api/wham/agent-identities/jwks"
    )


def test_agent_identity_jwks_url_uses_codex_api_base_url():
    assert (
        agent_identity_jwks_url("http://localhost:8080/api/codex")
        == "http://localhost:8080/api/codex/agent-identities/jwks"
    )
    assert (
        agent_identity_jwks_url("http://localhost:8080/api/codex/")
        == "http://localhost:8080/api/codex/agent-identities/jwks"
    )


def test_key_material_urls_registration_response_and_abom_helpers():
    key = _key()

    assert public_key_ssh_from_private_key_pkcs8_base64(key.private_key_pkcs8_base64).startswith(
        "ssh-ed25519 "
    )
    assert sign_task_registration_payload(key, "2023-11-14T22:13:20Z")
    assert task_id_from_register_task_response(key, {"taskId": "task-123"}) == "task-123"
    assert decode_agent_identity_jwt_payload(_jwt_with_payload(_claims_payload()))["email"] == "user@example.com"
    assert serialize_agent_assertion(
        {
            "agent_runtime_id": "agent",
            "task_id": "task",
            "timestamp": "time",
            "signature": "sig",
        }
    )
    assert build_abom("VSCode", version="1.2.3", os_name="linux").agent_harness_id == "codex-app"


def test_task_registration_response_decrypts_encrypted_task_id():
    # Rust crate/module: codex-agent-identity src/lib.rs,
    # contract for task_id_from_register_task_response -> decrypt_task_id_response.
    key = _key()
    recipient_secret = curve25519_secret_key_from_private_key_pkcs8_base64(
        key.private_key_pkcs8_base64
    )
    recipient_public = _x25519_base_for_test(recipient_secret)
    sealed = _sealed_box_seal_for_test(
        b"task-encrypted",
        recipient_public,
        bytes([11]) * 32,
    )

    assert task_id_from_register_task_response(
        key,
        {"encryptedTaskId": base64.b64encode(sealed).decode()},
    ) == "task-encrypted"


def _signed_rs256_jwt(payload: dict[str, object], *, kid: str) -> tuple[str, dict[str, object]]:
    p = _next_prime((1 << 511) + 643)
    q = _next_prime((1 << 510) + 1597)
    n = p * q
    e = 65537
    phi = (p - 1) * (q - 1)
    d = pow(e, -1, phi)
    header = {"alg": "RS256", "typ": "JWT", "kid": kid}
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()
    digest = hashlib.sha256(signing_input).digest()
    prefix = bytes.fromhex("3031300d060960864801650304020105000420")
    k = (n.bit_length() + 7) // 8
    encoded = b"\x00\x01" + (b"\xff" * (k - len(prefix) - len(digest) - 3)) + b"\x00" + prefix + digest
    signature = pow(int.from_bytes(encoded, "big"), d, n).to_bytes(k, "big")
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": kid,
                "use": "sig",
                "alg": "RS256",
                "n": _b64url(n.to_bytes(k, "big")),
                "e": _b64url(e.to_bytes((e.bit_length() + 7) // 8, "big")),
            }
        ]
    }
    return f"{header_b64}.{payload_b64}.{_b64url(signature)}", jwks


def _next_prime(value: int) -> int:
    candidate = value | 1
    while not _is_probable_prime(candidate):
        candidate += 2
    return candidate


def _is_probable_prime(value: int) -> bool:
    if value < 2:
        return False
    small_primes = (3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    if value == 2:
        return True
    if value % 2 == 0:
        return False
    for prime in small_primes:
        if value == prime:
            return True
        if value % prime == 0:
            return False
    d = value - 1
    s = 0
    while d % 2 == 0:
        s += 1
        d //= 2
    for base in (2, 3, 5, 7, 11, 13, 17):
        x = pow(base, d, value)
        if x in (1, value - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, value)
            if x == value - 1:
                break
        else:
            return False
    return True
