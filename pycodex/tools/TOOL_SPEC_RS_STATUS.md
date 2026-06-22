# codex-tools src/tool_spec.rs status

Status: complete_candidate

Rust crate: `codex-tools`
Rust module: `codex/codex-rs/tools/src/tool_spec.rs`
Rust tests: `codex/codex-rs/tools/src/tool_spec_tests.rs`
Python module: `pycodex/tools/tool_spec.py`
Python tests: `tests/test_core_hosted_spec.py`, `tests/test_core_client.py`

## Behavior contract

`src/tool_spec.rs` owns top-level Responses API tool specs:

- `ToolSpec::name()` for function, namespace, tool_search, image_generation,
  web_search, and freeform/custom variants.
- Responses API JSON serialization via `create_tools_json_for_responses_api`.
- `ResponsesApiWebSearchFilters` and
  `ResponsesApiWebSearchUserLocation` adapters from config-layer web-search
  types.
- Web-search, image-generation, custom/freeform, and tool-search wire shapes.

Function and namespace payload structs are owned by `src/responses_api.rs`.
Python therefore accepts those dependency payloads through mapping/to_mapping
interfaces in this module instead of duplicating the responses-api module.

## Python alignment

`pycodex.tools.tool_spec` implements the Rust-owned top-level variant wrapper,
name resolution, web-search adapters, tool-search/image-generation/freeform
constructors, and Responses API JSON serialization facade. Existing core hosted
tool helpers continue to carry the runtime web-search/image-generation use
cases; this module adds the canonical `codex-tools` ownership path.

## Evidence

Existing Python coverage validates the behavior contract:

- `tests/test_core_hosted_spec.py` covers freeform/custom, image generation,
  web-search config preservation, cached mode, disabled mode, and invalid
  variant shapes.
- `tests/test_core_client.py` covers `create_tools_json_for_responses_api`,
  mapping tools, nested enum serialization, and Rust-like omission of function
  output schemas.

Focused validation is deferred by the current crate automation rule until
`codex-tools` functional module code is complete.
