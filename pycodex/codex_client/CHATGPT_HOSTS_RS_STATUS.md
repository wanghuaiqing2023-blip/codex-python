# `codex-client/src/chatgpt_hosts.rs` alignment status

Rust crate: `codex-client`

Rust module: `src/chatgpt_hosts.rs`

Python module: `pycodex/codex_client/chatgpt_hosts.py`

Status: `complete`

Covered behavior:

- Exact first-party ChatGPT hosts:
  `chatgpt.com`, `chat.openai.com`, and `chatgpt-staging.com`.
- Subdomains of `chatgpt.com` and `chatgpt-staging.com`.
- Rejection of suffix-trick hosts such as `evilchatgpt.com`,
  `chatgpt.com.evil.example`, `api.openai.com`, and
  `foo.chat.openai.com`.

Evidence:

- Rust source: `codex/codex-rs/codex-client/src/chatgpt_hosts.rs`.
- Rust test: `recognizes_chatgpt_hosts_without_suffix_tricks`.
- Python tests: `tests/test_codex_client_chatgpt_hosts_rs.py`.

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `1 test`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/codex_client/__init__.py pycodex/codex_client/chatgpt_hosts.py tests/test_codex_client_chatgpt_hosts_rs.py`
  passed on 2026-06-20.
