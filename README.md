# codex-python

Python-first port of Codex.

## Mission

This project exists to translate the upstream Codex codebase into Python while
preserving behavior as closely as possible. The target is not a Python wrapper
around the existing binaries. The target is a Python implementation whose logic,
interfaces, and user-visible behavior can be checked against the upstream
sources in `codex/`.

## Porting Rules

1. Preserve upstream behavior before redesigning anything.
2. Keep each Python module traceable to the Rust, TypeScript, or existing Python
   source file it was ported from.
3. Prefer the Python standard library for runtime code.
4. Do not add a third-party dependency unless a standard-library implementation
   would be impractical, unsafe, or materially less faithful.
5. Isolate platform-specific behavior behind small modules so Linux, macOS, and
   Windows differences are explicit.
6. Use upstream tests, fixtures, snapshots, and protocol files as parity checks
   whenever possible.
7. Treat generated or SDK-only Python code as reference material, not as a
   substitute for porting Codex core behavior.

## Upstream Map

The checked-in `codex/` directory is the upstream reference tree. Its most
important areas for the Python port are:

| Upstream area | Python port target | Notes |
| --- | --- | --- |
| `codex/codex-rs/cli` | `pycodex.cli` | Command parsing and top-level dispatch. |
| `codex/codex-rs/core` | `pycodex.core` | Session, turn, tool, config, and agent logic. |
| `codex/codex-rs/protocol` | `pycodex.protocol` | Shared message and event types. |
| `codex/codex-rs/shell-command` | `pycodex.shell_command` | Command summaries and safety helpers. |
| `codex/codex-rs/exec` | `pycodex.exec` | Non-interactive execution path. |
| `codex/codex-rs/login` | `pycodex.login` | Auth flows and credential lookup. |
| `codex/codex-rs/sandboxing` | `pycodex.sandboxing` | Permission and sandbox policy model. |
| `codex/codex-rs/tui` | `pycodex.tui` | Terminal UI behavior, ported after core parity. |
| `codex/sdk/python` | reference only | Existing SDK depends on generated models and the Codex binary. |

## Dependency Policy

Runtime code should start from the standard library: `argparse`, `asyncio`,
`dataclasses`, `enum`, `json`, `logging`, `pathlib`, `queue`, `sqlite3`,
`subprocess`, `threading`, `typing`, `unittest`, and related modules.

If a dependency is proposed, document:

- the upstream behavior it is needed to match,
- why the standard library is not enough,
- the smallest acceptable package,
- how tests prove the dependency does not change behavior.

## Current Python Port

The first Python modules are `pycodex.cli`, `pycodex.config`,
`pycodex.protocol`, `pycodex.shell_command`, `pycodex.exec`, and
`pycodex.core`.

`pycodex.cli` ports the top-level command surface from
`codex/codex-rs/cli/src/main.rs`:

- `python -m pycodex --help` prints the recognized top-level command list.
- `pycodex.cli.parse_args()` maps upstream command names and aliases to
  canonical command names.
- top-level `exec` arguments are parsed by `pycodex.exec` before dispatch.
- root `--enable` and `--disable` feature flags validate against the ported
  upstream feature registry and fold into effective `features.<key>=...`
  config overrides in upstream order.
- root `--remote` and `--remote-auth-token-env` are accepted for the
  interactive surface but rejected for non-interactive subcommands with the
  upstream error text.
- `codex features list|enable|disable` now validates feature names, reads and
  writes `config.toml` through the ported config edit helpers, lists effective
  feature states with root overrides applied, and emits the upstream
  under-development warning text when enabling incomplete features.
- other command bodies intentionally return "recognized but not implemented
  yet" until the corresponding Rust crates are ported.

`pycodex.config` ports shared config override parsing from
`codex/codex-rs/utils/cli/src/config_override.rs`:

- raw `-c key=value` arguments are preserved first, matching upstream's
  two-stage parsing model.
- values are parsed as TOML through the standard-library `tomllib` module.
- invalid TOML values fall back to strings, matching upstream convenience
  behavior for values such as `model=gpt-5`.
- dotted override paths can be applied onto nested Python mappings.
- personality migration helpers now mirror `core/src/personality_migration.rs`
  for the standard-library surface: marker-file skipping, explicit top-level
  or selected-profile personality detection, active/archived session probing,
  and pragmatic personality persistence into `config.toml`.

`pycodex.protocol` begins the config type port from
`codex/codex-rs/protocol/src/config_types.rs` and
`codex/codex-rs/protocol/src/protocol.rs`:

- sandbox, approval, Windows sandbox, verbosity, and alternate-screen values
  are represented as explicit string enums with upstream serialized names.
- reasoning, approval reviewer, shell environment, web search, service tier,
  auth-helper, trust, and collaboration-mode settings are represented as
  standard-library enums and dataclasses.
- agent paths, auth/account plan types, provider account shapes, and exec
  output stream decoding helpers now mirror their upstream protocol modules.
- thread/session IDs, tool names, image detail values, and user-input/text
  element helpers are available for the next `items.rs` and session ports.
- shell environment policy application can now build command environments with
  upstream inherit/filter/override/thread-id behavior.
- the core `exec_env.rs` wrapper is now represented too, preserving
  `CODEX_THREAD_ID` injection and environment construction through the shared
  protocol shell-environment implementation.
- sandbox permission modes, filesystem/network permission overlays, managed
  filesystem policies, and built-in permission profiles are modeled for the
  upcoming exec-policy and sandboxing ports.
- `permissions.rs` runtime helpers now cover protected workspace metadata,
  full-disk access checks, cwd-aware readable/writable/unreadable roots,
  `WritableRoot` protections, and read-deny exact/glob matching.
- `permissions.rs` project-root helpers now materialize symbolic
  `:workspace_roots` entries for a cwd or explicit workspace-root list,
  preserve deny-read rules across permission replacement, and add readable or
  writable roots using upstream skip/append semantics.
- `permissions.rs` semantic signatures now compare effective filesystem
  policy behavior independently of entry ordering, including normalized
  readable, writable, unreadable, and deny-glob roots.
- legacy `SandboxPolicy` bridge behavior now covers read-only, workspace-write,
  external-sandbox, and danger-full-access conversions, deny-read preservation,
  direct-runtime-enforcement detection, and rejection of unbridgeable
  non-workspace writes.
- `PermissionProfile` now mirrors the upstream legacy sandbox conversion path,
  including enforcement inference, profile-to-legacy projection, and
  materializing symbolic project roots for managed profiles.
