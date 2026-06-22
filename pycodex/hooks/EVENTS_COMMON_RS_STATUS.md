# codex-hooks src/events/common.rs Status

Rust crate: `codex-hooks`

Rust module: `src/events/common.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Behavior Contract

- `SubagentHookContext` carries `agent_id` and `agent_type`.
- Text/context helpers preserve Rust semantics for joining chunks, trimming
  non-empty text, appending model context entries, and flattening context
  slices.
- Serialization failure helpers create failed hook-completed events with
  `completed_at = started_at`, `duration_ms = 0`, and a single error entry.
- Tool-use helpers append `:<tool_use_id>` to hook run IDs.
- Matcher helpers preserve match-all, exact literal/pipe, regex fallback,
  invalid-regex rejection, matcher input ordering, and event-specific matcher
  support.

## Rust Evidence

- `codex/codex-rs/hooks/src/events/common.rs`
- Rust tests:
  - `matcher_omitted_matches_all_occurrences`
  - `matcher_star_matches_all_occurrences`
  - `matcher_empty_string_matches_all_occurrences`
  - `exact_matcher_supports_pipe_alternatives`
  - `literal_matcher_uses_exact_matching`
  - `matcher_uses_regex_when_it_contains_regex_characters`
  - `mcp_matchers_support_regex_wildcards`
  - `matcher_supports_anchored_regexes`
  - `invalid_regex_is_rejected`
  - `unsupported_events_ignore_matchers`
  - `supported_events_keep_matchers`

## Python Evidence

- `tests/test_hooks_events_common_rs.py`

Focused validation:

```text
python -m pytest tests/test_hooks_events_common_rs.py -q --tb=short
```

Passed on 2026-06-21 with `12 passed`.
