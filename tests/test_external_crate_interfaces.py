"""External Rust crate public API parity contracts.

These tests are anchored to the external crates' own source, not only
``codex-core`` use sites.
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import pytest

from pycodex.protocol import AskForApproval, SandboxPolicy, SessionSource, ThreadId, ThreadMemoryMode, ThreadSource


ROOT = Path(__file__).resolve().parents[1]

CORE_RUNTIME_DEPENDENCY_PACKAGES = {
    "codex-analytics": ("pycodex/analytics", "codex-analytics", "codex/codex-rs/analytics"),
    "codex-api": ("pycodex/api", "codex-api", "codex/codex-rs/codex-api"),
    "codex-code-mode": ("pycodex/code_mode", "codex-code-mode", "codex/codex-rs/code-mode"),
    "codex-core-plugins": ("pycodex/core_plugins", "codex-core-plugins", "codex/codex-rs/core-plugins"),
    "codex-exec-server": ("pycodex/exec_server", "codex-exec-server", "codex/codex-rs/exec-server"),
    "codex-extension-api": ("pycodex/extension_api", "codex-extension-api", "codex/codex-rs/ext/extension-api"),
    "codex-feedback": ("pycodex/feedback", "codex-feedback", "codex/codex-rs/feedback"),
    "codex-mcp": ("pycodex/mcp", "codex-mcp", "codex/codex-rs/codex-mcp"),
    "codex-memories-read": ("pycodex/memories_read", "codex-memories-read", "codex/codex-rs/memories/read"),
    "codex-otel": ("pycodex/otel", "codex-otel", "codex/codex-rs/otel"),
    "codex-plugin": ("pycodex/plugin", "codex-plugin", "codex/codex-rs/plugin"),
    "codex-rmcp-client": ("pycodex/rmcp_client", "codex-rmcp-client", "codex/codex-rs/rmcp-client"),
    "codex-utils-image": ("pycodex/utils/image", "codex-utils-image", "codex/codex-rs/utils/image"),
    "codex-windows-sandbox": ("pycodex/windows_sandbox", "codex-windows-sandbox", "codex/codex-rs/windows-sandbox-rs"),
    "codex-shell-escalation": ("pycodex/shell_escalation", "codex-shell-escalation", "codex/codex-rs/shell-escalation"),
}


def test_core_runtime_dependency_packages_have_python_interfaces_and_readmes() -> None:
    """Rust: ``core/Cargo.toml`` runtime ``codex-*`` dependencies."""

    for dependency_name, (package_path, crate_name, rust_anchor) in CORE_RUNTIME_DEPENDENCY_PACKAGES.items():
        package_dir = ROOT / package_path
        assert package_dir.is_dir(), dependency_name
        assert (package_dir / "__init__.py").is_file(), dependency_name
        readme = package_dir / "README.md"
        assert readme.is_file(), dependency_name
        readme_text = readme.read_text(encoding="utf-8")
        assert f"Rust crate: `{crate_name}`" in readme_text, dependency_name
        assert rust_anchor in readme_text, dependency_name


def test_model_provider_info_defaults_validation_and_catalog() -> None:
    """Rust: ``model-provider-info/src/lib.rs``."""

    from pycodex.model_provider_info import (
        AMAZON_BEDROCK_PROVIDER_ID,
        CHATGPT_CODEX_BASE_URL,
        DEFAULT_REQUEST_MAX_RETRIES,
        DEFAULT_STREAM_IDLE_TIMEOUT_MS,
        DEFAULT_STREAM_MAX_RETRIES,
        DEFAULT_WEBSOCKET_CONNECT_TIMEOUT_MS,
        LMSTUDIO_OSS_PROVIDER_ID,
        ModelProviderAwsAuthInfo,
        ModelProviderInfo,
        OLLAMA_OSS_PROVIDER_ID,
        OPENAI_PROVIDER_ID,
        WireApi,
        built_in_model_providers,
        merge_configured_model_providers,
    )

    with pytest.raises(ValueError, match="wire_api"):
        WireApi.parse("chat")

    provider = ModelProviderInfo.create_openai_provider(None)
    assert provider.name == "OpenAI"
    assert provider.requires_openai_auth is True
    assert provider.supports_websockets is True
    assert provider.request_max_retries() == DEFAULT_REQUEST_MAX_RETRIES
    assert provider.stream_max_retries() == DEFAULT_STREAM_MAX_RETRIES
    assert provider.stream_idle_timeout() == DEFAULT_STREAM_IDLE_TIMEOUT_MS
    assert provider.websocket_connect_timeout() == DEFAULT_WEBSOCKET_CONNECT_TIMEOUT_MS
    assert provider.to_api_provider("chatgpt").base_url == CHATGPT_CODEX_BASE_URL

    with pytest.raises(ValueError, match="provider aws cannot be combined with env_key"):
        ModelProviderInfo(aws=ModelProviderAwsAuthInfo(), env_key="OPENAI_API_KEY").validate()

    catalog = built_in_model_providers(None)
    assert {OPENAI_PROVIDER_ID, AMAZON_BEDROCK_PROVIDER_ID, OLLAMA_OSS_PROVIDER_ID, LMSTUDIO_OSS_PROVIDER_ID} <= set(catalog)

    merged = merge_configured_model_providers(
        catalog,
        {AMAZON_BEDROCK_PROVIDER_ID: ModelProviderInfo(aws=ModelProviderAwsAuthInfo(profile="p", region="r"))},
    )
    assert merged[AMAZON_BEDROCK_PROVIDER_ID].aws.profile == "p"
    assert merged[AMAZON_BEDROCK_PROVIDER_ID].aws.region == "r"


def test_model_provider_bearer_auth_and_configured_provider() -> None:
    """Rust: ``model-provider/src/lib.rs``, ``provider.rs``, ``bearer_auth_provider.rs``."""

    from pycodex.model_provider import (
        DEFAULT_APPROVAL_REVIEW_PREFERRED_MODEL,
        BearerAuthProvider,
        ProviderCapabilities,
        create_model_provider,
    )
    from pycodex.model_provider_info import ModelProviderInfo

    auth = BearerAuthProvider.for_test("token", "workspace-1")
    auth.is_fedramp_account = True
    headers: dict[str, str] = {}
    auth.add_auth_headers(headers)
    assert headers == {
        "Authorization": "Bearer token",
        "ChatGPT-Account-ID": "workspace-1",
        "X-OpenAI-Fedramp": "true",
    }

    provider_info = ModelProviderInfo.create_openai_provider("https://example.test/v1")
    provider = create_model_provider(provider_info)
    assert provider.info() is provider_info
    assert provider.capabilities() == ProviderCapabilities()
    assert provider.approval_review_preferred_model() == DEFAULT_APPROVAL_REVIEW_PREFERRED_MODEL
    assert asyncio.run(provider.runtime_base_url()) == "https://example.test/v1"


def test_thread_store_types_merge_and_in_memory_store_contract() -> None:
    """Rust: ``thread-store/src/lib.rs``, ``types.rs``, ``store.rs``, ``in_memory.rs``."""

    from pycodex.thread_store import (
        AppendThreadItemsParams,
        CreateThreadParams,
        InMemoryThreadStore,
        ListTurnsParams,
        LoadThreadHistoryParams,
        SortDirection,
        StoredTurnItemsView,
        ThreadEventPersistenceMode,
        ThreadMetadataPatch,
        ThreadPersistenceMetadata,
        ThreadStoreError,
        UpdateThreadMetadataParams,
    )

    thread_id = ThreadId.new()
    store = InMemoryThreadStore()
    metadata = ThreadPersistenceMetadata(Path.cwd(), "openai", ThreadMemoryMode.ENABLED)

    asyncio.run(
        store.create_thread(
            CreateThreadParams(
                thread_id=thread_id,
                forked_from_id=None,
                source=SessionSource.exec(),
                thread_source=ThreadSource.USER,
                base_instructions=None,
                dynamic_tools=(),
                metadata=metadata,
                event_persistence_mode=ThreadEventPersistenceMode.LIMITED,
            )
        )
    )
    asyncio.run(store.append_items(AppendThreadItemsParams(thread_id, ("item-1", "item-2"))))
    history = asyncio.run(store.load_history(LoadThreadHistoryParams(thread_id, include_archived=False)))
    assert history.items == ("item-1", "item-2")

    patch = ThreadMetadataPatch(
        preview="hello",
        model="gpt-test",
        approval_mode=AskForApproval.NEVER,
        sandbox_policy=SandboxPolicy.danger_full_access(),
    )
    updated = asyncio.run(
        store.update_thread_metadata(
            UpdateThreadMetadataParams(thread_id, patch, include_archived=False)
        )
    )
    assert updated.preview == "hello"
    assert updated.model == "gpt-test"

    with pytest.raises(ThreadStoreError) as err:
        asyncio.run(
            store.list_turns(
                ListTurnsParams(
                    thread_id=thread_id,
                    include_archived=True,
                    cursor=None,
                    page_size=10,
                    sort_direction=SortDirection.ASC,
                    items_view=StoredTurnItemsView.SUMMARY,
                )
            )
        )
    assert err.value.kind == "unsupported"
    assert err.value.fields["operation"] == "list_turns"

    calls = asyncio.run(store.calls())
    assert calls.create_thread == 1
    assert calls.append_items == 1
    assert calls.load_history == 1
    assert calls.update_thread_metadata == 1


def test_response_debug_context_extracts_headers_and_telemetry_messages() -> None:
    """Rust: ``response-debug-context/src/lib.rs``."""

    from pycodex.response_debug_context import (
        ResponseDebugContext,
        extract_response_debug_context,
        extract_response_debug_context_from_api_error,
        telemetry_api_error_message,
        telemetry_transport_error_message,
    )

    encoded = base64.b64encode(json.dumps({"error": {"code": "token_expired"}}).encode()).decode()
    transport = {
        "type": "http",
        "status": 401,
        "headers": {
            "x-oai-request-id": "req-auth",
            "cf-ray": "ray-auth",
            "x-openai-authorization-error": "missing_authorization_header",
            "x-error-json": encoded,
        },
        "body": '{"error":{"message":"plain text error"},"status":401}',
    }

    assert extract_response_debug_context(transport) == ResponseDebugContext(
        request_id="req-auth",
        cf_ray="ray-auth",
        auth_error="missing_authorization_header",
        auth_error_code="token_expired",
    )
    assert extract_response_debug_context_from_api_error({"type": "transport", "transport": transport}).request_id == "req-auth"
    assert telemetry_transport_error_message(transport) == "http 401"
    assert telemetry_api_error_message({"type": "transport", "transport": transport}) == "http 401"
    assert telemetry_api_error_message({"type": "context_window_exceeded"}) == "context window exceeded"


def test_terminal_detection_user_agent_and_priority_rules() -> None:
    """Rust: ``terminal-detection/src/lib.rs`` and ``terminal_tests.rs``."""

    from pycodex.terminal_detection import TerminalName, terminal_info, user_agent

    env = {"TERM_PROGRAM": "iTerm.app", "TERM_PROGRAM_VERSION": "3.5.0", "WEZTERM_VERSION": "ignored"}
    terminal = terminal_info(env)
    assert terminal.name is TerminalName.ITERM2
    assert terminal.term_program == "iTerm.app"
    assert terminal.version == "3.5.0"
    assert terminal.user_agent_token() == "iTerm.app/3.5.0"
    assert user_agent(env) == "iTerm.app/3.5.0"

    assert terminal_info({"WEZTERM_VERSION": "20240203"}).name is TerminalName.WEZTERM
    assert terminal_info({"TERM": "dumb"}).name is TerminalName.DUMB
    assert terminal_info({"ZELLIJ": "1"}).is_zellij() is True
    assert user_agent({"TERM_PROGRAM": "bad value/with spaces"}) == "bad_value/with_spaces"


def test_absolute_path_buf_resolves_base_and_checked_paths(tmp_path: Path) -> None:
    """Rust: ``utils/absolute-path/src/lib.rs``."""

    from pycodex.utils.absolute_path import AbsolutePathBuf, AbsolutePathBufGuard

    absolute_file = tmp_path / "file.txt"
    assert AbsolutePathBuf.resolve_path_against_base(absolute_file, tmp_path).as_path() == absolute_file
    assert AbsolutePathBuf.resolve_path_against_base("./nested/../file.txt", tmp_path).as_path() == absolute_file

    with pytest.raises(ValueError, match="path is not absolute"):
        AbsolutePathBuf.from_absolute_path_checked("relative/path")

    with pytest.raises(ValueError, match="without a base path"):
        AbsolutePathBuf.deserialize("relative/path")

    with AbsolutePathBufGuard(tmp_path):
        assert AbsolutePathBuf.deserialize("subdir/file.txt").as_path() == tmp_path / "subdir" / "file.txt"

    abs_path = AbsolutePathBuf.from_absolute_path_checked(tmp_path)
    assert abs_path.join("child").as_path() == tmp_path / "child"
    assert abs_path.parent() is not None


def test_utils_pty_pipe_process_public_contract(tmp_path: Path) -> None:
    """Rust: ``utils/pty/src/lib.rs``, ``process.rs``, ``pipe.rs``, ``pty.rs``."""

    import sys

    from pycodex.utils.pty import DEFAULT_OUTPUT_BYTES_CAP, TerminalSize, spawn_pipe_process, spawn_pipe_process_no_stdin

    async def run() -> None:
        assert DEFAULT_OUTPUT_BYTES_CAP == 1024 * 1024
        assert TerminalSize() == TerminalSize(rows=24, cols=80)

        with pytest.raises(ValueError, match="missing program for pipe spawn"):
            await spawn_pipe_process("", [], tmp_path, {})

        child = await spawn_pipe_process(
            sys.executable,
            ["-c", "import sys; data=sys.stdin.buffer.read(); print(data.decode().upper(), end='')"],
            tmp_path,
            {},
        )
        await child.session.writer_sender().send(b"hello")
        child.session.close_stdin()
        assert await child.stdout_rx.get() == b"HELLO"
        assert await child.exit_rx == 0
        assert child.session.has_exited() is True
        assert child.session.exit_code() == 0

        no_stdin = await spawn_pipe_process_no_stdin(
            sys.executable,
            ["-c", "import sys; print(sys.stdin.read() == '')"],
            tmp_path,
            {},
        )
        assert (await no_stdin.stdout_rx.get()).strip() == b"True"
        assert await no_stdin.exit_rx == 0

    asyncio.run(run())


def test_hooks_public_api_keys_payload_and_registry_defaults(tmp_path: Path) -> None:
    """Rust: ``hooks/src/lib.rs``, ``types.rs``, ``legacy_notify.rs``, ``registry.rs``."""

    from datetime import datetime, timezone

    from pycodex.hooks import (
        HOOK_EVENT_NAMES,
        HOOK_EVENT_NAMES_WITH_MATCHERS,
        Hook,
        HookEvent,
        HookEventAfterAgent,
        HookPayload,
        HookResult,
        Hooks,
        HooksConfig,
        PluginHookDeclaration,
        hook_key,
        legacy_notify_json,
        list_hooks,
        plugin_hook_declarations,
    )
    from pycodex.protocol import HookEventName

    assert HOOK_EVENT_NAMES == (
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "PreCompact",
        "PostCompact",
        "SessionStart",
        "UserPromptSubmit",
        "SubagentStart",
        "SubagentStop",
        "Stop",
    )
    assert "Stop" not in HOOK_EVENT_NAMES_WITH_MATCHERS
    assert hook_key("file:/tmp/hooks.json", HookEventName.PRE_TOOL_USE, 0, 1) == "file:/tmp/hooks.json:pre_tool_use:0:1"

    payload = HookPayload(
        session_id="session-1",
        cwd=tmp_path,
        client="codex-tui",
        triggered_at=datetime(2026, 6, 7, 1, 2, 3, tzinfo=timezone.utc),
        hook_event=HookEvent.AfterAgent(
            HookEventAfterAgent(
                thread_id="b5f6c1c2-1111-2222-3333-444455556666",
                turn_id="12345",
                input_messages=["Rename `foo` to `bar`."],
                last_assistant_message="Done.",
            )
        ),
    )
    assert payload.to_mapping()["hook_event"]["event_type"] == "after_agent"
    notify = json.loads(legacy_notify_json(payload))
    assert notify == {
        "type": "agent-turn-complete",
        "thread-id": "b5f6c1c2-1111-2222-3333-444455556666",
        "turn-id": "12345",
        "cwd": str(tmp_path),
        "client": "codex-tui",
        "input-messages": ["Rename `foo` to `bar`."],
        "last-assistant-message": "Done.",
    }

    async def run() -> None:
        default_response = await Hook().execute(payload)
        assert default_response.hook_name == "default"
        assert default_response.result == HookResult.Success()

        hooks = Hooks.new(HooksConfig())
        assert hooks.startup_warnings() == []
        assert await hooks.dispatch(payload) == []
        assert list_hooks(HooksConfig()).hooks == []

    asyncio.run(run())

    source = {
        "plugin_id": "demo@test",
        "source_relative_path": "hooks/hooks.json",
        "hooks": {
            HookEventName.PRE_TOOL_USE: [{"hooks": ["prompt", "command"]}],
            HookEventName.SESSION_START: [{"hooks": ["agent"]}],
        },
    }
    assert plugin_hook_declarations([source]) == [
        PluginHookDeclaration("demo@test:hooks/hooks.json:pre_tool_use:0:0", HookEventName.PRE_TOOL_USE),
        PluginHookDeclaration("demo@test:hooks/hooks.json:pre_tool_use:0:1", HookEventName.PRE_TOOL_USE),
        PluginHookDeclaration("demo@test:hooks/hooks.json:session_start:0:0", HookEventName.SESSION_START),
    ]


def test_rollout_trace_writer_payload_refs_and_noop_contexts(tmp_path: Path) -> None:
    """Rust: ``rollout-trace/src/lib.rs``, ``payload.rs``, ``writer.rs``, ``mcp.rs``."""

    from pycodex.rollout_trace import (
        MCP_CALL_ID_META_KEY,
        RAW_TRACE_EVENT_SCHEMA_VERSION,
        InferenceTraceAttempt,
        McpCallTraceContext,
        RawPayloadKind,
        RawTraceEventContext,
        RawTraceEventPayload,
        REDUCED_STATE_FILE_NAME,
        ThreadTraceContext,
        TraceWriter,
    )

    assert REDUCED_STATE_FILE_NAME == "state.json"

    writer = TraceWriter.create(tmp_path, "trace-1", "rollout-1", "thread-root")
    payload_ref = writer.write_json_payload(RawPayloadKind.PROTOCOL_EVENT, {"source": "test"})
    assert payload_ref.raw_payload_id == "raw_payload:1"
    assert payload_ref.kind is RawPayloadKind.PROTOCOL_EVENT
    assert payload_ref.path == "payloads/1.json"
    assert json.loads((tmp_path / payload_ref.path).read_text()) == {"source": "test"}

    event = writer.append_with_context(
        RawTraceEventContext(thread_id="thread-root", codex_turn_id="turn-1"),
        RawTraceEventPayload.variant("ProtocolEventObserved", event_type="test", event_payload=payload_ref),
    )
    assert event.schema_version == RAW_TRACE_EVENT_SCHEMA_VERSION
    assert event.seq == 1
    assert event.payload.raw_payload_refs() == [payload_ref]

    logged = json.loads((tmp_path / "trace.jsonl").read_text().strip())
    assert logged["seq"] == 1
    assert logged["thread_id"] == "thread-root"
    assert logged["payload"]["type"] == "protocol_event_observed"

    assert McpCallTraceContext.disabled().add_request_meta({"source": "test"}) == {"source": "test"}
    assert McpCallTraceContext.enabled("mcp-call-id").add_request_meta({"source": "test"}) == {
        "source": "test",
        MCP_CALL_ID_META_KEY: "mcp-call-id",
    }

    headers: dict[str, str] = {}
    InferenceTraceAttempt.disabled().add_request_headers(headers)
    assert headers == {}
    assert ThreadTraceContext.disabled().is_enabled() is False


def test_async_utils_or_cancel_contract() -> None:
    """Rust: ``async-utils/src/lib.rs``."""

    from pycodex.async_utils import CancellationToken, CancelledError, or_cancel

    async def run() -> None:
        token = CancellationToken()
        assert await or_cancel(asyncio.sleep(0, result=42), token) == 42

        cancelled = CancellationToken()
        cancelled.cancel()
        with pytest.raises(CancelledError) as err:
            await or_cancel(asyncio.sleep(0.05, result=5), cancelled)
        assert err.value.kind.value == "cancelled"

        delayed = CancellationToken()

        async def cancel_soon() -> None:
            await asyncio.sleep(0.01)
            delayed.cancel()

        asyncio.create_task(cancel_soon())
        with pytest.raises(CancelledError):
            await or_cancel(asyncio.sleep(0.1, result=7), delayed)

    asyncio.run(run())


def test_install_context_layout_standalone_and_managed_detection(tmp_path: Path) -> None:
    """Rust: ``install-context/src/lib.rs``."""

    import sys

    from pycodex.install_context import (
        CodexPackageLayout,
        InstallContext,
        InstallMethod,
        InstallMethodKind,
        StandalonePlatform,
    )

    exe_name = "codex.exe" if sys.platform.startswith("win") else "codex"
    rg_name = "rg.exe" if sys.platform.startswith("win") else "rg"

    package_dir = tmp_path / "package"
    bin_dir = package_dir / "bin"
    resources_dir = package_dir / "codex-resources"
    path_dir = package_dir / "codex-path"
    bin_dir.mkdir(parents=True)
    resources_dir.mkdir()
    path_dir.mkdir()
    (package_dir / "codex-package.json").write_text("{}", encoding="utf-8")
    exe_path = bin_dir / exe_name
    exe_path.write_text("", encoding="utf-8")
    (resources_dir / "helper").write_text("", encoding="utf-8")
    (path_dir / rg_name).write_text("", encoding="utf-8")

    layout = CodexPackageLayout.from_exe(exe_path)
    assert layout is not None
    assert layout.package_dir.as_path() == package_dir.resolve()
    assert layout.bin_dir.as_path() == bin_dir.resolve()
    assert layout.resources_dir.as_path() == resources_dir.resolve()
    assert layout.path_dir.as_path() == path_dir.resolve()

    npm_context = InstallContext.from_exe_with_codex_home(False, exe_path, True, False, None)
    assert npm_context.method == InstallMethod.Npm()
    assert npm_context.package_layout is not None
    assert npm_context.rg_command() == (path_dir / rg_name).resolve()
    assert npm_context.bundled_resource("helper").as_path() == (resources_dir / "helper").resolve()

    bun_context = InstallContext.from_exe_with_codex_home(False, Path("/tmp/codex"), False, True, None)
    assert bun_context.method == InstallMethod.Bun()

    codex_home = tmp_path / "codex-home"
    standalone_release = codex_home / "packages" / "standalone" / "releases" / "1.2.3-test"
    standalone_resources = standalone_release / "codex-resources"
    standalone_resources.mkdir(parents=True)
    standalone_exe = standalone_release / exe_name
    standalone_exe.write_text("", encoding="utf-8")
    (standalone_resources / "helper").write_text("", encoding="utf-8")
    (standalone_resources / rg_name).write_text("", encoding="utf-8")

    standalone = InstallContext.from_exe_with_codex_home(False, standalone_exe, False, False, codex_home)
    assert standalone.method.kind is InstallMethodKind.STANDALONE
    assert standalone.method.release_dir.as_path() == standalone_release.resolve()
    assert standalone.method.resources_dir.as_path() == standalone_resources.resolve()
    assert standalone.method.platform in {StandalonePlatform.UNIX, StandalonePlatform.WINDOWS}
    assert standalone.rg_command() == (standalone_resources / rg_name).resolve()
    assert standalone.bundled_resource("helper").as_path() == (standalone_resources / "helper").resolve()

    other = InstallContext.from_exe_with_codex_home(False, tmp_path / "missing-codex", False, False, None)
    assert other.method.kind is InstallMethodKind.OTHER


def test_utils_cache_lru_and_sha1_digest() -> None:
    """Rust: ``utils/cache/src/lib.rs``."""

    import hashlib

    from pycodex.utils.cache import BlockingLruCache, sha1_digest

    assert BlockingLruCache.try_with_capacity(0) is None
    cache = BlockingLruCache[str, int].new(2)
    assert cache.get("first") is None
    assert cache.insert("first", 1) is None
    assert cache.get("first") == 1
    assert cache.insert("second", 2) is None
    assert cache.get("first") == 1
    assert cache.insert("third", 3) is None
    assert cache.get("second") is None
    assert cache.get("first") == 1
    assert cache.get_or_insert_with("first", lambda: 99) == 1
    assert cache.get_or_try_insert_with("fourth", lambda: 4) == 4
    assert cache.remove("first") == 1
    cache.clear()
    assert cache.get("third") is None
    assert sha1_digest(b"hello") == hashlib.sha1(b"hello").digest()


def test_models_manager_top_level_catalog_and_config() -> None:
    """Rust: ``models-manager/src/lib.rs`` and ``config.rs``."""

    from pycodex.models_manager import ModelsManagerConfig, bundled_models_response, client_version_to_whole

    config = ModelsManagerConfig()
    assert config.model_context_window is None
    assert config.personality_enabled is False
    assert config.model_catalog is None

    catalog = bundled_models_response()
    assert isinstance(catalog["models"], list)
    assert catalog["models"]
    assert client_version_to_whole("1.2.3-alpha.4") == "1.2.3"
    assert client_version_to_whole("1.2") == "1.2.0"


def test_codex_api_provider_headers_and_text_controls() -> None:
    """Rust: ``codex-api/src/provider.rs``, ``requests/headers.rs``, ``common.rs``."""

    from pycodex.api import (
        OpenAiVerbosity,
        Provider,
        build_session_headers,
        create_text_param_for_request,
        is_azure_responses_provider,
        response_create_client_metadata,
    )

    assert build_session_headers("session-1", "thread-1") == {
        "session-id": "session-1",
        "thread-id": "thread-1",
    }
    provider = Provider("azure", "https://foo.openai.azure.com/openai/", {"api-version": "2025-01-01"})
    assert provider.url_for_path("/responses") == "https://foo.openai.azure.com/openai/responses?api-version=2025-01-01"
    assert provider.websocket_url_for_path("/responses").startswith("wss://")
    assert provider.is_azure_responses_endpoint() is True
    assert is_azure_responses_provider("openai", "https://foo.windows.net/openai/deployments/x") is True

    text = create_text_param_for_request("high", {"type": "object"}, True)
    assert text is not None
    assert text.verbosity is OpenAiVerbosity.HIGH
    assert text.format is not None
    assert text.format.name == "codex_output_schema"
    trace = type("Trace", (), {"traceparent": "00-abc", "tracestate": "state"})()
    assert response_create_client_metadata({}, trace) == {
        "ws_request_header_traceparent": "00-abc",
        "ws_request_header_tracestate": "state",
    }


def test_code_mode_exec_source_and_identifier_helpers() -> None:
    """Rust: ``code-mode/src/description.rs`` and ``response.rs``."""

    from pycodex.code_mode import (
        DEFAULT_IMAGE_DETAIL,
        CODE_MODE_PRAGMA_PREFIX,
        ImageDetail,
        is_code_mode_nested_tool,
        normalize_code_mode_identifier,
        parse_exec_source,
    )

    parsed = parse_exec_source(f'{CODE_MODE_PRAGMA_PREFIX} {{"yield_time_ms": 7, "max_output_tokens": 8}}\ntext("ok")')
    assert parsed.code == 'text("ok")'
    assert parsed.yield_time_ms == 7
    assert parsed.max_output_tokens == 8
    assert normalize_code_mode_identifier("mcp/tool-name") == "mcp_tool_name"
    assert is_code_mode_nested_tool("wait") is False
    assert is_code_mode_nested_tool("mcp__x__y") is True
    assert DEFAULT_IMAGE_DETAIL is ImageDetail.HIGH
    with pytest.raises(ValueError, match="exec pragma only supports"):
        parse_exec_source(f'{CODE_MODE_PRAGMA_PREFIX} {{"bad": 1}}\n1')


def test_exec_server_protocol_and_environment_shapes() -> None:
    """Rust: ``exec-server/src/protocol.rs``, ``environment.rs``, ``fs_helper.rs``."""

    from pycodex.exec_server import (
        CODEX_FS_HELPER_ARG1,
        DEFAULT_LISTEN_URL,
        EXEC_METHOD,
        ByteChunk,
        Environment,
        EnvironmentManager,
        ExecOutputStream,
        ProcessOutputChunk,
        ReadResponse,
    )

    assert CODEX_FS_HELPER_ARG1 == "--codex-run-as-fs-helper"
    assert DEFAULT_LISTEN_URL == "ws://127.0.0.1:0"
    assert EXEC_METHOD == "process/start"
    chunk = ByteChunk(b"hello")
    assert ByteChunk.from_base64(chunk.to_base64()).into_inner() == b"hello"
    response = ReadResponse([ProcessOutputChunk(1, ExecOutputStream.STDOUT, chunk)], 2, False, None, False)
    assert response.chunks[0].stream is ExecOutputStream.STDOUT
    remote = Environment.create_for_tests("ws://127.0.0.1:9999")
    assert remote.is_remote() is True
    manager = EnvironmentManager.default_for_tests()
    assert manager.default_environment_id() == "local"
    assert manager.default_environment() is not None


def test_core_plugins_feedback_image_and_escalation_interfaces(tmp_path: Path) -> None:
    """Rust: ``core-plugins``, ``feedback``, ``utils/image``, ``shell-escalation`` public exports."""

    from pycodex.core_plugins import OPENAI_CURATED_MARKETPLACE_NAME, TOOL_SUGGEST_DISCOVERABLE_PLUGIN_ALLOWLIST
    from pycodex.feedback import CodexFeedback, FeedbackRequestTags, emit_feedback_request_tags
    from pycodex.shell_escalation import ESCALATE_SOCKET_ENV_VAR, EscalationDecision
    from pycodex.utils.image import EncodedImage, PromptImageMode, load_for_prompt_bytes

    assert OPENAI_CURATED_MARKETPLACE_NAME == "openai-curated"
    assert "github@openai-curated" in TOOL_SUGGEST_DISCOVERABLE_PLUGIN_ALLOWLIST
    feedback = CodexFeedback.new()
    feedback.write("one\ntwo")
    assert feedback.snapshot("thread-1").logs == "one\ntwo"
    emit_feedback_request_tags(FeedbackRequestTags(client="codex-python"))

    png = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89"
    )
    encoded = load_for_prompt_bytes(tmp_path / "pixel.png", png, PromptImageMode.ORIGINAL)
    assert isinstance(encoded, EncodedImage)
    assert encoded.mime == "image/png"
    assert encoded.width == 1
    assert encoded.height == 1
    assert encoded.into_data_url().startswith("data:image/png;base64,")

    assert ESCALATE_SOCKET_ENV_VAR == "CODEX_ESCALATE_SOCKET"
    assert EscalationDecision.deny("no").kind == "deny"
