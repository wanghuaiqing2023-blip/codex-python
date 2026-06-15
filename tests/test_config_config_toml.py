import unittest
from pathlib import Path
from unittest import mock

import pycodex.config.config_toml as config_toml_module
from pycodex.config import (
    ConfigLockfileToml,
    ConfigToml,
    DEFAULT_PROJECT_DOC_MAX_BYTES,
    FORCED_CHATGPT_WORKSPACE_ID_ERROR,
    ProjectConfig,
    RealtimeConfig,
    RealtimeTransport,
    RealtimeWsMode,
    ThreadStoreToml,
    TuiPetAnchor,
    validate_oss_provider,
)
from pycodex.model_provider_info import (
    AMAZON_BEDROCK_PROVIDER_ID,
    LEGACY_OLLAMA_CHAT_PROVIDER_ID,
    OLLAMA_CHAT_PROVIDER_REMOVED_ERROR,
)
from pycodex.protocol import NetworkSandboxPolicy, PermissionProfile
from pycodex.protocol import (
    AskForApproval,
    AutoCompactTokenLimitScope,
    ForcedLoginMethod,
    RealtimeConversationVersion,
    RealtimeVoice,
    ReasoningEffort,
    ReasoningSummary,
    SandboxMode,
    Verbosity,
)
from pycodex.protocol.config_types import TrustLevel, WebSearchMode


WORKSPACE_ID_A = "123e4567-e89b-42d3-a456-426614174000"
WORKSPACE_ID_B = "123e4567-e89b-42d3-a456-426614174001"


