# codex-client/src/chatgpt_cloudflare_cookies.rs status

Rust module: `codex/codex-rs/codex-client/src/chatgpt_cloudflare_cookies.rs`

Python module: `pycodex/codex_client/chatgpt_cloudflare_cookies.py`

Status: `complete`

Ported contract:

- Shared ChatGPT Cloudflare cookie store hook via `with_chatgpt_cloudflare_cookie_store`.
- Only HTTPS first-party ChatGPT hosts are accepted.
- Only Cloudflare service cookie names are stored and returned.
- Non-Cloudflare ChatGPT account/session/auth cookies are rejected.
- Stored cookies are not returned for non-ChatGPT hosts.
- Plain HTTP and non-HTTPS ChatGPT URLs are rejected.
- `cf_chl_*` challenge cookies are allowed.

Validation:

- `tests/test_codex_client_chatgpt_cloudflare_cookies_rs.py`
- Focused command passed on 2026-06-20:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`

