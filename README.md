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
- command bodies intentionally return "recognized but not implemented yet"
  until the corresponding Rust crates are ported.

`pycodex.config` ports shared config override parsing from
`codex/codex-rs/utils/cli/src/config_override.rs`:

- raw `-c key=value` arguments are preserved first, matching upstream's
  two-stage parsing model.
- values are parsed as TOML through the standard-library `tomllib` module.
- invalid TOML values fall back to strings, matching upstream convenience
  behavior for values such as `model=gpt-5`.
- dotted override paths can be applied onto nested Python mappings.

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
`codex/codex-rs/exec/src/cli.rs`:

- main `codex exec [OPTIONS] [PROMPT]` parsing is represented by `ExecCli`.
- `resume` and `review` subcommand argument shapes are represented explicitly.
- global flags that upstream allows after `resume` are accepted after the
  subcommand.
- the removed `--full-auto` flag reports the upstream migration warning.

`pycodex.core` starts the local state and rollout port from
`codex/codex-rs/utils/home-dir`, `codex/codex-rs/state`,
`codex/codex-rs/rollout`, and `codex/codex-rs/core`:

- `find_codex_home()` follows the upstream `CODEX_HOME` validation rules.
- runtime DB filenames and path helpers match the Rust constants.
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
- permissions instructions now render the upstream sandbox/approval developer
  context, including network status, writable roots, on-request escalation
  guidance, sandboxed permission requests, granular approval categories,
  approved command prefixes, and auto-review guidance.
- network policy decision helpers now mirror the upstream approval-context
  extraction, denied-request user messages, and execution-policy network rule
  amendment conversion for HTTP, HTTPS connect, and SOCKS protocols.
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
- tool context helpers now convert function, custom, apply-patch, aborted,
  tool-search, and exec-command outputs into upstream-shaped response items,
  including telemetry previews, model-output truncation markers, and
  output-truncation content-item policies that merge text while preserving
  image and encrypted content items.
- tool router helpers now build internal `ToolCall` values from model response
  items, preserving namespaced function calls, client-side tool-search calls,
  custom tool calls, and upstream-style invalid tool-search argument errors.
- hosted tool spec helpers now generate image-generation, web-search, and
  freeform custom tool specs with upstream live/cached/disabled access flags,
  configured filters, location, context size, text+image search content types,
  and grammar-format custom tool serialization.
- connector helpers now derive accessible ChatGPT connectors from MCP tool
  metadata, generate upstream install URLs/slugs, merge plugin connector
  placeholders with accessible connector metadata, carry plugin display names,
  apply user/requirements app-enabled overrides, and evaluate Codex Apps
  tool policy from app defaults, per-tool overrides, managed approval modes,
  and destructive/open-world annotations.
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
  telemetry metadata, and keep the session-dependent install confirmation
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