- permission-related models now expose upstream-style mapping helpers for
  canonical tagged JSON plus legacy rollout shapes, including special-path
  aliases and `glob_scan_max_depth` validation.
- request-permissions and approval event models now cover review decisions,
  exec-policy/network amendments, guardian actions, MCP elicitations, and patch
  approval request shapes.
- MCP and dynamic-tool protocol values now cover request IDs, tool/resource
  metadata, call-tool results, deferred dynamic tool specs, and MCP approval
  metadata keys.
- `protocol.rs` transport primitives now include submission/event wrappers,
  tagged op/event message helpers, session source/product routing helpers,
  request-user-input payloads, granular approval flags, thread goals, and token
  usage summaries.
- `token_count` events now use upstream-shaped rate-limit snapshots, including
  primary/secondary windows, credits metadata, plan type, and reached-type
  enums instead of loose JSON payloads.
- thread-settings-applied events now carry the upstream snapshot shape for
  model/provider, approval reviewer, active permission profile, cwd,
  reasoning/personality settings, and collaboration mode.
- lightweight protocol events now cover turn aborts, review-mode entry/exit,
  hook lifecycle summaries, shutdown-complete, and realtime conversation
  start/stream/close/SDP/voice-list payloads.
- realtime conversation request `Op` variants now match upstream's unnested
  wire format for start/audio/text/close/list-voices, including the distinction
  between omitted and explicit-null start prompts.
- `user_input` and `thread_settings` submission `Op` payloads now model
  flattened thread-settings overrides, optional response metadata, turn
  environments, final-output JSON schema omission rules, and structured
  `UserInput` round-tripping.
- response-side submission `Op` payloads now round-trip exec/patch approvals,
  MCP elicitation resolution, request-user-input answers, request-permissions
  grants, and dynamic tool responses using upstream wire shapes.
- request-side `EventMsg` payloads now parse and serialize structured
  approval, request-permissions, request-user-input, dynamic-tool,
  elicitation, apply-patch approval, model-reroute, model-verification, and
  context-compaction events.
- collaboration `EventMsg` payloads now model upstream agent spawn,
  interaction, waiting, close, and resume lifecycle events, including agent
  status variants and thread-id keyed status maps.
- guardian assessment and thread-goal update events now round-trip through
  structured `EventMsg` payloads, including guardian action variants and
  camelCase thread-goal counters.
- control-plane submission `Op` payloads now cover inter-agent communication,
  MCP refresh requests, user-config reloads, thread memory mode changes,
  thread rollback, Guardian-denied retry approval, shutdown/compact commands,
  and user-initiated shell commands.
- resume/fork history protocol models now cover conversation path responses,
  resumed history payloads, structured rollout envelopes, session metadata,
  git info, compacted items, rollout item scanning, event-message extraction,
  fork source, cwd, and session metadata helpers.
- turn context and session-configured protocol payloads now deserialize both
  canonical `permission_profile` data and legacy `sandbox_policy` rollouts,
  while preserving upstream network-proxy and filesystem sandbox wire shapes.
- exec command events, base64 output deltas, patch-apply lifecycle events, MCP
  tool/startup events, review request/output payloads, deprecation/stream
  notices, web search, and image-generation event payloads are represented for
  the next core/agent event ports.
- `items.rs` turn items now cover user/agent/reasoning messages, hook prompts,
  web search, image view/generation, file changes, MCP tool calls, context
  compaction, and their legacy `EventMsg` conversion path.
- `models.rs` shared message models now include content items,
  response-input/response items, function-call output payloads, web-search
  actions, reasoning summaries/content filtering, message phases, base
  instructions, approved command-prefix formatting, and image tag helpers.
- function-call output payloads now preserve upstream text-vs-content-items
  bodies, lossy content-item text extraction, internal success metadata, and
  tool-search call params for the core tool context port.
- `parse_command.rs` and `plan_tool.rs` protocol models now cover parsed
  command summaries, exec event `parsed_cmd` payloads, and update-plan tool
  arguments.
- `memory_citation.rs`, `network_policy.rs`, and `num_format.rs` are now
  represented with memory citation payloads, network policy decision metadata,
  and token/count formatting helpers.
- `error.rs` protocol helpers now cover upstream `CodexErrorInfo` variants,
  turn-status impact rules, retryable error classification, user-facing usage
  limit and unexpected-status messages, response-stream error mapping, and
  sandbox UI error extraction.
- `openai_models.rs` model metadata now covers model/preset conversion,
  reasoning effort presets and migrations, input modalities, shell/apply-patch
  tool types, truncation policy, service-tier filtering, personality instruction
  templates, and model response wrappers.
- `ProfileV2Name` validates the same plain ASCII profile names accepted by the
  Rust implementation.
- CLI options such as `--sandbox`, `--ask-for-approval`, and `--profile` now
  parse into these protocol/config types.

`pycodex.shell_command` starts the standard-library port from
`codex/codex-rs/shell-command/src/parse_command.rs`:

- shell command extraction handles bash, zsh, sh, PowerShell, and pwsh wrapper
  invocations.
- common read/list/search summaries are recognized for `rg`, `git grep`,
  `git ls-files`, `fd`, `find`, `grep`, `cat`, `sed`, `head`, `tail`, `awk`,
  `nl`, and Python file-walk snippets.
- plain `bash -lc` command sequences are split with `shlex`, with unsupported
  shell syntax falling back to the same `unknown` summary shape rather than
  guessing.
- exec-policy-oriented shell parsing now rejects empty connector segments and
  extracts single-command heredoc prefixes for conservative prefix-rule checks.
- command-safety helpers now mirror the upstream safe-command allowlist,
  dangerous `rm`/Windows URL-launch/delete heuristics, read-only git option
  checks, and conservative bash-wrapper handling.

`pycodex.exec` ports the non-interactive command surface from
`codex/codex-rs/exec/src/cli.rs` and the pre-client run preparation logic from
`codex/codex-rs/exec/src/lib.rs`:

- main `codex exec [OPTIONS] [PROMPT]` parsing is represented by `ExecCli`.
- `resume` and `review` subcommand argument shapes are represented explicitly.
- global flags that upstream allows after `resume` are accepted after the
  subcommand.
- the removed `--full-auto` flag reports the upstream migration warning.
- prompt preparation now mirrors the upstream stdin behavior: missing prompts
  read piped stdin, `-` forces stdin, positional prompts append non-empty piped
  stdin in `<stdin>...</stdin>` context, UTF-8/UTF-16 BOM decoding is handled,
  and UTF-32/invalid UTF-8 inputs produce actionable errors.