class ConfigTomlTests(unittest.TestCase):
    def test_forced_chatgpt_workspace_id_accepts_single_string(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/config_toml.rs
        # Rust test: forced_chatgpt_workspace_id_accepts_single_string
        config = ConfigToml.from_toml(f'forced_chatgpt_workspace_id = "{WORKSPACE_ID_A}"')

        self.assertEqual(config.forced_chatgpt_workspace_id.into_vec(), [WORKSPACE_ID_A])

    def test_forced_chatgpt_workspace_id_accepts_string_list(self) -> None:
        # Rust test: forced_chatgpt_workspace_id_accepts_string_list
        config = ConfigToml.from_toml(
            f'forced_chatgpt_workspace_id = ["{WORKSPACE_ID_A}", "{WORKSPACE_ID_B}"]'
        )

        self.assertEqual(config.forced_chatgpt_workspace_id.into_vec(), [WORKSPACE_ID_A, WORKSPACE_ID_B])

    def test_forced_chatgpt_workspace_id_rejects_comma_separated_string(self) -> None:
        # Rust test: forced_chatgpt_workspace_id_rejects_comma_separated_string
        with self.assertRaisesRegex(ValueError, "comma-separated strings are not supported") as caught:
            ConfigToml.from_toml(f'forced_chatgpt_workspace_id = "{WORKSPACE_ID_A},{WORKSPACE_ID_B}"')

        self.assertIn("TOML list of strings", str(caught.exception))
        self.assertEqual(str(caught.exception), FORCED_CHATGPT_WORKSPACE_ID_ERROR)

    def test_config_toml_slice_defaults_match_rust_default_helpers(self) -> None:
        # Rust source: default_allow_login_shell, default_project_doc_max_bytes,
        # default_project_doc_fallback_filenames, default_hide_agent_reasoning.
        config = ConfigToml.from_toml("")

        self.assertIs(config.allow_login_shell, True)
        self.assertEqual(config.project_doc_max_bytes, DEFAULT_PROJECT_DOC_MAX_BYTES)
        self.assertEqual(config.project_doc_fallback_filenames, ())
        self.assertIs(config.hide_agent_reasoning, False)

    def test_project_config_trust_helpers(self) -> None:
        # Rust source: ProjectConfig::is_trusted / is_untrusted.
        trusted = ProjectConfig.from_mapping({"trust_level": "trusted"})
        untrusted = ProjectConfig.from_mapping({"trust_level": "untrusted"})
        unset = ProjectConfig.from_mapping({})

        self.assertTrue(trusted.is_trusted())
        self.assertFalse(trusted.is_untrusted())
        self.assertFalse(untrusted.is_trusted())
        self.assertTrue(untrusted.is_untrusted())
        self.assertFalse(unset.is_trusted())
        self.assertFalse(unset.is_untrusted())

    def test_config_toml_parses_debug_thread_store_realtime_agents_and_ghost_shapes(self) -> None:
        # Rust source: ConfigToml child data structures below the main schema.
        config = ConfigToml.from_toml(
            """
experimental_thread_store = { type = "in_memory", id = "test-store" }

[debug.config_lockfile]
export_dir = "/tmp/export"
load_path = "/tmp/lock.toml"
allow_codex_version_mismatch = true
save_fields_resolved_from_model_catalog = false

[auto_review]
policy = "check carefully"

[projects."/repo"]
trust_level = "trusted"

[realtime]
version = "v2"
type = "transcription"
transport = "websocket"
voice = "alloy"

[realtime_audio]
microphone = "mic-1"
speaker = "speaker-1"

[tools]
web_search = true

[agents]
max_threads = 3
max_depth = 2
job_max_runtime_seconds = 60
interrupt_message = false

[agents.researcher]
description = "Research-focused role."
config_file = "./agents/researcher.toml"
nickname_candidates = ["Ada", "Grace"]

[ghost_snapshot]
ignore_untracked_files_over_bytes = 10
large_untracked_dir_warning_threshold = 20
disable_warnings = true
"""
        )

        self.assertEqual(config.debug.config_lockfile.export_dir, Path("/tmp/export"))
        self.assertEqual(config.debug.config_lockfile.load_path, Path("/tmp/lock.toml"))
        self.assertIs(config.debug.config_lockfile.allow_codex_version_mismatch, True)
        self.assertIs(config.debug.config_lockfile.save_fields_resolved_from_model_catalog, False)
        self.assertEqual(config.auto_review.policy, "check carefully")
        self.assertEqual(config.experimental_thread_store, ThreadStoreToml.in_memory("test-store"))
        self.assertEqual(config.projects["/repo"].trust_level, TrustLevel.TRUSTED)
        self.assertEqual(config.realtime.version, RealtimeConversationVersion.V2)
        self.assertEqual(config.realtime.session_type, RealtimeWsMode.TRANSCRIPTION)
        self.assertEqual(config.realtime.transport, RealtimeTransport.WEBSOCKET)
        self.assertEqual(config.realtime.voice, RealtimeVoice.ALLOY)
        self.assertEqual(config.realtime_audio.microphone, "mic-1")
        self.assertEqual(config.realtime_audio.speaker, "speaker-1")
        self.assertIsNone(config.tools.web_search)
        self.assertEqual(config.agents.max_threads, 3)
        self.assertEqual(config.agents.roles["researcher"].config_file, Path("./agents/researcher.toml"))
        self.assertEqual(config.agents.roles["researcher"].nickname_candidates, ("Ada", "Grace"))
        self.assertEqual(config.ghost_snapshot.ignore_large_untracked_files, 10)
        self.assertEqual(config.ghost_snapshot.ignore_large_untracked_dirs, 20)
        self.assertIs(config.ghost_snapshot.disable_warnings, True)

    def test_realtime_config_defaults_match_rust_defaults(self) -> None:
        realtime = RealtimeConfig()

        self.assertEqual(realtime.version, RealtimeConversationVersion.V2)
        self.assertEqual(realtime.session_type, RealtimeWsMode.CONVERSATIONAL)
        self.assertEqual(realtime.transport, RealtimeTransport.WEBRTC)

    def test_config_toml_parses_main_schema_surface(self) -> None:
        # Rust source: codex-config::config_toml::ConfigToml.
        config = ConfigToml.from_toml(
            """
model = "gpt-5"
review_model = "gpt-5-review"
model_provider = "openai-custom"
model_context_window = 123
model_auto_compact_token_limit = 45
model_auto_compact_token_limit_scope = "body_after_prefix"
approval_policy = "on-request"
approvals_reviewer = "auto_review"
allow_login_shell = false
sandbox_mode = "workspace-write"
default_permissions = ":default"
notify = ["say", "done"]
instructions = "system"
developer_instructions = "developer"
include_permissions_instructions = true
include_apps_instructions = false
include_collaboration_mode_instructions = true
include_environment_context = false
model_instructions_file = "/tmp/model.md"
compact_prompt = "compact"
forced_login_method = "api"
cli_auth_credentials_store = "auto"
mcp_oauth_credentials_store = "file"
mcp_oauth_callback_port = 4567
mcp_oauth_callback_url = "http://127.0.0.1/callback"
tool_output_token_limit = 100
background_terminal_max_timeout = 200
js_repl_node_path = "/tmp/node"
js_repl_node_module_dirs = ["/tmp/node_modules"]
profile = "work"
sqlite_home = "/tmp/sqlite"
log_dir = "/tmp/log"
file_opener = "vscode"
hide_agent_reasoning = true
show_raw_agent_reasoning = true
model_reasoning_effort = "high"
plan_mode_reasoning_effort = "low"
model_reasoning_summary = "detailed"
model_verbosity = "high"
model_supports_reasoning_summaries = true
model_catalog_json = "/tmp/catalog.json"
personality = "pragmatic"
service_tier = "priority"
chatgpt_base_url = "https://chatgpt.example"
apps_mcp_product_sku = "sku"
openai_base_url = "https://api.example"
experimental_realtime_ws_base_url = "wss://rt.example"
experimental_realtime_ws_model = "rt-model"
experimental_realtime_ws_backend_prompt = "backend"
experimental_realtime_ws_startup_context = "startup"
experimental_realtime_start_instructions = "start"
experimental_thread_config_endpoint = "https://threads.example"
experimental_thread_store_endpoint = "https://removed.example"
web_search = "live"
suppress_unstable_features_warning = true
project_root_markers = [".git", "pyproject.toml"]
check_for_update_on_startup = false
disable_paste_burst = true
experimental_compact_prompt_file = "/tmp/compact.md"
experimental_use_unified_exec_tool = true
oss_provider = "lmstudio"

[shell_environment_policy]
inherit = "none"
set = { FOO = "bar" }

[sandbox_workspace_write]
writable_roots = ["/tmp/work"]
network_access = true

[permissions.readonly]
filesystem = { mode = "read-only" }

[mcp_servers.local]
command = "python"
args = ["-m", "server"]

[model_providers.openai-custom]
name = "OpenAI Custom"
base_url = "https://api.example/v1"
wire_api = "responses"

[profiles.work]
model = "gpt-5-mini"

[history]
persistence = "none"

[tui]
pet_anchor = "screen-bottom"

[audio]
microphone = "USB Mic"
speaker = "Desk Speakers"

[tools.web_search]
context_size = "medium"
allowed_domains = ["example.com"]

[tool_suggest]
discoverables = [{ type = "plugin", id = "github" }]

[memories]
generate_memories = false

[skills]
include_instructions = false

[hooks.on_user_turn_start]
command = "echo"

[plugins.github]
enabled = false

[marketplaces.main]
source_type = "git"
source = "https://example/repo"

[features]
experimental = true

[analytics]
enabled = false

[feedback]
enabled = false

[apps._default]
enabled = false

[desktop]
theme = "dark"

[otel]
environment = "prod"

[windows]
sandbox = "elevated"

[notice]
hide_full_access_warning = true
"""
        )

        self.assertEqual(config.model, "gpt-5")
        self.assertEqual(config.model_auto_compact_token_limit_scope, AutoCompactTokenLimitScope.BODY_AFTER_PREFIX)
        self.assertEqual(config.approval_policy, AskForApproval.ON_REQUEST)
        self.assertEqual(config.sandbox_mode, SandboxMode.WORKSPACE_WRITE)
        self.assertEqual(config.forced_login_method, ForcedLoginMethod.API)
        self.assertEqual(config.model_reasoning_effort, ReasoningEffort.HIGH)
        self.assertEqual(config.plan_mode_reasoning_effort, ReasoningEffort.LOW)
        self.assertEqual(config.model_reasoning_summary, ReasoningSummary.DETAILED)
        self.assertEqual(config.model_verbosity, Verbosity.HIGH)
        self.assertEqual(config.web_search, WebSearchMode.LIVE)
        self.assertEqual(config.notify, ("say", "done"))
        self.assertEqual(config.mcp_oauth_callback_port, 4567)
        self.assertIn("local", config.mcp_servers)
        self.assertIn("openai-custom", config.model_providers)
        self.assertEqual(config.model_providers["openai-custom"].name, "OpenAI Custom")
        self.assertEqual(config.profiles["work"].model, "gpt-5-mini")
        self.assertEqual(config.tui.pet_anchor, TuiPetAnchor.SCREEN_BOTTOM)
        self.assertEqual(config.audio.microphone, "USB Mic")
        self.assertEqual(config.realtime_audio.speaker, "Desk Speakers")
        self.assertEqual(config.tools.web_search.allowed_domains, ("example.com",))
        self.assertEqual(config.desktop, {"theme": "dark"})
        self.assertTrue(config.notice.hide_full_access_warning)

    def test_config_toml_rejects_unknown_root_and_reserved_provider(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown fields for ConfigToml"):
            ConfigToml.from_toml("unknown_key = true")
        with self.assertRaisesRegex(ValueError, "reserved built-in provider IDs"):
            ConfigToml.from_toml(
                """
[model_providers.openai]
name = "bad"
"""
            )
        with self.assertRaisesRegex(ValueError, "mcp_oauth_callback_port"):
            ConfigToml.from_toml("mcp_oauth_callback_port = 70000")

    def test_model_provider_validation_matches_rust_config_toml_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "model_providers.corp: provider auth cannot be combined with env_key"):
            ConfigToml.from_toml(
                """
[model_providers.corp]
name = "Corp"
env_key = "CORP_TOKEN"

[model_providers.corp.auth]
command = "print-token"
"""
            )

        with self.assertRaisesRegex(ValueError, "provider aws is only supported"):
            ConfigToml.from_toml(
                """
[model_providers.custom]
name = "Custom Provider"

[model_providers.custom.aws]
profile = "codex-bedrock"
"""
            )

        cfg = ConfigToml.from_toml(
            """
[model_providers.amazon-bedrock.aws]
profile = "codex-bedrock"
region = "us-west-2"
"""
        )
        aws = cfg.model_providers[AMAZON_BEDROCK_PROVIDER_ID].aws
        self.assertEqual(aws.profile, "codex-bedrock")
        self.assertEqual(aws.region, "us-west-2")

    def test_config_lockfile_toml_shape(self) -> None:
        lockfile = ConfigLockfileToml.from_toml(
            """
version = 1
codex_version = "0.1.0"

[config]
model = "gpt-5"
"""
        )

        self.assertEqual(lockfile.version, 1)
        self.assertEqual(lockfile.codex_version, "0.1.0")
        self.assertEqual(lockfile.config.model, "gpt-5")

        with self.assertRaisesRegex(ValueError, "unknown fields for ConfigLockfileToml"):
            ConfigLockfileToml.from_mapping({"version": 1, "codex_version": "x", "config": {}, "extra": True})

    def test_validate_oss_provider_matches_rust_values(self) -> None:
        validate_oss_provider("lmstudio")
        validate_oss_provider("ollama")

        with self.assertRaisesRegex(ValueError, OLLAMA_CHAT_PROVIDER_REMOVED_ERROR.splitlines()[0]):
            validate_oss_provider(LEGACY_OLLAMA_CHAT_PROVIDER_ID)
        with self.assertRaisesRegex(ValueError, "Invalid OSS provider"):
            validate_oss_provider("other")

    def test_get_active_project_prefers_cwd_then_repo_root(self) -> None:
        config = ConfigToml.from_mapping(
            {
                "projects": {
                    str(Path("/repo")): {"trust_level": "trusted"},
                    str(Path("/repo/sub")): {"trust_level": "untrusted"},
                }
            }
        )

        self.assertTrue(config.get_active_project(Path("/repo/sub"), Path("/repo")).is_untrusted())
        self.assertTrue(config.get_active_project(Path("/repo/missing"), Path("/repo")).is_trusted())
        self.assertIsNone(config.get_active_project(Path("/other"), None))

    def test_derive_permission_profile_matches_legacy_sandbox_contract(self) -> None:
        config = ConfigToml.from_mapping(
            {
                "sandbox_workspace_write": {
                    "writable_roots": ["/tmp/work"],
                    "network_access": True,
                    "exclude_slash_tmp": True,
                }
            }
        )

        self.assertEqual(
            config.derive_permission_profile(sandbox_mode_override=SandboxMode.DANGER_FULL_ACCESS),
            PermissionProfile.disabled(),
        )
        with mock.patch.object(config_toml_module, "_is_windows_platform", return_value=False):
            workspace = config.derive_permission_profile(sandbox_mode_override=SandboxMode.WORKSPACE_WRITE)
        self.assertEqual(workspace.network_sandbox_policy(), NetworkSandboxPolicy.ENABLED)

        active_project = ProjectConfig(trust_level=TrustLevel.TRUSTED)
        with mock.patch.object(config_toml_module, "_is_windows_platform", return_value=False):
            implicit = ConfigToml().derive_permission_profile(active_project=active_project)
            self.assertEqual(implicit.network_sandbox_policy(), NetworkSandboxPolicy.RESTRICTED)
            self.assertNotEqual(implicit, PermissionProfile.read_only())
        with mock.patch.object(config_toml_module, "_is_windows_platform", return_value=True):
            downgraded = ConfigToml().derive_permission_profile(active_project=active_project)
            self.assertEqual(downgraded, PermissionProfile.read_only())

    def test_derive_permission_profile_falls_back_when_implicit_default_disallowed(self) -> None:
        class ReadOnlyConstraint:
            def can_set(self, candidate: PermissionProfile) -> None:
                if candidate != PermissionProfile.read_only():
                    raise ValueError("disallowed")

        with mock.patch.object(config_toml_module, "_is_windows_platform", return_value=False):
            profile = ConfigToml().derive_permission_profile(
                active_project=ProjectConfig(trust_level=TrustLevel.TRUSTED),
                permission_profile_constraint=ReadOnlyConstraint(),
            )

        self.assertEqual(profile, PermissionProfile.read_only())


if __name__ == "__main__":
    unittest.main()
