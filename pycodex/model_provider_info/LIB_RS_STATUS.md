# codex-model-provider-info src/lib.rs status

Rust coordinate: `codex/codex-rs/model-provider-info/src/lib.rs`

Python coordinate: `pycodex/model_provider_info/__init__.py`

Status: `complete`

Behavior contract:

- define model-provider registry constants and `WireApi`.
- define `ModelProviderInfo` and `ModelProviderAwsAuthInfo` provider shapes.
- deserialize provider config from TOML/mappings with Rust defaults and removed
  chat-wire API errors.
- validate mutually exclusive auth/AWS provider fields.
- project provider info into an API provider shape with headers, query params,
  retry config, and stream timeout.
- construct built-in OpenAI, Amazon Bedrock, Ollama, and LM Studio providers.
- merge configured providers into the built-in provider catalog.

Evidence:

- Python preserves the Rust public constants, provider constructors, retry and
  timeout defaults/caps, auth validation messages, Bedrock override rule, OSS
  environment overrides, and remote-compaction predicate.
- `ModelProviderInfo.from_toml` and `from_mapping` cover the Rust serde
  behavior used by config loading and tests, including command auth defaults
  and zero refresh interval handling.

Validation:

- `python -m pytest tests/test_model_provider_info.py -q` (`18 passed`)
- `python -m py_compile pycodex/model_provider_info/__init__.py tests/test_model_provider_info.py` (passed)