- exec run preparation now builds the upstream-shaped initial operation for
  user turns and reviews, merging image inputs, loading JSON output schemas,
  building review targets, and computing review prompt summaries before the
  future in-process app-server loop is connected.
- exec config bootstrap planning now mirrors the `run_main` harness override
  slice before full `ConfigBuilder` startup: headless approval defaults to
  `never`, `--full-auto`/danger bypass/sandbox precedence is preserved, OSS
  provider selection follows `--local-provider` before `oss_provider` in
  config, built-in OSS providers choose the same default models, `-c` overrides
  are parsed through the shared config override parser, and `-C`/`--add-dir`
  are projected into config-cwd/additional-writable-root inputs.
- exec session request builders now mirror the app-server payloads emitted by
  upstream `run_exec_session`: `thread/start`, `thread/resume`, `turn/start`,
  and `review/start` parameters preserve model/provider, cwd, workspace roots,
  approval reviewer, active permission-profile selection, inferred legacy
  sandbox mode, reasoning effort, output schema, review target, and request ID
  wire shapes. Initial-operation helpers now also choose the correct
  `turn/start` or `review/start` request, extract the resulting task turn ID,
  and synthesize the review `turn/started` notification that upstream feeds
  into the event processor.
- exec loop control helpers now cover the dependency-free parts of the
  in-process session loop: integer request-id sequencing, `turn/interrupt`,
  `thread/unsubscribe`, and `thread/read` request payloads, lagged-event
  warnings, primary-thread/turn notification filtering, terminal error
  detection, processor shutdown-to-unsubscribe decisions, final exit-code
  selection, interrupt-channel state transitions for Ctrl-C initiated
  `turn/interrupt` requests, turn-completion item backfill eligibility, and
  pure backfill of empty `turn.items` from `thread/read` responses. A pure
  loop-step reducer now
  ties those decisions together for server requests, notifications, lagged
  warnings, backfill waits, error-state accumulation, and shutdown requests so
  the eventual transport loop can mirror upstream `run_exec_session` without
  embedding that policy in I/O code.
- exec server-request helpers now mirror the pure handling in upstream exec
  mode: app-server request errors keep the `method: error` prefix rule, MCP
  elicitations auto-resolve with a cancel payload preserving `content: null`
  and `_meta: null`, and unsupported command/file/permissions approvals,
  request-user-input, dynamic tool calls, ChatGPT token refresh, attestation,
  and legacy patch/exec approvals reject with upstream JSON-RPC error payloads.
- thread start/resume responses now map into upstream-shaped
  `SessionConfiguredEvent` values for exec initialization, including session
  and thread UUID validation, thread source/name/path metadata, model/provider
  settings, approval reviewer, active permission profile, cwd, reasoning
  effort, rollout path, and the effective permission profile from the exec
  config.
