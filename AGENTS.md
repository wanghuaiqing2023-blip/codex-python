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

## Porting discipline

When implementing functionality:

- Use `codex/` as the authoritative source for Rust behavior.
- Prefer narrow, behavior-focused slices that move Python closer to Rust Codex.
- Keep the implementation dependency-light and standard-library-first.
- Update `PORTING_STATUS.md` and `porting_notes/turns/` for meaningful progress.
- Validate only the touched behavior unless broader validation is explicitly requested.
