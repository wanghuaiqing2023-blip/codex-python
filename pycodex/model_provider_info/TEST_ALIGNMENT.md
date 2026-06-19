# codex-model-provider-info test alignment

Rust crate: `codex-model-provider-info`

Python package: `pycodex/model_provider_info`

Status: `complete`

Certified modules:

- `codex/codex-rs/model-provider-info/src/lib.rs` -> `pycodex/model_provider_info/__init__.py`
- `codex/codex-rs/model-provider-info/src/model_provider_info_tests.rs` -> `tests/test_model_provider_info.py`

Rust behavior covered by `tests/test_model_provider_info.py`:

- TOML/mapping deserialization for Ollama, Azure, custom headers, WebSocket
  connect timeout, command auth, and AWS auth config.
- removed `wire_api = "chat"` produces the Rust helpful error.
- OpenAI provider defaults, ChatGPT/API-key base URL selection, environment
  headers, retry caps/defaults, and timeout defaults.
- environment API-key lookup rejects missing or blank values.
- AWS/auth validation rejects conflicting auth modes and AWS WebSocket usage.
- Amazon Bedrock provider defaults and mantle client-agent header.
- built-in provider catalog includes OpenAI, Amazon Bedrock, Ollama, and
  LM Studio OSS providers.
- OSS provider environment overrides.
- configured-provider merge behavior, including custom providers and the
  Amazon Bedrock profile/region-only override rule.
- remote compaction support for OpenAI/Azure providers only.

Validation:

- `python -m pytest tests/test_model_provider_info.py -q` (`18 passed`)
- `python -m py_compile pycodex/model_provider_info/__init__.py tests/test_model_provider_info.py` (passed)