- exec resume lookup helpers now mirror the dependency-free selection rules
  from upstream: `--last` applies the current model-provider filter, thread
  list requests include all app-server source kinds, resume-by-name searches
  can require exact thread names, direct UUID resume is detected before search,
  local state-db and rollout-metadata candidates can short-circuit named
  resume before app-server search, rollout files are scanned from the end for
  the latest `turn_context` cwd, and cwd matching follows Codex path
  normalization with a direct-equality fallback. The pure bootstrap plan now
  mirrors the `run_exec_session`
  start/resume branch: unresolved resume falls back to `thread/start`, resolved
  resume builds `thread/resume`, list pagination tracks `nextCursor`, and
  start/resume responses are converted into authoritative
  `SessionConfiguredEvent` bootstrap state. Startup sequencing helpers now
  consume the shared request-id stream for bootstrap and initial operation
  requests, derive the first `ExecLoopState` from the initial operation
  response, emit an upstream-ordered config-summary processor action before
  the initial operation, preserve the non-JSON Linux sandbox warning slot that
  upstream emits immediately after the config summary, and preserve review-mode
  synthetic `turn/started` notifications for the event processor after
  `review/start`. The loop-step action planner now projects each pure
  reducer result into ordered I/O work for server-request resolve/reject,
  lagged-stream warnings, `thread/read` backfills, notification processing,
  `thread/unsubscribe` shutdown, and loop termination; action-failure helpers
  fold transport failures back into upstream warning text and `error_seen`
  semantics, including server-request failures becoming fatal while
  interrupt/backfill/unsubscribe failures remain warnings. Loop completion now
  also preserves the upstream tail sequence of app-server shutdown, final-output
  printing, and `error_seen`-based exit-code selection. Unified loop-cycle
  helpers now model the `tokio::select!` branches for server events,
  interrupts, and closed event streams so the eventual transport layer can
  poll once and execute a normalized action list.
  Transport wire projection now covers the remote app-server JSON-RPC envelope
  shape for client requests and server-request resolve/reject decisions,
  including upstream `id`/`method` request fields, response/error envelopes,
  optional trace propagation, and omitted `error.data` when no data is present.
  The first remote-client facade state machine is also represented: outgoing
  requests register pending response IDs, response/error messages clear them,
  client notification commands emit JSON-RPC notifications, notifications and
  supported server requests become `AppServerEvent` values, queued startup
  events drain in order, and unsupported remote server requests produce the
  upstream `-32601` JSON-RPC error envelope. The remote initialize handshake is
  modeled as a pure state machine too: it emits the `initialize` request with
  optional trace metadata, buffers server notifications/requests before the
  matching response, sends `initialized` on success, ignores unrelated
  responses, and reports rejected initializes with upstream wording.
  Compact JSON-RPC text encoding/decoding now bridges those envelope and state
  helpers to future transport I/O, including UTF-8 byte input, strict message
  kind validation, and direct text handlers for initialize/client event loops.
  Remote transport connection, upgrade, write, disconnect, invalid-message, and
  initialize-timeout/error wording is pinned to the upstream app-server-client
  messages so future socket I/O can surface the same user-facing failures.
  Remote endpoint/connect-argument helpers now mirror the upstream WebSocket vs
  Unix-socket endpoint shapes, initialize client-info/capability payloads,
  WebSocket frame/message size constants, timeout constants, UDS handshake URL,
  channel-capacity clamping, and the auth-token rule that only permits `wss://`
  or loopback `ws://` URLs. Remote worker/request-channel helpers now preserve
  upstream duplicate-request-id handling, channel-closed messages, close/write
  failure wording, shutdown timeout planning, already-closed WebSocket close
  tolerance, and fan-out of worker-exit errors to all pending requests.
  A dependency-free WebSocket foundation now covers the remote transport pieces
  that Python lacks in the standard library: client handshake request building,
  `Sec-WebSocket-Accept` validation, bearer auth header projection, configured
  max-message-size enforcement, and masked client/unmasked server text-frame
  encoding/decoding for JSON-RPC payloads. Socket-backed frame readers now
  handle split `recv` chunks for server text and close frames, enforce the same
  mask and message-size rules, and expose `StdlibWebSocket.recv_frame()` /
  `recv_text()` for the upcoming transport loop. Frame classification now
  mirrors the remote loop branches by surfacing text payloads, parsing close
  codes/reasons with the upstream default `"connection closed"` fallback, and
  marking binary/ping/pong/continuation frames as ignored. Session helpers now
  consume those WebSocket frame events directly, mapping text frames into the
  existing JSON-RPC initialize/client reducers, close frames into upstream
  disconnected/initialize-close errors, invalid JSON into disconnected or
  initialize-invalid-response failures, and ignored frames into no-op steps.
  JSON-RPC/WebSocket bridge helpers now serialize outgoing envelopes into the
  same compact text payloads that upstream writes to WebSocket frames, write
  those payloads through the standard-library WebSocket wrapper, and turn
  received frames back into reusable frame events for the initialize/client
  reducers. A blocking initialize handshake driver now mirrors upstream
  `initialize_remote_connection`: it writes the initial `initialize` request,
  buffers startup notifications/requests, rejects unsupported startup requests
  with `-32601`, sends `initialized` after the matching response, and reports
  timeout/EOF/close/write failures with upstream wording. A blocking
  `RemoteWebSocketClient` facade now owns the post-initialize client state over
  a WebSocket-like object: it sends client requests/notifications and
  server-request resolve/reject responses as compact JSON-RPC text messages,
  drains buffered startup events before reading more frames, maps socket
  EOF/timeout/transport failures into upstream disconnected events, rejects
  unsupported remote server requests immediately, preserves previous state on
  write failures, and projects close/shutdown into the same pending-request
  failure plan used by the pure worker helpers. Remote connect orchestration
  now accepts upstream-shaped `RemoteAppServerConnectArgs`, enforces the same
  auth-token rule for `wss://` or loopback `ws://` URLs, connects WebSocket
  endpoints through the standard-library socket/TLS wrapper, upgrades Unix
  sockets with the upstream `ws://localhost/rpc` handshake URL, runs the
  initialize handshake, closes failed initialize attempts, and returns a ready
  `RemoteWebSocketClient` plus the initialize transcript or an upstream-shaped
  connection/initialize error. Remote address helpers now mirror the TUI
  `--remote` rules for `ws://host:port`, `wss://host:port`, `unix://`, and
  `unix://PATH`, including default control-socket resolution and
  `--remote-auth-token-env` trimming/empty-value rejection. The facade can now
  perform blocking request/response calls for bootstrap-style app-server methods:
  while waiting
  for the matching response it continues to read WebSocket frames, queues
  intervening notifications and supported server requests for later event
  consumption, rejects unsupported server requests immediately, clears pending
  requests on disconnect/invalid JSON/timeout, and exposes `request_typed()`
  through the same transport/server/deserialize error layers used by the
  upstream typed client.
  Typed request helpers now keep the upstream transport/server/deserialize
  error layers and display text distinct for future typed app-server callers.
  Remote exec startup helpers now drive the blocking bootstrap path end to end:
  they send `thread/start` or `thread/resume`, decode the configured session,
  issue the initial `turn/start` or `review/start` request on the same request
  ID stream, queue intervening app-server events, and return either the initial
  loop state or the same typed transport/server/deserialize error layers.
  The first blocking remote exec loop driver is now wired over that facade: it
  reads app-server events, executes server-request resolve/reject responses,
  performs `thread/read` backfill before processing empty terminal
  `turn/completed` notifications, sends `thread/unsubscribe` when the processor
  initiates shutdown, closes the client, prints final output, and preserves the
  upstream non-zero exit-code rule for failed or interrupted turns.
  A combined remote exec session driver now composes bootstrap, startup
  processor actions, optional review synthetic notifications, the blocking
  event loop, completion cleanup, and startup-failure client closure into one
  upstream-shaped call boundary.
  Connect-and-run orchestration now adds the remote endpoint initialization
  layer to that boundary, preserving the initialize/initialized handshake before
  session startup and short-circuiting safely when remote connection or
  authorization validation fails.
- `codex exec --json` event shapes and the first event-processor state machine
  are now ported: thread/turn/item/error JSONL events serialize with upstream
  tags, MCP tool `_meta` payloads are preserved, started/completed item IDs are
  reconciled, final agent messages are written only after successful turns, and
  human-output final-message routing follows upstream TTY rules. The startup
  config summary path now mirrors upstream human/json behavior too: human mode
  prints the version banner, workdir/model/provider/approval/sandbox/reasoning
  entries and prompt, while json mode emits the initial `thread.started` event;
  sandbox summaries preserve workspace roots, `/tmp`/`$TMPDIR`, network suffix
  rules, and `danger-full-access`/read-only/external/workspace-write labels.
  App-server notification dispatch is now wired through the processors for
  config warnings, errors, deprecation notices, item lifecycle updates, model
  reroutes, token-usage snapshots, turn diffs/plans, and terminal turn
  completion; JSONL mode now tracks plan todo-list started/updated/completed
  events, emits app-server `collabAgentToolCall` items as upstream
  `collab_tool_call` payloads (including `resumeAgent` -> `wait` mapping and
  agent-state normalization), and reuses upstream item IDs across notification
  pairs. Human mode now renders the same key item notifications as upstream's
  plain stderr path for command execution, MCP calls, patches, web searches,
  collab starts, reasoning summaries, and context compaction.

`pycodex.core` starts the local state and rollout port from
`codex/codex-rs/utils/home-dir`, `codex/codex-rs/state`,
`codex/codex-rs/rollout`, and `codex/codex-rs/core`:

- `find_codex_home()` follows the upstream `CODEX_HOME` validation rules.
- runtime DB filenames and path helpers match the Rust constants.
- installation ID persistence now mirrors `core/src/installation_id.rs`,
  creating or reusing a stable UUID in `CODEX_HOME/installation_id`, rewriting
  invalid contents, and repairing Unix file permissions with only stdlib APIs.
