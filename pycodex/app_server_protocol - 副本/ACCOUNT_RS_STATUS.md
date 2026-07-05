# app-server-protocol `protocol/v2/account.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/account.rs`

Python target: `pycodex/app_server_protocol/account.py`

Status: implemented module contract.

## Covered Rust items

- `Account`
- `LoginAccountParams`
- `LoginAccountResponse`
- `CancelLoginAccountParams`
- `CancelLoginAccountStatus`
- `CancelLoginAccountResponse`
- `LogoutAccountResponse`
- `ChatgptAuthTokensRefreshReason`
- `ChatgptAuthTokensRefreshParams`
- `ChatgptAuthTokensRefreshResponse`
- `GetAccountRateLimitsResponse`
- `SendAddCreditsNudgeEmailParams`
- `AddCreditsNudgeCreditType`
- `SendAddCreditsNudgeEmailResponse`
- `AddCreditsNudgeEmailStatus`
- `GetAccountParams`
- `GetAccountResponse`
- `AccountUpdatedNotification`
- `AccountRateLimitsUpdatedNotification`
- `RateLimitSnapshot`
- `RateLimitReachedType`
- `RateLimitWindow`
- `CreditsSnapshot`
- `AccountLoginCompletedNotification`

## Notes

- Tagged variants preserve Rust wire names such as `apiKey`, `chatgpt`,
  `chatgptDeviceCode`, `chatgptAuthTokens`, and `amazonBedrock`.
- False default booleans with Rust `skip_serializing_if` are omitted from
  serialized mappings.
- `PlanType` is reused from `pycodex.protocol.account` for stable plan wire
  values, while this module owns the app-server v2 field names.
- `AuthMode` is included for `AccountUpdatedNotification`, mirroring the common
  app-server auth-mode wire values used by this Rust module.

## Validation

- Compile check: `python -m py_compile
  pycodex/app_server_protocol/account.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: account/provider conversion, login tagged variants, default
  boolean omission, auth-token refresh, nudge params/response, get-account,
  rate-limit snapshots, and account notifications.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
