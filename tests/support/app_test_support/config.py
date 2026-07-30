from __future__ import annotations

from pathlib import Path
from typing import Mapping


def write_mock_responses_config_toml(
    codex_home: Path,
    server_uri: str,
    feature_flags: Mapping[object, bool],
    auto_compact_limit: int,
    requires_openai_auth: bool | None,
    model_provider_id: str,
    compact_prompt: str,
) -> None:
    features = "\n".join(
        f"{getattr(feature, 'value', feature)} = {str(enabled).lower()}"
        for feature, enabled in sorted(feature_flags.items(), key=lambda item: str(item[0]))
    )
    requires_line = "requires_openai_auth = true\n" if requires_openai_auth else ""
    provider_name = "OpenAI" if requires_openai_auth else "Mock provider for test"
    openai_base_url = (
        f'openai_base_url = "{server_uri}/v1"\n'
        if model_provider_id == "openai"
        else ""
    )
    text = f'''
model = "mock-model"
approval_policy = "never"
sandbox_mode = "read-only"
compact_prompt = "{compact_prompt}"
model_auto_compact_token_limit = {auto_compact_limit}

model_provider = "{model_provider_id}"
{openai_base_url}
[features]
{features}

[model_providers.{model_provider_id}]
name = "{provider_name}"
base_url = "{server_uri}/v1"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0
supports_websockets = false
{requires_line}'''
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / "config.toml").write_text(text, encoding="utf-8")


def write_mock_responses_config_toml_with_chatgpt_base_url(
    codex_home: Path,
    server_uri: str,
    chatgpt_base_url: str,
) -> None:
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / "config.toml").write_text(
        f'''
model = "mock-model"
approval_policy = "never"
sandbox_mode = "read-only"
chatgpt_base_url = "{chatgpt_base_url}"

model_provider = "mock_provider"

[model_providers.mock_provider]
name = "Mock provider for test"
base_url = "{server_uri}/v1"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0
''',
        encoding="utf-8",
    )