- AGENTS.md discovery now mirrors `core/src/agents_md.rs`, including global
  override preference, project-root marker traversal, fallback filenames,
  byte-budget truncation, lossy UTF-8 warnings, source ordering, and project
  doc concatenation with user instructions.
- agent role helpers now mirror the dependency-free portions of
  `core/src/config/agent_roles.rs` and `core/src/agent/role.rs`, including
  role-file metadata parsing, developer-instruction and nickname validation,
  recursive role discovery, built-in role declarations/config contents,
  user-over-built-in resolution, locked model/reasoning/service-tier notes,
  spawn-agent tool description rendering, and nickname ordinal suffixes.
- feature flag registry helpers now mirror the dependency-free portions of
  `codex-rs/features/src/lib.rs`, including lifecycle stages, canonical and
  legacy feature-key lookup, default-enabled sets, dependency normalization,
  special feature config tables, materialized resolved states, legacy usage
  warnings, and under-development feature warning events.
- managed feature constraints now mirror the pure logic from
  `core/src/config/managed_features.rs`, including `features` requirement
  parsing, `auto_review` compatibility, legacy/unknown requirement warnings,
  requirement display formatting, runtime mutation normalization, explicit
  config conflict validation, and profile-aware requirement checks.
- config edit helpers now cover the dependency-free subset of
  `core/src/config/edit.rs` needed by feature toggles: `SetPath`/`ClearPath`
  edits, `set_feature_enabled` default-false clearing semantics, atomic
  `config.toml` writes, TUI/session-picker/keymap/status-line helpers,
  model/service-tier/personality persistence, notice and migration
  acknowledgements, `tool_suggest.disabled_tools` persistence for dismissed
  plugin/connector install suggestions, project `trust_level` table writes,
  `skills.config` enable/disable rules by path or name, stdio/streamable-http
  `mcp_servers` replacement for the existing MCP config model,
  model-availability nudge counters, Windows sandbox and realtime audio/voice
  edits, legacy Windows sandbox key cleanup, and a small standard-library TOML
  serializer for the supported scalar/table/inline-table-array/array-of-tables
  shapes.
- agent registry/status helpers now mirror the pure state-machine portions of
  `core/src/agent/registry.rs` and `core/src/agent/status.rs`, including
  spawn-slot limits, reservation rollback, root/live-agent indexing, agent-path
  uniqueness, task-message updates, nickname pool reset behavior, thread-spawn
  depth accounting, and event-to-`AgentStatus` transitions.
- agent control pure helpers now mirror dependency-free pieces of
  `core/src/agent/control.rs`, including the embedded default nickname list,
  forked-rollout history retention, multi-agent usage-hint filtering inside
  response and compacted histories, agent-path prefix matching, thread-spawn
  parent/depth extraction, and initial operation input previews.
- auto-compact window state now mirrors
  `core/src/state/auto_compact_window.rs`, tracking window ordinals,
  estimated prefill baselines, server-observed prefill replacement, clamping,
  and snapshot generation for scoped compaction budgets.
- core utility helpers now mirror the standard-library slice of
  `core/src/util.rs`, including feedback tag logging, auth-recovery feedback
  tags, exponential retry backoff with jitter, path resolution, debug
  error-or-panic behavior, and thread-name normalization.
- string utility helpers now mirror upstream UTF-8 byte-boundary prefixing,
  metric tag sanitization, UUID extraction, Markdown `#L..` location suffix
  normalization, middle truncation with upstream 4-bytes-per-token estimates,
  character-boundary truncation, and ASCII-safe JSON encoding.
- rollout JSONL helpers can read the session metadata head record.
- session index helpers append and resolve thread names with newest-entry wins.
- cursor and rollout filename date parsing follow the upstream token formats.
- thread listing can scan rollout files, build `ThreadItem` summaries, filter by
  source/provider/cwd, and paginate by created or updated time.
- git-utils helpers now collect repository commit/branch/remote metadata,
  canonicalize remote URLs, detect dirty worktrees, list recent commits, resolve
  trust roots for worktree pointers, and build diffs against the closest remote
  branch using standard-library subprocess calls to `git`.
- turn metadata helpers now build ASCII-safe request headers, merge
  Responses API client metadata without replacing reserved fields, include
  sandbox/thread/workspace git metadata, and produce MCP request metadata with
  model, reasoning-effort, and in-turn user-input flags.
- config lock helpers now mirror `core/src/config_lock.rs` for the
  standard-library surface: lock metadata/version validation, Codex-version
  mismatch policy, `debug.config_lockfile` control stripping, replay
  comparison, deterministic compact diffs, TOML lockfile loading via
  `tomllib`, and config-layer projection without third-party TOML emitters.
- approval-cache command canonicalization now mirrors
  `core/src/command_canonicalization.rs`, normalizing plain shell wrappers to
  inner argv and complex bash/PowerShell wrappers to stable script keys.
- exec-policy helpers now cover unmatched-command decision rendering,
  prompt-rejection reasons, shell/PowerShell command extraction for policy
  checks, and Windows read-only managed-profile sandbox detection.
- tool sandboxing helpers now cover session approval caching, bash permission
  request payloads, default exec approval requirements, first-attempt sandbox
  override selection, and managed-network suppression for explicit escalation.
- contextual user fragment helpers now mirror environment-context marker
  matching, response-item conversion, environment/network/subagent rendering,
  turn-context-item diffs, goal/user/skill/shell/turn-aborted/subagent
  fragments, developer fragments for saved command prefixes/network rules,
  guardian follow-up reminders, hook additional context, app/plugin/skills
  instruction blocks, collaboration-mode instructions, realtime
  start/end/resume instructions, model-switch/personality/style fragments,
  image-generation save-location guidance, plugin text, legacy warning
  detection, and visible hook-prompt filtering used to build model-visible
  session context.
- user shell command record helpers now mirror `core/src/user_shell_command.rs`,
  formatting aggregated exec output with timeout/truncation handling and
  wrapping user-initiated shell commands as model-visible `ResponseItem`
  fragments.
- thread rollout truncation helpers now mirror
  `core/src/thread_rollout_truncation.rs`, cutting rollout history before the
  nth real user message, retaining the last fork turns, handling assistant
  inter-agent `trigger_turn` envelopes, and applying thread rollback markers.
- session prefix helpers now mirror `core/src/session_prefix.rs`, rendering
  model-visible subagent notification fragments and subagent context lines
  with the same empty-nickname handling as upstream.
- session rollout initialization error mapping now mirrors
  `core/src/session_rollout_init_error.rs`, translating common session storage
  IO failures into `CodexErr.fatal` messages with permission, missing
  directory, existing file, corrupt data, and unexpected-type hints.
