"""Agent identity helpers ported from ``codex-agent-identity``."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping


AGENT_TASK_REGISTRATION_TIMEOUT_SECONDS = 30
AGENT_IDENTITY_JWKS_TIMEOUT_SECONDS = 10
AGENT_IDENTITY_JWT_AUDIENCE = "codex-app-server"
AGENT_IDENTITY_JWT_ISSUER = "https://chatgpt.com/codex-backend/agent-identity"
_ED25519_PKCS8_PREFIX = bytes.fromhex("302e020100300506032b657004220420")
_B64URL_ALPHABET = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


@dataclass(frozen=True)
class AgentIdentityKey:
    agent_runtime_id: str
    private_key_pkcs8_base64: str


@dataclass(frozen=True)
class AgentTaskAuthorizationTarget:
    agent_runtime_id: str
    task_id: str


@dataclass(frozen=True)
class AgentBillOfMaterials:
    agent_version: str
    agent_harness_id: str
    running_location: str


@dataclass(frozen=True)
class GeneratedAgentKeyMaterial:
    private_key_pkcs8_base64: str
    public_key_ssh: str


@dataclass(frozen=True)
class AgentIdentityJwtClaims:
    iss: str
    aud: str
    iat: int
    exp: int
    agent_runtime_id: str
    agent_private_key: str
    account_id: str
    chatgpt_user_id: str
    email: str
    plan_type: str
    chatgpt_account_is_fedramp: bool


def authorization_header_for_agent_task(
    key: AgentIdentityKey,
    target: AgentTaskAuthorizationTarget,
    *,
    timestamp: str | None = None,
) -> str:
    if key.agent_runtime_id != target.agent_runtime_id:
        raise ValueError(
            "agent task runtime "
            f"{target.agent_runtime_id} does not match stored agent identity "
            f"{key.agent_runtime_id}"
        )
    timestamp = timestamp or _now_rfc3339()
    envelope = {
        "agent_runtime_id": target.agent_runtime_id,
        "signature": sign_agent_assertion_payload(key, target.task_id, timestamp),
        "task_id": target.task_id,
        "timestamp": timestamp,
    }
    return "AgentAssertion " + serialize_agent_assertion(envelope)


def decode_agent_identity_jwt(
    jwt: str,
    jwks: Mapping[str, Any] | None = None,
    *,
    now: int | None = None,
) -> AgentIdentityJwtClaims:
    if jwks is None:
        return _claims_from_mapping(decode_agent_identity_jwt_payload(jwt))
    header, payload, signing_input, signature = _jwt_parts(jwt)
    kid = header.get("kid")
    if not kid:
        raise ValueError("agent identity JWT header does not include a kid")
    jwk = _find_jwk(jwks, str(kid))
    if jwk is None:
        raise ValueError(f"agent identity JWT kid {kid} is not trusted")
    if header.get("alg") != "RS256":
        raise ValueError("failed to verify agent identity JWT")
    if not _verify_rs256(jwk, signing_input, signature):
        raise ValueError("failed to verify agent identity JWT")
    claims = _claims_from_mapping(payload)
    if claims.iss != AGENT_IDENTITY_JWT_ISSUER or claims.aud != AGENT_IDENTITY_JWT_AUDIENCE:
        raise ValueError("failed to verify agent identity JWT")
    now = int(time.time()) if now is None else now
    if claims.exp < now:
        raise ValueError("failed to verify agent identity JWT")
    return claims


async def fetch_agent_identity_jwks(client: Any, chatgpt_base_url: str) -> Mapping[str, Any]:
    response = await _maybe_await(
        client.get(
            agent_identity_jwks_url(chatgpt_base_url),
            timeout=AGENT_IDENTITY_JWKS_TIMEOUT_SECONDS,
        )
    )
    response = _raise_for_status(response, "agent identity JWKS endpoint returned an error")
    return await _response_json(response, "failed to decode agent identity JWKS")


def decode_agent_identity_jwt_payload(jwt: str) -> dict[str, Any]:
    _header, payload, _signing_input, _signature = _jwt_parts(jwt)
    return payload


async def register_agent_task(client: Any, chatgpt_base_url: str, key: AgentIdentityKey) -> str:
    timestamp = _now_rfc3339()
    request = {
        "timestamp": timestamp,
        "signature": sign_task_registration_payload(key, timestamp),
    }
    response = await _maybe_await(
        client.post(
            agent_task_registration_url(chatgpt_base_url, key.agent_runtime_id),
            timeout=AGENT_TASK_REGISTRATION_TIMEOUT_SECONDS,
            json=request,
        )
    )
    status = getattr(response, "status", getattr(response, "status_code", 200))
    if not (200 <= int(status) < 300):
        body = await _response_text(response)
        if len(body) > 512:
            body = body[:512] + "..."
        raise ValueError(f"failed to register agent task with status {status}: {body}")
    decoded = await _response_json(response, "failed to decode agent task registration response")
    return task_id_from_register_task_response(key, decoded)


def sign_task_registration_payload(key: AgentIdentityKey, timestamp: str) -> str:
    signing_key = signing_key_from_private_key_pkcs8_base64(key.private_key_pkcs8_base64)
    return _b64encode(_ed25519_sign(signing_key, f"{key.agent_runtime_id}:{timestamp}".encode()))


def task_id_from_register_task_response(
    key: AgentIdentityKey,
    response: Mapping[str, Any],
) -> str:
    task_id = response.get("task_id") or response.get("taskId")
    if task_id is not None:
        return str(task_id)
    encrypted = response.get("encrypted_task_id") or response.get("encryptedTaskId")
    if encrypted is None:
        raise ValueError("agent task registration response omitted task id")
    return decrypt_task_id_response(key, str(encrypted))


def decrypt_task_id_response(key: AgentIdentityKey, encrypted_task_id: str) -> str:
    try:
        sealed = base64.b64decode(encrypted_task_id, validate=True)
    except Exception as exc:
        raise ValueError("encrypted task id is not valid base64") from exc
    signing_seed = signing_key_from_private_key_pkcs8_base64(key.private_key_pkcs8_base64)
    secret_key = curve25519_secret_key_from_private_key_pkcs8_base64(key.private_key_pkcs8_base64)
    public_key = _x25519_base(secret_key)
    try:
        plaintext = _sealed_box_open(sealed, secret_key, public_key)
    except ValueError as exc:
        raise ValueError("failed to decrypt encrypted task id") from exc
    _ = signing_seed
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("decrypted task id is not valid UTF-8") from exc


def generate_agent_key_material(*, seed: bytes | None = None) -> GeneratedAgentKeyMaterial:
    seed = seed or os.urandom(32)
    if len(seed) != 32:
        raise ValueError("agent identity private key bytes must be 32 bytes")
    private_key_pkcs8 = _ED25519_PKCS8_PREFIX + seed
    return GeneratedAgentKeyMaterial(
        private_key_pkcs8_base64=_b64encode(private_key_pkcs8),
        public_key_ssh=encode_ssh_ed25519_public_key(_ed25519_public_key(seed)),
    )


def public_key_ssh_from_private_key_pkcs8_base64(private_key_pkcs8_base64: str) -> str:
    return encode_ssh_ed25519_public_key(
        _ed25519_public_key(signing_key_from_private_key_pkcs8_base64(private_key_pkcs8_base64))
    )


def verifying_key_from_private_key_pkcs8_base64(private_key_pkcs8_base64: str) -> bytes:
    return _ed25519_public_key(signing_key_from_private_key_pkcs8_base64(private_key_pkcs8_base64))


def curve25519_secret_key_from_private_key_pkcs8_base64(private_key_pkcs8_base64: str) -> bytes:
    seed = signing_key_from_private_key_pkcs8_base64(private_key_pkcs8_base64)
    digest = bytearray(hashlib.sha512(seed).digest()[:32])
    digest[0] &= 248
    digest[31] &= 127
    digest[31] |= 64
    return bytes(digest)


def agent_registration_url(chatgpt_base_url: str) -> str:
    return f"{chatgpt_base_url.rstrip('/')}/v1/agent/register"


def agent_task_registration_url(chatgpt_base_url: str, agent_runtime_id: str) -> str:
    return f"{chatgpt_base_url.rstrip('/')}/v1/agent/{agent_runtime_id}/task/register"


def agent_identity_biscuit_url(chatgpt_base_url: str) -> str:
    return f"{chatgpt_base_url.rstrip('/')}/authenticate_app_v2"


def agent_identity_jwks_url(chatgpt_base_url: str) -> str:
    trimmed = chatgpt_base_url.rstrip("/")
    if "/backend-api" in trimmed:
        return f"{trimmed}/wham/agent-identities/jwks"
    return f"{trimmed}/agent-identities/jwks"


def agent_identity_request_id(*, random_bytes: bytes | None = None) -> str:
    random_bytes = random_bytes or os.urandom(16)
    return f"codex-agent-identity-{_b64url_encode(random_bytes)}"


def build_abom(session_source: Any, *, version: str = "0.0.0", os_name: str | None = None) -> AgentBillOfMaterials:
    source = str(session_source)
    harness = "codex-app" if source == "vscode" or source == "VSCode" else "codex-cli"
    return AgentBillOfMaterials(
        agent_version=version,
        agent_harness_id=harness,
        running_location=f"{source}-{os_name or os.name}",
    )


def encode_ssh_ed25519_public_key(verifying_key: bytes) -> str:
    blob = _ssh_string(b"ssh-ed25519") + _ssh_string(verifying_key)
    return f"ssh-ed25519 {_b64encode(blob)}"


def sign_agent_assertion_payload(
    key: AgentIdentityKey,
    task_id: str,
    timestamp: str,
) -> str:
    signing_key = signing_key_from_private_key_pkcs8_base64(key.private_key_pkcs8_base64)
    payload = f"{key.agent_runtime_id}:{task_id}:{timestamp}".encode()
    return _b64encode(_ed25519_sign(signing_key, payload))


def serialize_agent_assertion(envelope: Mapping[str, str]) -> str:
    ordered = {
        "agent_runtime_id": envelope["agent_runtime_id"],
        "signature": envelope["signature"],
        "task_id": envelope["task_id"],
        "timestamp": envelope["timestamp"],
    }
    return _b64url_encode(json.dumps(ordered, separators=(",", ":")).encode())


def signing_key_from_private_key_pkcs8_base64(private_key_pkcs8_base64: str) -> bytes:
    try:
        private_key = base64.b64decode(private_key_pkcs8_base64, validate=True)
    except Exception as exc:
        raise ValueError("stored agent identity private key is not valid base64") from exc
    if not private_key.startswith(_ED25519_PKCS8_PREFIX) or len(private_key) != len(_ED25519_PKCS8_PREFIX) + 32:
        raise ValueError("stored agent identity private key is not valid PKCS#8")
    return private_key[len(_ED25519_PKCS8_PREFIX) :]


def _claims_from_mapping(data: Mapping[str, Any]) -> AgentIdentityJwtClaims:
    return AgentIdentityJwtClaims(
        iss=str(data["iss"]),
        aud=str(data["aud"]),
        iat=int(data["iat"]),
        exp=int(data["exp"]),
        agent_runtime_id=str(data["agent_runtime_id"]),
        agent_private_key=str(data["agent_private_key"]),
        account_id=str(data["account_id"]),
        chatgpt_user_id=str(data["chatgpt_user_id"]),
        email=str(data["email"]),
        plan_type=_plan_type_alias(str(data["plan_type"])),
        chatgpt_account_is_fedramp=bool(data["chatgpt_account_is_fedramp"]),
    )


def _plan_type_alias(value: str) -> str:
    if value == "hc":
        return "enterprise"
    return value


def _jwt_parts(jwt: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    parts = jwt.split(".")
    if len(parts) != 3 or any(part == "" for part in parts):
        raise ValueError("invalid agent identity JWT format")
    try:
        header = json.loads(_b64url_decode(parts[0]))
        payload = json.loads(_b64url_decode(parts[1]))
        signature = _b64url_decode(parts[2])
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("agent identity JWT payload is not valid JSON") from exc
    return header, payload, f"{parts[0]}.{parts[1]}".encode(), signature


def _find_jwk(jwks: Mapping[str, Any], kid: str) -> Mapping[str, Any] | None:
    for item in jwks.get("keys", []):
        if isinstance(item, Mapping) and item.get("kid") == kid:
            return item
    return None


def _verify_rs256(jwk: Mapping[str, Any], signing_input: bytes, signature: bytes) -> bool:
    try:
        n = int.from_bytes(_b64url_decode(str(jwk["n"])), "big")
        e = int.from_bytes(_b64url_decode(str(jwk["e"])), "big")
    except Exception:
        return False
    k = (n.bit_length() + 7) // 8
    if len(signature) != k:
        return False
    encoded = pow(int.from_bytes(signature, "big"), e, n).to_bytes(k, "big")
    digest = hashlib.sha256(signing_input).digest()
    prefix = bytes.fromhex("3031300d060960864801650304020105000420")
    expected = b"\x00\x01" + (b"\xff" * (k - len(prefix) - len(digest) - 3)) + b"\x00" + prefix + digest
    return encoded == expected


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


def _raise_for_status(response: Any, message: str) -> Any:
    method = getattr(response, "error_for_status", None)
    if callable(method):
        try:
            return method()
        except Exception as exc:
            raise ValueError(message) from exc
    status = getattr(response, "status", getattr(response, "status_code", 200))
    if not (200 <= int(status) < 300):
        raise ValueError(message)
    return response


async def _response_json(response: Any, message: str) -> Mapping[str, Any]:
    method = getattr(response, "json", None)
    try:
        data = method() if callable(method) else response
        data = await _maybe_await(data)
        if not isinstance(data, Mapping):
            raise TypeError("response JSON must be an object")
        return data
    except Exception as exc:
        raise ValueError(message) from exc


async def _response_text(response: Any) -> str:
    method = getattr(response, "text", None)
    try:
        data = method() if callable(method) else ""
        data = await _maybe_await(data)
        return str(data)
    except Exception:
        return ""


def _now_rfc3339() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ssh_string(value: bytes) -> bytes:
    return len(value).to_bytes(4, "big") + value


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode()


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _b64url_decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise ValueError("agent identity JWT payload is not valid base64url") from exc


def _sealed_box_open(sealed: bytes, recipient_secret: bytes, recipient_public: bytes) -> bytes:
    if len(sealed) < 32 + 16:
        raise ValueError("sealed box is too short")
    ephemeral_public = sealed[:32]
    box = sealed[32:]
    nonce = hashlib.blake2b(ephemeral_public + recipient_public, digest_size=24).digest()
    shared = _crypto_box_beforenm(ephemeral_public, recipient_secret)
    return _secretbox_open(box, nonce, shared)


def _sealed_box_seal_for_test(message: bytes, recipient_public: bytes, ephemeral_secret: bytes) -> bytes:
    ephemeral_public = _x25519_base(ephemeral_secret)
    nonce = hashlib.blake2b(ephemeral_public + recipient_public, digest_size=24).digest()
    shared = _crypto_box_beforenm(recipient_public, ephemeral_secret)
    return ephemeral_public + _secretbox_seal(message, nonce, shared)


def _crypto_box_beforenm(public_key: bytes, secret_key: bytes) -> bytes:
    shared = _x25519(secret_key, public_key)
    return _hsalsa20(b"\x00" * 16, shared)


def _secretbox_open(box: bytes, nonce: bytes, key: bytes) -> bytes:
    if len(box) < 16:
        raise ValueError("ciphertext is too short")
    tag = box[:16]
    ciphertext = box[16:]
    stream = _xsalsa20_stream(len(ciphertext) + 32, nonce, key)
    poly_key = stream[:32]
    if not _constant_time_equal(_poly1305_mac(ciphertext, poly_key), tag):
        raise ValueError("authentication failed")
    return bytes(c ^ s for c, s in zip(ciphertext, stream[32:]))


def _secretbox_seal(message: bytes, nonce: bytes, key: bytes) -> bytes:
    stream = _xsalsa20_stream(len(message) + 32, nonce, key)
    poly_key = stream[:32]
    ciphertext = bytes(m ^ s for m, s in zip(message, stream[32:]))
    return _poly1305_mac(ciphertext, poly_key) + ciphertext


def _constant_time_equal(left: bytes, right: bytes) -> bool:
    if len(left) != len(right):
        return False
    diff = 0
    for a, b in zip(left, right):
        diff |= a ^ b
    return diff == 0


def _x25519_base(scalar: bytes) -> bytes:
    return _x25519(scalar, (9).to_bytes(32, "little"))


def _x25519(scalar: bytes, point: bytes) -> bytes:
    k = bytearray(scalar)
    k[0] &= 248
    k[31] &= 127
    k[31] |= 64
    x1 = int.from_bytes(point, "little")
    x2, z2 = 1, 0
    x3, z3 = x1, 1
    swap = 0
    p = 2**255 - 19
    a24 = 121665
    scalar_int = int.from_bytes(k, "little")
    for t in range(254, -1, -1):
        bit = (scalar_int >> t) & 1
        swap ^= bit
        if swap:
            x2, x3 = x3, x2
            z2, z3 = z3, z2
        swap = bit
        a = (x2 + z2) % p
        aa = (a * a) % p
        b = (x2 - z2) % p
        bb = (b * b) % p
        e = (aa - bb) % p
        c = (x3 + z3) % p
        d = (x3 - z3) % p
        da = (d * a) % p
        cb = (c * b) % p
        x3 = ((da + cb) ** 2) % p
        z3 = (x1 * ((da - cb) ** 2)) % p
        x2 = (aa * bb) % p
        z2 = (e * (aa + a24 * e)) % p
    if swap:
        x2, x3 = x3, x2
        z2, z3 = z3, z2
    return (x2 * pow(z2, p - 2, p) % p).to_bytes(32, "little")


def _xsalsa20_stream(length: int, nonce: bytes, key: bytes) -> bytes:
    subkey = _hsalsa20(nonce[:16], key)
    return _salsa20_stream(length, nonce[16:], subkey)


def _hsalsa20(nonce16: bytes, key: bytes) -> bytes:
    state = _salsa_state(key, nonce16)
    output = _salsa20_core(state)
    words = [0, 5, 10, 15, 6, 7, 8, 9]
    return b"".join(output[index].to_bytes(4, "little") for index in words)


def _salsa20_stream(length: int, nonce8: bytes, key: bytes) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < length:
        nonce_counter = nonce8 + counter.to_bytes(8, "little")
        block = _salsa20_block(key, nonce_counter)
        output.extend(block)
        counter += 1
    return bytes(output[:length])


def _salsa20_block(key: bytes, nonce16: bytes) -> bytes:
    state = _salsa_state(key, nonce16)
    core = _salsa20_core(state)
    final = [(core[i] + state[i]) & 0xFFFFFFFF for i in range(16)]
    return b"".join(word.to_bytes(4, "little") for word in final)


def _salsa_state(key: bytes, nonce16: bytes) -> list[int]:
    sigma = b"expand 32-byte k"
    words = [
        sigma[0:4],
        key[0:4],
        key[4:8],
        key[8:12],
        key[12:16],
        sigma[4:8],
        nonce16[0:4],
        nonce16[4:8],
        nonce16[8:12],
        nonce16[12:16],
        sigma[8:12],
        key[16:20],
        key[20:24],
        key[24:28],
        key[28:32],
        sigma[12:16],
    ]
    return [int.from_bytes(word, "little") for word in words]


def _salsa20_core(state: list[int]) -> list[int]:
    x = state.copy()
    for _ in range(10):
        x[4] ^= _rotl32((x[0] + x[12]) & 0xFFFFFFFF, 7)
        x[8] ^= _rotl32((x[4] + x[0]) & 0xFFFFFFFF, 9)
        x[12] ^= _rotl32((x[8] + x[4]) & 0xFFFFFFFF, 13)
        x[0] ^= _rotl32((x[12] + x[8]) & 0xFFFFFFFF, 18)
        x[9] ^= _rotl32((x[5] + x[1]) & 0xFFFFFFFF, 7)
        x[13] ^= _rotl32((x[9] + x[5]) & 0xFFFFFFFF, 9)
        x[1] ^= _rotl32((x[13] + x[9]) & 0xFFFFFFFF, 13)
        x[5] ^= _rotl32((x[1] + x[13]) & 0xFFFFFFFF, 18)
        x[14] ^= _rotl32((x[10] + x[6]) & 0xFFFFFFFF, 7)
        x[2] ^= _rotl32((x[14] + x[10]) & 0xFFFFFFFF, 9)
        x[6] ^= _rotl32((x[2] + x[14]) & 0xFFFFFFFF, 13)
        x[10] ^= _rotl32((x[6] + x[2]) & 0xFFFFFFFF, 18)
        x[3] ^= _rotl32((x[15] + x[11]) & 0xFFFFFFFF, 7)
        x[7] ^= _rotl32((x[3] + x[15]) & 0xFFFFFFFF, 9)
        x[11] ^= _rotl32((x[7] + x[3]) & 0xFFFFFFFF, 13)
        x[15] ^= _rotl32((x[11] + x[7]) & 0xFFFFFFFF, 18)
        x[1] ^= _rotl32((x[0] + x[3]) & 0xFFFFFFFF, 7)
        x[2] ^= _rotl32((x[1] + x[0]) & 0xFFFFFFFF, 9)
        x[3] ^= _rotl32((x[2] + x[1]) & 0xFFFFFFFF, 13)
        x[0] ^= _rotl32((x[3] + x[2]) & 0xFFFFFFFF, 18)
        x[6] ^= _rotl32((x[5] + x[4]) & 0xFFFFFFFF, 7)
        x[7] ^= _rotl32((x[6] + x[5]) & 0xFFFFFFFF, 9)
        x[4] ^= _rotl32((x[7] + x[6]) & 0xFFFFFFFF, 13)
        x[5] ^= _rotl32((x[4] + x[7]) & 0xFFFFFFFF, 18)
        x[11] ^= _rotl32((x[10] + x[9]) & 0xFFFFFFFF, 7)
        x[8] ^= _rotl32((x[11] + x[10]) & 0xFFFFFFFF, 9)
        x[9] ^= _rotl32((x[8] + x[11]) & 0xFFFFFFFF, 13)
        x[10] ^= _rotl32((x[9] + x[8]) & 0xFFFFFFFF, 18)
        x[12] ^= _rotl32((x[15] + x[14]) & 0xFFFFFFFF, 7)
        x[13] ^= _rotl32((x[12] + x[15]) & 0xFFFFFFFF, 9)
        x[14] ^= _rotl32((x[13] + x[12]) & 0xFFFFFFFF, 13)
        x[15] ^= _rotl32((x[14] + x[13]) & 0xFFFFFFFF, 18)
    return x


def _rotl32(value: int, shift: int) -> int:
    return ((value << shift) | (value >> (32 - shift))) & 0xFFFFFFFF


def _poly1305_mac(message: bytes, key: bytes) -> bytes:
    r = int.from_bytes(key[:16], "little")
    r &= 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
    s = int.from_bytes(key[16:32], "little")
    p = (1 << 130) - 5
    acc = 0
    for index in range(0, len(message), 16):
        block = message[index : index + 16]
        n = int.from_bytes(block + b"\x01", "little")
        acc = ((acc + n) * r) % p
    return ((acc + s) % (1 << 128)).to_bytes(16, "little")


# Minimal Ed25519 implementation for the crate's standard-library port.
_P = 2**255 - 19
_Q = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, -1, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)
_B = (
    15112221349535400772501151409588531511454012693041857206046113283949847762202,
    46316835694926478169428394003475163141307993866256225615783033603165251855960,
)


def _ed25519_public_key(seed: bytes) -> bytes:
    h = hashlib.sha512(seed).digest()
    a = _clamp(int.from_bytes(h[:32], "little"))
    return _encode_point(_scalarmult(_B, a))


def _ed25519_sign(seed: bytes, message: bytes) -> bytes:
    h = hashlib.sha512(seed).digest()
    a = _clamp(int.from_bytes(h[:32], "little"))
    prefix = h[32:]
    public = _encode_point(_scalarmult(_B, a))
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _Q
    encoded_r = _encode_point(_scalarmult(_B, r))
    k = int.from_bytes(hashlib.sha512(encoded_r + public + message).digest(), "little") % _Q
    s = (r + k * a) % _Q
    return encoded_r + s.to_bytes(32, "little")


def _clamp(value: int) -> int:
    value &= ~(7)
    value &= ~(1 << 255)
    value |= 1 << 254
    return value


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = (x * _I) % _P
    if x % 2 != 0:
        x = _P - x
    return x


def _edwards_add(p: tuple[int, int], q: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = p
    x2, y2 = q
    den = pow(1 + _D * x1 * x2 * y1 * y2, _P - 2, _P)
    x3 = (x1 * y2 + x2 * y1) * den % _P
    den = pow(1 - _D * x1 * x2 * y1 * y2, _P - 2, _P)
    y3 = (y1 * y2 + x1 * x2) * den % _P
    return x3, y3


def _scalarmult(point: tuple[int, int], scalar: int) -> tuple[int, int]:
    result = (0, 1)
    addend = point
    while scalar:
        if scalar & 1:
            result = _edwards_add(result, addend)
        addend = _edwards_add(addend, addend)
        scalar >>= 1
    return result


def _encode_point(point: tuple[int, int]) -> bytes:
    x, y = point
    bits = bytearray(y.to_bytes(32, "little"))
    bits[31] |= (x & 1) << 7
    return bytes(bits)


__all__ = [
    "AGENT_IDENTITY_JWKS_TIMEOUT_SECONDS",
    "AGENT_IDENTITY_JWT_AUDIENCE",
    "AGENT_IDENTITY_JWT_ISSUER",
    "AGENT_TASK_REGISTRATION_TIMEOUT_SECONDS",
    "AgentBillOfMaterials",
    "AgentIdentityJwtClaims",
    "AgentIdentityKey",
    "AgentTaskAuthorizationTarget",
    "GeneratedAgentKeyMaterial",
    "agent_identity_biscuit_url",
    "agent_identity_jwks_url",
    "agent_identity_request_id",
    "agent_registration_url",
    "agent_task_registration_url",
    "authorization_header_for_agent_task",
    "build_abom",
    "curve25519_secret_key_from_private_key_pkcs8_base64",
    "decode_agent_identity_jwt",
    "decode_agent_identity_jwt_payload",
    "decrypt_task_id_response",
    "encode_ssh_ed25519_public_key",
    "fetch_agent_identity_jwks",
    "generate_agent_key_material",
    "public_key_ssh_from_private_key_pkcs8_base64",
    "register_agent_task",
    "serialize_agent_assertion",
    "sign_agent_assertion_payload",
    "sign_task_registration_payload",
    "signing_key_from_private_key_pkcs8_base64",
    "task_id_from_register_task_response",
    "verifying_key_from_private_key_pkcs8_base64",
]
