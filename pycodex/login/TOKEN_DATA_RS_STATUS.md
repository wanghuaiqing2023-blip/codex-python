# token_data.rs alignment

Rust crate: `codex-login`

Rust module: `codex/codex-rs/login/src/token_data.rs`

Python module: `pycodex/login/token_data.py`

Status: `complete`

Aligned behavior:

- `TokenData` stores parsed `IdTokenInfo`, access token, refresh token, and
  optional account id.
- `TokenData.from_mapping()` mirrors Rust serde deserialization by parsing the
  raw `id_token` JWT into `IdTokenInfo`.
- `TokenData.to_json_dict()` mirrors Rust serde serialization by emitting the
  raw JWT string for `id_token`.
- `parse_chatgpt_jwt_claims()` decodes the JWT payload, reads top-level/profile
  email claims, ChatGPT auth claims, user/account identifiers, FedRAMP flag, and
  known/unknown plan types.
- `parse_jwt_expiration()` decodes the standard `exp` claim into a UTC
  `datetime`, returning `None` when the claim is absent.
- `IdTokenInfo` exposes display plan type, raw plan type, workspace-account, and
  FedRAMP helpers matching the Rust methods.

Validation:

- Not run in this turn; current automation defers actual test execution until the crate functional code is complete.