- environment selection helpers now mirror `core/src/environment_selection.rs`,
  building default turn environment selections, resolving selected
  environments, rejecting duplicate or unknown environment IDs, and exposing
  primary environment/filesystem accessors.
- realtime startup context helpers now mirror the pure standard-library slice
  of `core/src/realtime_context.rs`, including startup-context wrapping,
  fixed-budget sections, current-thread user/assistant summaries, realtime
  text truncation, and bounded workspace tree rendering with noisy directory
  filtering.
- realtime prompt helpers now mirror `core/src/realtime_prompt.rs`, preserving
  the config-override/request-prompt/default-template priority order, explicit
  empty-prompt handling, and default backend prompt username substitution using
  standard-library account lookup.
- thread-goal helpers now mirror the pure `core/src/goals.rs` behavior for
  goal budget validation, token-delta accounting, plan-mode continuation
  suppression, XML objective escaping, goal-context response input wrapping,
  and continuation/budget-limit/objective-updated hidden prompt rendering.
- permissions instructions now render the upstream sandbox/approval developer
  context, including network status, writable roots, on-request escalation
  guidance, sandboxed permission requests, granular approval categories,
  approved command prefixes, and auto-review guidance.
- network policy decision helpers now mirror the upstream approval-context
  extraction, denied-request user messages, and execution-policy network rule
  amendment conversion for HTTP, HTTPS connect, and SOCKS protocols.
- network approval helpers now mirror the dependency-free state-machine slice
  of `core/src/tools/network_approval.rs`, including host/protocol/port
  approval keys, pending decision fan-out, session approved-host sync,
  active-call outcome recording, and blocked-request denial propagation.
- hook-facing tool names now preserve upstream canonical names and matcher-only
  compatibility aliases, including `Bash`, `apply_patch` with `Write`/`Edit`,
  and `spawn_agent` with `Agent`.
- apply-patch helpers now mirror the upstream pure conversion layer from
  internal add/delete/update patch changes into protocol `FileChange` payloads,
  including move-path preservation for update changes, plus the upstream
  freeform Responses API tool spec, Lark grammar with optional environment ID
  support, custom-payload handler identity, and spec-planning injection gates
  for environment/model support. The dependency-free parser now also covers
  lenient heredoc-wrapped patch bodies, optional environment ID preambles,
  add/delete/update hunk parsing, update chunks, EOF markers, missing-context
  leniency for the first update chunk, and upstream-shaped parse errors.
  Streaming patch parsing now mirrors the upstream line-buffered state machine
  for partial model output, including complete-line previews, move hunks,
  environment ID preamble tolerance, CRLF handling, empty update validation, and
  final `*** End Patch` enforcement. Apply-patch invocation detection now
  covers literal `apply_patch`/`applypatch` calls and the upstream conservative
  shell heredoc forms with optional `cd <dir> &&`, while rejecting ambiguous
  extra commands, pipes, `||`, extra apply-patch arguments, and malformed
  heredoc terminators. Verified apply-patch handling now resolves effective
  working directories, reads delete/update targets from disk with only the
  standard library, detects implicit raw patch bodies, computes update
  replacements with the upstream exact/rstrip/trim/Unicode-normalized seek
  sequence, and produces one-line-context unified diffs plus resulting
  `new_content` for update changes.
- turn diff tracking now mirrors `core/src/turn_diff_tracker.rs`, accumulating
  exact committed apply-patch deltas into a single net git-style unified diff,
  including add/update/delete, rename-with-edit, overwrite, invalidation, and
  Git blob OID calculation using only `hashlib` and `difflib`.
- shell selection helpers now mirror `core/src/shell.rs` and
  `core/src/shell_detect.rs`, covering shell-type detection, default/user
  fallback selection, model-provided shell paths, and exec argv derivation for
  bash, zsh, sh, PowerShell, and cmd without third-party dependencies.
- shell snapshot helpers now mirror the dependency-free surface of
  `core/src/shell_snapshot.rs`, including bash/zsh/sh/PowerShell snapshot
  script generation, marker preamble stripping, snapshot path naming, legacy
  filename session-id parsing, unsupported shell rejection, and stale snapshot
  cleanup against rollout liveness/retention using only the standard library.
- apply-patch safety checks now mirror `core/src/safety.rs`, deciding when a
  patch should be auto-approved, rejected, or sent for user approval based on
  approval policy, permission profile, writable roots, move destinations, and
  platform sandbox availability.
- approval preset helpers now mirror
  `utils/approval-presets/src/lib.rs`, exposing the built-in read-only,
  default workspace, and full-access permission presets plus built-in active
  profile resolution.
- tool context helpers now convert function, JSON, custom, apply-patch,
  aborted, tool-search, and exec-command outputs into upstream-shaped response
  items, including telemetry previews, model-output truncation markers,
  code-mode/post-tool-use JSON preservation, upstream `ToolPayload`
  log-payload variants, and output-truncation content-item policies that merge
  text while preserving image and encrypted content items.
- tool router helpers now build internal `ToolCall` values from model response
  items, preserving namespaced function calls, client-side tool-search calls,
  custom tool calls, extension conversation-history snapshots,
  `function_arguments()` compatibility checks, and upstream-style invalid
  tool-search argument errors.
- tool definition helpers now mirror `codex-rs/tools/src/tool_definition.rs`,
  including name rewriting, deferred-load conversion, output-schema clearing,
  and JSON mapping round-trips without third-party schema libraries.
