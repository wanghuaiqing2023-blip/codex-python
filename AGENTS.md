# AGENTS.md

## Project mission

This project ports OpenAI Codex from the upstream Rust implementation in `codex/` to Python in `pycodex/`.

The goal is to preserve the core logic and common user-facing behavior as closely as possible while avoiding complex Python third-party dependencies. Prefer Python standard-library implementations unless a dependency is clearly necessary and approved.

## Current implementation priority

Current scope decision: first replicate Codex's core and commonly used features. MCP, plugin, marketplace, and other extension capabilities are not part of the active implementation target unless the core runtime directly needs a compatibility shim.

Focus on the common and core Codex experience first:

- CLI entrypoints needed for normal use, especially `exec` and interactive task execution.
- Core agent loop: user input, model request construction, streaming/response handling, tool-call execution, and final answer generation.
- Context assembly: project instructions, working directory, environment metadata, model/config selection, and conversation/session state.
- File and command tools: shell execution, reading/writing files, applying patches, and returning tool results to the model.
- Approval/safety behavior: dangerous command handling, write/network/sandbox policy approximation, and clear user-facing errors.
- App-server protocol/event model only where it is needed by the CLI/core runtime path.

## Deprioritized extension areas

Do not spend significant implementation time on these until the core agent loop is useful and stable:

- MCP runtime and external MCP server integrations.
- Plugin marketplace, plugin install/cache details, and plugin runtime behavior.
- Marketplace management beyond compatibility stubs needed to avoid obvious CLI breakage.
- Skills/plugin discovery beyond what is required for the core prompt/context path.
- Multi-agent/sub-agent orchestration.
- Cloud tasks and remote task execution.
- Telemetry, analytics, update checks, and marketplace backend features.
- App-server daemon, proxy, remote control, websocket transport, and schema-generation paths, except where a small compatibility shim helps the core CLI flow.

## Compatibility rule for extension areas

For MCP/plugin/marketplace and similar extension areas:

- Prefer lightweight compatibility shims over deep implementation.
- Keep existing behavior from regressing when it is already implemented.
- Do not continue expanding these areas unless the user explicitly asks or the core runtime depends on them.
- Document known gaps instead of fully implementing non-core extension behavior.

## Upstream knowledge graph

The upstream Rust source tree in `codex/` has an understand knowledge graph at:

- `codex/.understand-anything/knowledge-graph.json`

Use this graph as a navigation aid before doing broad source searches. It is intended to reduce token usage and search time by helping identify relevant files, symbols, import relationships, layers, and tour entry points inside the upstream implementation.

Recommended workflow when comparing or porting Rust behavior:

- Do not load the entire knowledge graph into model context.
- Query it selectively with small scripts or targeted JSON inspection, and summarize only the relevant nodes, edges, layers, or tour steps.
- Start with the knowledge graph to locate likely upstream files and relationships.
- Then read the small set of authoritative Rust files needed for the behavior being ported.
- Cross-check against `pycodex/` only after the upstream behavior is clear.
- Prefer targeted searches guided by graph node paths and edge relationships over broad repository scans.
- Treat the graph as an index, not as a replacement for source code; final behavior decisions must come from the Rust source.

The graph was generated for `codex/` only. Do not assume it describes `pycodex/`, tests, or project files outside `codex/` unless a separate graph is generated for those areas.

## Dependency-graph-driven priorities

When deciding what to implement next, use the upstream knowledge graph dependency relationships as the first planning input, not just the most visible local gap.

Priority workflow:

- Start from core user-facing entrypoints such as `exec`, interactive task execution, request/response streaming, tool dispatch, and final answer generation.
- Follow graph `calls`, `imports`, `exports`, and containing file relationships to identify the Rust modules and functions on the common runtime path.
- Prefer high-impact nodes that unblock many downstream behaviors, especially high fan-in/fan-out modules on the CLI/core agent loop path.
- Rank work by whether it helps complete an end-to-end common Codex flow before expanding peripheral parity details.
- Filter out MCP/plugin/marketplace/cloud/TUI branches unless the dependency path shows they are required for the core runtime slice being implemented.
- After identifying the Rust dependency slice, map it to the corresponding `pycodex/` modules and implement the smallest coherent Python slice that advances the common runtime path.
- Use targeted Rust source reads to confirm behavior after the graph identifies likely files; the graph determines navigation and priority, while Rust source determines final behavior.

## Mainline-first parity work

Local parity fixes and boundary coverage are necessary, but they should serve the graph-selected core runtime path instead of becoming an open-ended default task.

Use this balance when choosing work:

- Prefer mainline progress when the core `exec`/agent-loop/tool-dispatch/final-answer flow is not yet usable.
- Do local parity and boundary coverage primarily inside modules that the knowledge graph shows are on the current core dependency slice.
- Avoid spending long sequences of turns on adjacent edge cases unless they unblock or protect the current end-to-end slice.
- When a local parity issue is discovered outside the active dependency slice, document it as a follow-up unless it is a clear regression or a small compatibility shim needed by the core path.
- Treat an end-to-end runnable slice as more valuable than many isolated helper modules that are individually precise but not connected.
- A healthy default split is roughly 60-70% graph-driven core-path implementation, 20-30% parity and boundary coverage on that path, and 10% documentation/status cleanup.
- Before continuing local edge-case work, ask whether the same effort would more directly advance `exec -> context -> model request -> stream handling -> tool dispatch -> final answer`.

## Porting discipline

When implementing functionality:

- Use `codex/` as the authoritative source for Rust behavior.
- Prefer narrow, behavior-focused slices that move Python closer to Rust Codex.
- Keep the implementation dependency-light and standard-library-first.
- Update `PORTING_STATUS.md` and `porting_notes/turns/` for meaningful progress.
- Validate only the touched behavior unless broader validation is explicitly requested.