- code-mode helpers now cover the stdlib-only pure conversion path from
  Responses API tool specs into nested exec tool definitions, including
  upstream namespace naming rules, `exec`/`wait` filtering, exec pragma
  parsing, JSON Schema to TypeScript declaration rendering, namespace grouping,
  code-mode-specific tool description augmentation, runtime request/outcome
  data shapes, script status text, and nested function/freeform tool payload
  conversion, plus the upstream exec freeform grammar, wait tool JSON schema,
  wait-argument parsing, code-mode response item adaptation, and runtime
  response formatting into model-visible function-tool output with upstream
  status headers, error text, image-detail sanitization, and text/mixed-content
  truncation paths. Lightweight exec/wait handlers now mirror the upstream
  payload-kind checks, request construction, callback dispatch boundary, hook
  bypass for `wait`, and response adaptation without starting a V8 runtime.
  The service-facing shell now also preserves upstream cell-id allocation,
  missing-cell responses, pending-result conversion, and injectable
  execute/wait-to-pending callback boundaries. Runtime value helpers now
  mirror the stdlib-portable parts of `runtime/value.rs`, including text
  serialization and `image(...)` normalization for URL strings, `{image_url,
  detail}` objects, MCP image blocks, data URL construction, detail overrides,
  and upstream error text. Runtime globals helpers now also produce upstream
  `ALL_TOOLS` metadata and spec-planning sort order for direct and namespaced
  nested tools. Timer helpers now mirror `runtime/timers.rs` delay/id
  normalization for `setTimeout` and `clearTimeout`, including fractional
  truncation, invalid/non-finite handling, and `u64` saturation. Store/load,
  notify, and exit helpers now cover the stdlib-portable callback behavior for
  JSON-only runtime state, stored-value write tracking, non-empty notifications,
  and the upstream exit sentinel. Runtime command/control/event data shapes now
  mirror the V8 host boundary variants for tool responses, tool errors,
  timeout firing, termination, pending/yield notifications, nested tool calls,
  content items, stored-value writes, and result errors. Module-loader boundary
  helpers now also cover completion-state projection, exit-sentinel rejection,
  unsupported static/dynamic import messages, and stack-preferring error text.
  Main-loop control helpers now mirror `next_runtime_command` pending behavior
  for immediate commands, yielded pending events, continue-mode waiting,
  pause-until-resumed control messages, and termination control flow. Runtime
  callback helpers now mirror nested tool-call event generation, including
  callback-data index parsing, `tool-N` id allocation with `u64` saturation,
  JSON input normalization, pending tool-call id tracking, and metadata-based
  tool name/kind selection. Text/image callback helpers now emit upstream
  `RuntimeEvent::ContentItem` values, reusing the text serialization and image
  URL/detail normalization paths. Notify/yield/exit callback helpers now emit
  upstream notify and yield runtime events and expose the shared exit sentinel
  plus completion-state projection for callback shutdown.
- hosted tool spec helpers now generate image-generation, web-search, and
  freeform custom tool specs with upstream live/cached/disabled access flags,
  configured filters, location, context size, text+image search content types,
  and grammar-format custom tool serialization.
- web-search display helpers now mirror `core/src/web_search.rs`, deriving
  compact action details for search, open-page, find-in-page, and query
  fallback cases.
- connector helpers now derive accessible ChatGPT connectors from MCP tool
  metadata, generate upstream install URLs/slugs, merge plugin connector
  placeholders with accessible connector metadata, carry plugin display names,
  apply user/requirements app-enabled overrides, and evaluate Codex Apps
  tool policy from app defaults, per-tool overrides, managed approval modes,
  and destructive/open-world annotations.
- app/plugin render helpers now mirror `core/src/apps/render.rs` and
  `core/src/plugins/render.rs`, returning model-visible Apps/Plugins sections
  only when available capabilities warrant them and rendering explicit plugin
  instructions for skill prefixes, MCP servers, and app connectors.
- mention syntax constants now mirror the upstream shared plaintext sigils for
  tool (`$`) and plugin text (`@`) mentions.
- plugin/app mention collection now mirrors `core/src/plugins/mentions.rs` and
  the shared mention parser from `core-skills/src/injection.rs`, including
  Markdown linked mentions, common shell environment variable suppression,
  `app://` and `plugin://` path extraction, plugin-order-preserving selection,
  and connector mention slug counting without third-party dependencies.
- explicit skill mention selection now mirrors the pure
  `core-skills/src/injection.rs` path/name resolution behavior, including
  structured-skill priority, disabled-path blocking, linked-path selection,
  ambiguous-name suppression, connector slug conflict avoidance, and upstream
  skill-name count handling.
- skill injection loading now mirrors the standard-library surface of
  `core-skills/src/injection.rs`, preserving mentioned-skill order,
  `SkillInjection`/`SkillInjections` result shapes, SKILL.md content loading,
  missing-file warning collection, and continue-after-error behavior.
- implicit skill invocation helpers now mirror
  `core-skills/src/invocation_utils.rs`, including SKILL.md/scripts directory
  indexes, command tokenization, script runner/extension detection,
  file-reader command detection, workdir-relative path resolution, and
  disabled/policy-filtered implicit-skill eligibility.
- core skill model helpers now mirror the product-restriction slice of
  `core-skills/src/model.rs`, including `SkillPolicy` product lists,
  skill-level product matching, and `SkillLoadOutcome` filtering that keeps
  skills, roots, root maps, and implicit indexes in sync.
- skill config rule helpers now mirror `core-skills/src/config_rules.rs`,
  collecting user/session `skills.config` overrides in precedence order,
  parsing name/path selectors, deduplicating later overrides, and resolving
  disabled skill document paths for loaded skill metadata.
- skill metadata rendering helpers now mirror the dependency-free budgeted
  rendering and alias-table slices of `core-skills/src/render.rs`, including
  default 2% context-window budgets, scope/name/path ordering, equalized
  description truncation, omitted-skill warnings, implicit-skill filtering,
  `r0` skill-root aliases, and plugin marketplace root compaction.
- remote skill API helpers now mirror the low-level, not-yet-wired client in
  `core-skills/src/remote.rs`, including backend-auth validation, `/hazelnuts`
  query construction, export download status handling, zip payload detection,
  prefix stripping, and safe zip extraction into `CODEX_HOME/skills/<id>`.
- registry hook helpers now cover flattened tool names, default function
  pre/post hook payloads, JSON-or-string hook input parsing, spawn-agent hook
  aliases, output override preference, and hook input rewrites.
- tool registry primitives now cover upstream tool exposure modes, duplicate
  registration checks, explicit plain-vs-namespaced lookup, hidden-tool
  parallel suppression, payload-kind matching, and router-level parallel
  capability queries.
- tool-search entry helpers now convert function and namespace specs into
  deferred loadable outputs, apply default namespace descriptions, strip output
  schemas from deferred tools, carry source metadata, and coalesce namespace
  search results.
- tool-search handler helpers now build the upstream client-side `tool_search`
  spec, deduplicate source descriptions, implement BM25-style deferred-tool
  search without third-party Python dependencies, validate query/limit payloads,
  and return coalesced `ToolSearchOutput` values.
- tool discovery helpers now model connector/plugin discoverability, upstream
  request-plugin-install wire names, Codex TUI plugin filtering, and
  `list_available_plugins_to_install` result entries.
- request-plugin-install helpers now build upstream-shaped MCP elicitation
  requests, expose list/request function specs, sort and truncate install
  candidates, validate model arguments, extract plugin-install elicitation
  telemetry metadata, persist declined install suggestions through
  `tool_suggest.disabled_tools`, verify installed plugin entries from
  marketplace-shaped data, model connector refresh/completion checks with an
  injectable callback, and keep the session-dependent install confirmation
  behind an explicit callback.
- tool spec planning helpers now build model-visible specs and dispatch
  registries from planned runtimes, honor direct/deferred/direct-model-only/
  hidden exposure, inject `tool_search` for searchable deferred tools, add
  discoverable plugin-install tools behind feature gates, merge namespace specs
  with sorted functions and default descriptions, and filter namespace specs
  when provider support is unavailable.
- dynamic tool handlers now convert thread-provided dynamic tool specs into
  function or namespace tool specs, preserve direct-vs-deferred exposure,
  generate searchable metadata from names/descriptions/schema properties,
  surface Dynamic-tools source info, and turn callback responses into
  `FunctionToolOutput` content.
- MCP tool handlers now convert MCP `ToolInfo` metadata into namespaced
  Responses API specs, preserve connector/namespace descriptions, generate
  search metadata from server/tool/connector/plugin/schema fields, expose
  MCP source info, honor server/read-only parallel-call hints, and integrate
  direct/deferred MCP tools into spec planning.
- MCP tool exposure planning now mirrors `core/src/mcp_tool_exposure.rs`,
  filtering Codex Apps tools through accessible connectors and app policy,
  directly exposing small tool sets, and deferring large or forced-deferred
  tool sets behind `tool_search`.
- MCP skill dependency helpers now mirror the pure slice of
  `core/src/mcp_skill_dependencies.rs`, including canonical MCP dependency
  keys, streamable-http/stdio server config defaults, missing-dependency
  collection, prompted-dependency filtering, and sorted prompt display names.
- MCP tool-call approval helpers now model upstream approval decisions,
  Prompt-mode remember normalization, approval-required annotation logic,
  session/persistent approval cache keys for custom MCP servers and Codex Apps
  connectors, prompt option gating, and custom MCP server approval-mode
  precedence from user config before plugin config; they also build upstream
  approval questions, fallback prompt text, approval elicitation metadata,
  display params, question-id detection, and RequestUserInput/elicitation
  response parsing, session remembered-approval cache updates, and persistent
  approval `ConfigEdit::SetPath` segment/value planning for Codex Apps, custom
  MCP servers, and plugin MCP servers, plus model-facing image-result
  sanitization and bounded event-copy truncation for large MCP results or error
  strings. MCP request
  metadata helpers now also preserve turn metadata, plugin IDs, Codex Apps
  call IDs, thread IDs, app resource URIs, and Apps-only `openai/fileParams`
  declarations; MCP tool metadata lookup now preserves tool annotations,
  connector/tool titles and descriptions, connector descriptions, app resource
  URIs, Codex Apps metadata, and Apps-only file params. MCP app usage helpers
  now mirror Codex Apps usage metadata lookup and explicit/implicit invocation
  classification from mentioned connector ids. MCP telemetry helpers now mirror
  upstream call metric names/tag sanitization and allowlisted result span
  attributes, including target-id truncation on character boundaries. Guardian
  MCP review request builders preserve invocation metadata, tool annotations,
  and Guardian review-decision mapping. Session-side
  MCP elicitation helpers now also parse Guardian approval-request metadata into
  MCP tool-call review requests and map Guardian decisions back into upstream
  `ElicitationResponse` shapes with auto-review metadata.
- MCP tool outputs now convert `CallToolResult` into upstream-shaped function
  outputs with wall-time headers, structured-content precedence, MCP image
  content item conversion, original-image-detail sanitization, raw code-mode
  results, and stable pre/post-hook input/response payloads.
- original image-detail helpers now mirror the upstream `codex_tools`
  behavior for model support checks, output-detail normalization, and
  downgrading unsupported `original` images to the default high detail.
- tool dispatch trace helpers now map invocations, direct/code-mode requesters,
  function/tool-search/custom payloads, direct response items, code-mode result
  values, and logging success into upstream-shaped trace data.
- review-format helpers now mirror the upstream user-facing text rendering for
  review output, including single/plural headers, optional selection checkboxes,
  `path:start-end` locations, indented finding bodies, explanation/findings
  section joining, and the reviewer-failed fallback message.
- sandbox-tag helpers now mirror upstream sandbox metric and policy labels for
  disabled, external, managed read-only/workspace-write/full-access profiles,
  platform sandbox selection, Windows sandbox levels, and managed-network
  enforcement decisions.
- event-mapping helpers now mirror `core/src/event_mapping.rs`, converting
  response messages, reasoning, web search, image generation, hook prompts,
  image label wrappers, and contextual user/developer fragments into the
  corresponding turn-item visibility decisions.
- unified-exec output buffering now mirrors
  `core/src/unified_exec/head_tail_buffer.rs`, retaining bounded head/tail byte
  chunks, tracking omitted middle bytes, replacing oversized tail chunks, and
  draining snapshots for later process-manager integration. The pure
  `core/src/unified_exec/mod.rs` defaults now also cover yield-time clamping,
  default max-output token resolution, chunk-id generation, and process/output
  caps, while `process_state.rs` exit/failure state transitions are represented
  as immutable Python dataclass updates. Unified-exec error variants from
  `errors.rs` are represented as Python exceptions with upstream messages and
  sandbox-denied output payloads. The pure `process_manager.rs` environment
  overlay, exec-server process-id, and process-pruning policies are also
  covered for later process-manager integration.
- stream-event helpers now mirror the dependency-free slice of
  `core/src/stream_events_utils.rs`, including generated-image artifact path
  sanitization and base64 persistence, hidden citation/proposed-plan stripping,
  external-context pollution detection, response-input to response-item output
  conversion, and mailbox-delivery deferral decisions.
- turn-timing helpers now mirror the upstream TTFT/TTFM state machine for
  first-token and first-message recording, response-event categories, response
  item first-output detection, and raw assistant output-text aggregation.

The current test suite uses only the Python standard library:

```shell
python -m unittest discover -s tests
```

## First Milestones

1. Create a minimal `pycodex` package layout and command entrypoint.
2. Port protocol/config data models with `dataclasses`, `enum`, and explicit
   JSON serialization.
3. Port CLI argument parsing with `argparse`, matching upstream commands and
   help behavior where practical.
4. Port local state paths, session metadata, and rollout file handling.
5. Build parity tests from upstream fixtures before expanding into agent,
   sandbox, and TUI behavior.
