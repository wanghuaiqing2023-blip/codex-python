# codex-protocol test alignment

This ledger records Rust module-scoped behavior contracts for `codex-protocol`
that have explicit Python parity evidence.

Focused crate validation after all functional modules were recorded:
`$files = Get-ChildItem tests -Filter 'test_protocol_*.py' | ForEach-Object { $_.FullName }; python -m pytest $files -q`
passed on 2026-06-17 with `369 passed, 118 subtests passed`.

### `src/lib.rs` crate root surface

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/lib.rs`
- Python package root: `pycodex/protocol/__init__.py`
- Python status file: `pycodex/protocol/LIB_RS_STATUS.md`
- Status: `complete_slice`
- Evidence: Rust `lib.rs` declares the crate module graph and re-exports
  `AgentPath`, `SessionId`, `ThreadId`, and `ToolName` from private modules.
  Python mirrors this through package-root imports/`__all__`, maps public Rust
  modules to sibling Python modules, and documents the intentional
  `permissions.rs` merge into `models.py`.
- Focused validation: covered by the 2026-06-17 crate-level protocol run
  (`369 passed, 118 subtests passed`).

## complete_slice

### `src/models.rs` response input function-call encrypted output array

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `ResponseInputItem::FunctionCallOutput` encrypted content serialization is mirrored for content-item payloads: encrypted output serializes `output` as an array with `type: encrypted_content` and the opaque encrypted payload, while absent optional `success` is omitted. The Python parity test directly derives from Rust `serializes_encrypted_function_output_content_as_array`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k encrypted_content_serializes_array -q` passed on 2026-06-16 with `1 passed, 49 deselected`.

### `src/models.rs` response input custom-tool image output array

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `ResponseInputItem::CustomToolCallOutput` image output serialization is mirrored for content-item payloads: image payloads serialize `output` as an array and preserve `DEFAULT_IMAGE_DETAIL`, with absent optional `name`/`success` omitted. The Python parity test directly derives from Rust `serializes_custom_tool_image_outputs_as_array`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k custom_tool_call_output_image_outputs_serialize_array -q` passed on 2026-06-16 with `1 passed, 48 deselected`.

### `src/models.rs` response input function-call image output array

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `ResponseInputItem::FunctionCallOutput` image output serialization is mirrored for content-item payloads: text plus image payloads serialize `output` as an array, preserve explicit `success: true`, and keep the image `detail` at `DEFAULT_IMAGE_DETAIL`. The Python parity test directly derives from Rust `serializes_image_outputs_as_array` while staying within the response-input serialization boundary.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k image_outputs_serialize_array -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` response input function-call output failure

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `ResponseInputItem::FunctionCallOutput` failure serialization is mirrored for text payloads: failed text output serializes `output` as the plain string `"bad"` rather than an object or array, while Python preserves the explicit `success: false` field. The Python parity test directly derives from Rust `serializes_failure_as_string`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k failure_serializes_string -q` passed on 2026-06-16 with `1 passed, 46 deselected`.

### `src/models.rs` response input function-call output success

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `ResponseInputItem::FunctionCallOutput` success
  serialization is mirrored for text payloads: a successful
  `FunctionCallOutputPayload::from_text("ok")` serializes `output` as the
  plain string `"ok"` with the `function_call_output` type and call id. The
  Python parity test directly derives from Rust
  `serializes_success_as_plain_string`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k plain_string -q`
  passed on 2026-06-16 with `1 passed, 45 deselected`.

### `src/models.rs` allow-prefix text-budget truncation

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `format_allow_prefixes` text-budget truncation behavior is
  mirrored: very long rendered allow-prefix output is truncated to at most
  `MAX_ALLOW_PREFIX_TEXT_BYTES + len(TRUNCATED_MARKER)` and appends
  `TRUNCATED_MARKER`. The Python parity test directly derives from Rust
  `format_allow_prefixes_limits_output`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k limits_output_bytes -q`
  passed on 2026-06-16 with `1 passed, 44 deselected`.

### `src/models.rs` allow-prefix max-prefix truncation

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `format_allow_prefixes` max-prefix truncation behavior is
  mirrored: lists longer than `MAX_RENDERED_PREFIXES` render only the first
  maximum number of sorted prefixes and append `TRUNCATED_MARKER`, producing
  `MAX_RENDERED_PREFIXES + 1` output lines. The Python parity test directly
  derives from Rust `render_command_prefix_list_limits_output_to_max_prefixes`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k max_prefixes -q`
  passed on 2026-06-16 with `1 passed, 43 deselected`.

### `src/models.rs` allow-prefix rendering sort order

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `format_allow_prefixes` ordering behavior is mirrored for
  command prefixes sorted by token count, total token length, and
  lexicographic token order before rendering as JSON-style token arrays. The
  Python parity test directly derives from Rust
  `render_command_prefix_list_sorts_by_len_then_total_len_then_alphabetical`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k format_allow_prefixes -q`
  passed on 2026-06-16 with `1 passed, 42 deselected`.

### `src/models.rs` function call optional namespace

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `ResponseItem::FunctionCall` behavior is mirrored for
  optional `namespace` deserialization and serialization. The Python parity
  test directly derives from Rust
  `function_call_deserializes_optional_namespace` and verifies the MCP
  namespaced function-call shape preserves `name`, `namespace`, `arguments`,
  and `call_id`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k optional_namespace -q`
  passed on 2026-06-16 with `1 passed, 41 deselected`.

### `src/models.rs` function call output text fallback

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `function_call_output_content_items_to_text` and
  `FunctionCallOutputBody::to_text` behavior is mirrored for joining
  non-blank text segments while ignoring images, returning `None` for blank
  text plus non-text content, returning plain text body content directly, and
  using content-item lossy text fallback for content-item bodies. The Python
  test is now tied directly to the four Rust tests covering these paths.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k upstream_lossy_rules -q`
  passed on 2026-06-16 with `1 passed, 40 deselected`.

### `src/models.rs` MCP content conversion without images

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `convert_mcp_content_to_items` behavior is mirrored for MCP
  content arrays that contain no image blocks: Python returns `None`, so
  callers keep using the serialized text payload path instead of content-item
  output. The Python parity test directly derives from Rust
  `convert_mcp_content_to_items_returns_none_without_images`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k without_images -q`
  passed on 2026-06-16 with `1 passed, 40 deselected`.

### `src/models.rs` MCP image detail metadata preservation

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust MCP image metadata conversion is mirrored for `_meta.codex/imageDetail`: raw base64 image data is wrapped into a data URL while `original` maps to `ImageDetail.ORIGINAL` and `high` maps to `ImageDetail.HIGH`. The Python parity test directly derives from Rust `preserves_original_detail_metadata_on_mcp_images` and `preserves_standard_detail_metadata_on_mcp_images`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k preserves_image_detail_metadata -q` passed on 2026-06-16 with `1 passed, 50 deselected, 2 subtests passed`.

### `src/models.rs` MCP content conversion raw image data

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `convert_mcp_content_to_items` behavior is mirrored for MCP
  image content whose `data` field is raw base64 without a `data:` prefix:
  Python builds `data:{mimeType};base64,{data}` and emits a
  `FunctionCallOutputContentItem.input_image` with `DEFAULT_IMAGE_DETAIL`.
  The Python parity test directly derives from Rust
  `convert_mcp_content_to_items_builds_data_urls_when_missing_prefix`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k builds_data_urls -q`
  passed on 2026-06-16 with `1 passed, 39 deselected`.

### `src/models.rs` MCP content conversion data URLs

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `convert_mcp_content_to_items` behavior is mirrored for MCP
  image content whose `data` field is already a data URL: Python preserves the
  data URL unchanged and emits a `FunctionCallOutputContentItem.input_image`
  with `DEFAULT_IMAGE_DETAIL`. The core tool-context private helper now
  delegates to the protocol-owned implementation to keep Rust module ownership
  aligned and avoid duplicated conversion logic.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k convert_mcp_content -q`
  passed on 2026-06-16 with `1 passed, 38 deselected`.
- Related core validation: `python -m pytest tests/test_core_tool_context.py -k "mcp_tool_output_preserves_image_content_items or mcp_tool_output_image_only_content_items_get_wall_time_header" -q`
  passed on 2026-06-16 with `2 passed, 35 deselected`.

### `src/models.rs` runtime permissions preserve unrestricted managed network

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust runtime permission conversion semantics are mirrored for unrestricted filesystem policies when enforcement is not disabled: `PermissionProfile::from_runtime_permissions_with_enforcement` returns a managed unrestricted filesystem profile and preserves the runtime network policy rather than collapsing to disabled or external. Existing Python parity coverage directly derives from Rust `permission_profile_from_runtime_permissions_preserves_unrestricted_managed_network`.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k from_runtime_permissions -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` runtime permissions preserve external sandbox

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust runtime permission conversion semantics are mirrored for external filesystem sandboxes: `PermissionProfile::from_runtime_permissions` returns an external permission profile and preserves the runtime network policy when the filesystem policy is external. Existing Python parity coverage directly derives from Rust `permission_profile_from_runtime_permissions_preserves_external_sandbox`.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k from_runtime_permissions -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` disabled permission profile ignores runtime network policy

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust disabled permission-profile enforcement semantics are mirrored: `PermissionProfile::from_runtime_permissions_with_enforcement` returns a disabled profile for unrestricted filesystem runtime permissions when enforcement is disabled, even if the incoming runtime network policy is restricted. Existing Python parity coverage directly derives from Rust `disabled_permission_profile_ignores_runtime_network_policy`.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k from_runtime_permissions -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` permission profile legacy disabled/external roundtrip

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust legacy permission-profile roundtrip semantics are mirrored for disabled and external sandbox policies: disabled profiles roundtrip to danger-full-access legacy sandbox policy, and external profiles preserve the external sandbox network policy. Existing Python parity coverage directly derives from Rust `permission_profile_round_trip_preserves_disabled_sandbox` and `permission_profile_round_trip_preserves_external_sandbox`.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_profile_to_legacy_sandbox_policy -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` permission profile preset legacy defaults

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust permission profile preset compatibility is mirrored: `PermissionProfile::read_only()` and `PermissionProfile::workspace_write()` match the corresponding legacy sandbox-policy conversions. Existing Python parity coverage directly derives from Rust `permission_profile_presets_match_legacy_defaults`.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_profile_presets_match_legacy_defaults -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` permission profile legacy rollout shape

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust legacy rollout permission-profile shape deserialization is mirrored: an untagged legacy payload with `network.enabled: true`, restricted filesystem entries, and `glob_scan_max_depth` is parsed into a managed `PermissionProfile` with enabled network and restricted managed filesystem permissions. Existing Python parity coverage directly derives from Rust `permission_profile_deserializes_legacy_rollout_shape`.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k legacy_rollout_shape -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` managed filesystem runtime policy bridge

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust managed filesystem bridge behavior is mirrored for runtime filesystem policies: restricted sandbox policies convert to restricted managed filesystem permissions, unrestricted runtime policies convert to unrestricted managed permissions, and external sandbox policies are rejected because they belong to `PermissionProfile::External`. Existing Python coverage exercises this local model bridge via `ManagedFileSystemPermissions.from_sandbox_policy`.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k direct_runtime_enforcement_detects_unbridgeable_and_metadata_cases -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` managed filesystem permission tagged shapes

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust managed filesystem permission tagged shape is mirrored: unrestricted and restricted variants parse from canonical mappings, restricted variants validate entries and `glob_scan_max_depth`, unrestricted rejects entries/depth, and unknown or invalid type values are rejected. Existing Python parity coverage exercises this model boundary through the permission profile canonical-shape test.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_profile_mapping_roundtrips_canonical_shapes -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` permission profile tagged canonical shapes

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust tagged `PermissionProfile` serde shape is mirrored for managed, disabled, and external profiles: canonical mappings roundtrip, managed profiles require valid filesystem/network fields, disabled profiles reject extra filesystem/network fields, external profiles require network and reject filesystem, and unknown/invalid type values are rejected. Existing Python parity coverage exercises the Rust public model contract for tagged permission profiles.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_profile_mapping_roundtrips_canonical_shapes -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` active permission profile identity surface

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `ActivePermissionProfile` surface behavior is mirrored: `read_only()` uses the built-in read-only profile id, `new(id)` preserves explicit ids, optional `extends` is omitted when absent and preserved when present, and invalid id/extends field types are rejected. Existing Python parity coverage derives from the Rust public model contract around `ActivePermissionProfile` constructors and serde shape.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k active_permission_profile_read_only_identity -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` filesystem sandbox policy mapping roundtrip

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxPolicy` serde/public API shape is mirrored for restricted, unrestricted, and external sandbox policies: mapping roundtrips preserve entries and `glob_scan_max_depth`, zero and non-integer depth inputs are rejected, invalid kinds are rejected, and entry type boundaries are enforced. This is a module-local model contract adjacent to Rust `FileSystemSandboxPolicy`/`PermissionProfile` tests.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k sandbox_and_filesystem_policy_mapping_roundtrips -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` filesystem permissions reject zero glob depth

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemPermissions` validation is mirrored for `glob_scan_max_depth`: zero depth is rejected during canonical mapping deserialization and direct construction, and non-integer values are rejected as type errors. Existing Python parity coverage directly derives from Rust `file_system_permissions_rejects_zero_glob_scan_depth`.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k filesystem_permissions_mapping_uses_canonical_entries_shape -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` filesystem permissions glob depth canonical JSON

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemPermissions` canonical JSON behavior is mirrored when `glob_scan_max_depth` is present: permissions serialize using the canonical `entries` shape plus `glob_scan_max_depth`, and the canonical shape roundtrips back to the same permissions object. Existing Python parity coverage directly derives from Rust `file_system_permissions_with_glob_scan_depth_uses_canonical_json`.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k filesystem_permissions_mapping_uses_canonical_entries_shape -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` permission profile glob scan depth roundtrip

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `PermissionProfile::from_runtime_permissions` roundtrip semantics are mirrored for restricted filesystem policies with glob deny entries and `glob_scan_max_depth`: converting runtime permissions into a permission profile and back through `file_system_sandbox_policy()` preserves the original policy, including the nonzero scan depth. The Python parity coverage directly derives from Rust `permission_profile_round_trip_preserves_glob_scan_max_depth`.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k from_runtime_permissions -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` additional permission profile empty semantics

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `AdditionalPermissionProfile::is_empty` semantics are mirrored: a default profile with both optional fields absent is empty, but a present `network` field is non-empty even when the nested `NetworkPermissions` is itself empty. The Python parity coverage directly derives from Rust `additional_permission_profile_is_empty_when_all_fields_are_none` and `additional_permission_profile_is_not_empty_when_field_is_present_but_nested_empty`.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_overlay_empty_helpers -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` sandbox permissions helpers

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `SandboxPermissions` helper semantics are mirrored for
  `UseDefault`, `RequireEscalated`, and `WithAdditionalPermissions` across
  `requires_escalated_permissions`, `requests_sandbox_override`, and
  `uses_additional_permissions`. The Python test now uses the same truth table
  as Rust `sandbox_permissions_helpers_match_documented_semantics`.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k sandbox_permissions -q`
  passed on 2026-06-16 with `1 passed, 47 deselected, 3 subtests passed`.

### `src/models.rs` image detail wire values

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `ImageDetail` serde behavior is mirrored for `auto` and
  `low` wire-value parsing/serialization, and `ContentItem::InputImage`
  parsing preserves `detail: "auto"` as `ImageDetail::Auto`. Existing Python
  coverage also exercises requested remote image detail preservation.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k image_detail -q`
  passed on 2026-06-16 with `2 passed, 36 deselected`.

### `src/models.rs` response input message conversion

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `impl From<ResponseInputItem> for ResponseItem` message
  conversion is mirrored for assistant message content and preservation of
  optional `MessagePhase::Commentary` into `ResponseItem::Message`. The
  Python parity test is tied directly to Rust
  `response_input_message_conversion_preserves_phase`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k response_input_message_conversion -q`
  passed on 2026-06-16 with `1 passed, 36 deselected`.

### `src/models.rs` image generation response items

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `ResponseItem::ImageGenerationCall` behavior is mirrored for
  required `id`, `status`, and `result` fields, optional `revised_prompt`
  preservation, and omission of absent `revised_prompt` on serialization. The
  Python parity test directly derives from Rust
  `response_item_parses_image_generation_call` and
  `response_item_parses_image_generation_call_without_revised_prompt`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k image_generation -q`
  passed on 2026-06-16 with `1 passed, 36 deselected`.

### `src/models.rs` tool search response items

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `ResponseItem::ToolSearchCall` and
  `ResponseItem::ToolSearchOutput` behavior is mirrored for client
  call/output roundtrips, server execution with explicit null `call_id`,
  status/execution/arguments/tools preservation, and empty tool result
  serialization. This pass fixed Python serialization to emit
  `"call_id": null` for tool-search call/output items when call_id is absent,
  and to preserve `tools: []` for tool-search outputs, matching Rust serde.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k tool_search -q`
  passed on 2026-06-16 with `1 passed, 35 deselected`.

### `src/models.rs` local image requested detail preservation

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `ResponseInputItem::from(Vec<UserInput>)` local image detail preservation is mirrored for successfully attached local images: a `UserInput::LocalImage` with requested `ImageDetail::Original` emits the local image open tag, an input image with `detail: original`, and the close tag. The Python parity test directly derives from Rust `local_image_user_input_preserves_requested_detail`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k local_image_preserves_requested_detail -q` passed on 2026-06-16 with `1 passed, 53 deselected`.

### `src/models.rs` mixed remote/local image label sequencing

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `ResponseInputItem::from(Vec<UserInput>)` label sequencing is mirrored across mixed remote and local images: the remote image is emitted directly, the following local image uses label number 2 in the local image open tag, then emits the local image and close tag. The Python parity test directly derives from Rust `mixed_remote_and_local_images_share_label_sequence`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k mixed_remote_and_local_images -q` passed on 2026-06-16 with `1 passed, 52 deselected`.

### `src/models.rs` local image error placeholders

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust local image user-input placeholder behavior is mirrored for
  read errors, non-image MIME files, unsupported image formats such as SVG,
  invalid bytes for otherwise supported image MIME types, and placeholder text
  containing the local path and reason. This pass fixed Python MIME filtering
  so `image/svg+xml` follows the Rust unsupported-image placeholder path rather
  than the decode-error path.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k "local_image or non_image_mime or svg_mime or invalid_local_image" -q`
  passed on 2026-06-16 with `4 passed, 31 deselected`.

### `src/models.rs` remote image user input conversion

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `ResponseInputItem::from(Vec<UserInput>)` behavior for
  remote image inputs is mirrored for direct `input_image` conversion without
  XML image tags, default `ImageDetail::High`, requested detail preservation
  such as `ImageDetail::Original`, and filtering of non-text/non-image user
  input variants from model request content.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k response_input_from_user_inputs -q`
  passed on 2026-06-16 with `6 passed, 27 deselected`.

### `src/models.rs` function call output payloads

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `FunctionCallOutputPayload` behavior is mirrored for plain
  text output, array payloads deserialized into content items, encrypted
  content items, serialization back to the array shape, lossy text extraction
  that joins non-blank text items while ignoring images/encrypted content, and
  invalid wire shape boundaries.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k function_call_output -q`
  passed on 2026-06-16 with `5 passed, 27 deselected`.

### `src/mcp.rs` module summary

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/mcp.rs`
- Python module: `pycodex/protocol/mcp.py`
- Python tests: `tests/test_protocol_mcp_dynamic_tools.py`
- Status: `complete_slice`
- Evidence: The Rust MCP protocol value module is covered by focused slices
  for `RequestId`, `Tool`, `Resource`, `ResourceContent`, `ResourceTemplate`,
  `CallToolResult`, and lossy `Resource::size` adapter behavior. These cover
  the module's public TS/JSON-schema-friendly value surface, MCP wire adapter
  aliases, camelCase protocol serialization, `_meta` handling, i64 request/size
  boundaries, and invalid Python shape boundaries.
- Focused validation: `python -m pytest tests/test_protocol_mcp_dynamic_tools.py -k "request_id or mcp_values or tool_from_mcp_value or resource_size or resource_template_adapter or resource_adapter or resource_content or call_tool_result" -q`
  passed on 2026-06-16 with `9 passed, 9 deselected`.

### `src/mcp.rs` request id

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/mcp.rs`
- Python module: `pycodex/protocol/mcp.py`
- Python tests: `tests/test_protocol_mcp_dynamic_tools.py`
- Status: `complete_slice`
- Evidence: Rust `RequestId` behavior is mirrored for untagged string and
  i64 integer variants, `Display` string conversion, JSON scalar output,
  i64 min/max boundaries, and rejection of bool/non-i64 integer inputs.
- Focused validation: `python -m pytest tests/test_protocol_mcp_dynamic_tools.py -k request_id -q`
  passed on 2026-06-16 with `2 passed, 16 deselected`.

### `src/mcp.rs` call tool result payload

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/mcp.rs`
- Python module: `pycodex/protocol/mcp.py`
- Python tests: `tests/test_protocol_mcp_dynamic_tools.py`
- Status: `complete_slice`
- Evidence: Rust `CallToolResult` behavior is mirrored for required content
  arrays, optional `structuredContent`/`isError` camelCase protocol fields,
  snake_case compatibility aliases, optional `_meta`, content tuple
  normalization, and invalid non-list/non-bool boundaries.
- Focused validation: `python -m pytest tests/test_protocol_mcp_dynamic_tools.py -k call_tool_result -q`
  passed on 2026-06-16 with `1 passed, 17 deselected`.

### `src/mcp.rs` resource content adapter variants

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/mcp.rs`
- Python module: `pycodex/protocol/mcp.py`
- Python tests: `tests/test_protocol_mcp_dynamic_tools.py`
- Status: `complete_slice`
- Evidence: Rust `ResourceContent` untagged text/blob behavior is mirrored for
  required `uri`, text and blob payload variants, camelCase `mimeType`,
  snake_case `mime_type` adapter input, optional `_meta`, and protocol
  serialization back to camelCase.
- Focused validation: `python -m pytest tests/test_protocol_mcp_dynamic_tools.py -k resource_content -q`
  passed on 2026-06-16 with `1 passed, 17 deselected`.

### `src/mcp.rs` resource adapter aliases

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/mcp.rs`
- Python module: `pycodex/protocol/mcp.py`
- Python tests: `tests/test_protocol_mcp_dynamic_tools.py`
- Status: `complete_slice`
- Evidence: Rust `Resource::from_mcp_value` MCP adapter behavior is mirrored
  for camelCase `mimeType`, snake_case `mime_type` alias input, required
  `name`/`uri`, optional title/description/annotations/icons/`_meta`, lossy
  size handled by the resource-size slice, and protocol serialization back to
  camelCase plus `_meta`.
- Focused validation: `python -m pytest tests/test_protocol_mcp_dynamic_tools.py -k resource_adapter -q`
  passed on 2026-06-16 with `1 passed, 17 deselected`.

### `src/mcp.rs` resource template adapter aliases

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/mcp.rs`
- Python module: `pycodex/protocol/mcp.py`
- Python tests: `tests/test_protocol_mcp_dynamic_tools.py`
- Status: `complete_slice`
- Evidence: Rust `ResourceTemplate::from_mcp_value` MCP adapter behavior is
  mirrored for camelCase `uriTemplate`/`mimeType`, snake_case
  `uri_template`/`mime_type` aliases, required name, optional title and
  description handling, and protocol serialization back to camelCase.
- Focused validation: `python -m pytest tests/test_protocol_mcp_dynamic_tools.py -k resource_template_adapter -q`
  passed on 2026-06-16 with `1 passed, 17 deselected`.

### `src/mcp.rs` tool adapter aliases

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/mcp.rs`
- Python module: `pycodex/protocol/mcp.py`
- Python tests: `tests/test_protocol_mcp_dynamic_tools.py`
- Status: `complete_slice`
- Evidence: Rust `Tool::from_mcp_value` MCP adapter behavior is mirrored for
  camelCase `inputSchema`/`outputSchema`, snake_case `input_schema` alias
  input, optional title/description/icons, `_meta`, tuple normalization for
  icons, and protocol serialization back to camelCase plus `_meta`.
- Focused validation: `python -m pytest tests/test_protocol_mcp_dynamic_tools.py -k tool_from_mcp_value -q`
  passed on 2026-06-16 with `1 passed, 16 deselected`.

### `src/models.rs` compaction response items

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `ResponseItem` compaction behavior is mirrored for the
  legacy `compaction_summary` alias, `context_compaction` with and without
  encrypted content, and `compaction_trigger` serialization/deserialization
  without extra payload.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k compaction -q`
  passed on 2026-06-16 with `1 passed, 30 deselected`.

### `src/mcp.rs` resource size adapter

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/mcp.rs`
- Python module: `pycodex/protocol/mcp.py`
- Python tests: `tests/test_protocol_mcp_dynamic_tools.py`
- Status: `complete_slice`
- Evidence: Rust `Resource::from_mcp_value` lossy MCP adapter behavior is
  mirrored for large positive values that exceed i32 but fit i64, negative
  values, exact i64 min/max bounds, unsigned values too large for i64 mapping
  to `None`, and non-integer JSON numbers mapping to `None`.
- Focused validation: `python -m pytest tests/test_protocol_mcp_dynamic_tools.py -k resource_size -q`
  passed on 2026-06-16 with `1 passed, 16 deselected`.

### `src/models.rs` legacy ghost snapshot compatibility

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust legacy `ghost_snapshot` response item compatibility is mirrored: deserializing the old payload shape maps to `ResponseItem::Other` instead of preserving the legacy type or raising. Python now handles this explicit legacy type while leaving the general unknown-type behavior unchanged. The Python parity test directly derives from Rust `deserializes_legacy_ghost_snapshot_as_other`.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k legacy_ghost_snapshot -q` passed on 2026-06-16 with `1 passed, 51 deselected`.

### `src/models.rs` web search call actions

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_models_content.py`
- Status: `complete_slice`
- Evidence: Rust `ResponseItem::WebSearchCall` behavior is mirrored for
  `search`, `open_page`, and `find_in_page` actions, status preservation,
  optional action parsing, and partial in-progress calls that accept `id` on
  input but omit it on serialization when no action is present. This pass fixed
  Python serialization for that partial-call `id` omission.
- Focused validation: `python -m pytest tests/test_protocol_models_content.py -k web_search -q`
  passed on 2026-06-16 with `3 passed, 27 deselected`.

### `src/parse_command.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/parse_command.rs`
- Python module: `pycodex/protocol/parse_command.py`
- Python tests: `tests/test_protocol_parse_command_plan_tool.py`
- Status: `complete_slice`
- Evidence: Rust `ParsedCommand` tagged enum behavior is mirrored for
  `read`, `list_files`, `search`, and `unknown` variants, snake_case type
  tags, `PathBuf` string mapping, optional `query`/`path` field parsing, and
  invalid variant/type boundaries. This pass fixed Python serialization so
  Rust `Option<String>` fields without `skip_serializing_if` are emitted as
  explicit `null` values for `list_files.path`, `search.query`, and
  `search.path`.
- Focused validation: `python -m pytest tests/test_protocol_parse_command_plan_tool.py -k parsed_command -q`
  passed on 2026-06-16 with `4 passed, 4 deselected`.

### `src/items.rs` hook prompt helpers

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/items.rs`
- Python module: `pycodex/protocol/items.py`
- Python tests: `tests/test_protocol_items.py`
- Status: `complete_slice`
- Evidence: The Rust hook prompt fragment/message behavior is mirrored for
  XML serialization, XML parsing, blank hook-run-id rejection, generated IDs
  only when `id` is `None`, app-server mapping for `HookPrompt` turn items,
  multi-fragment round-trips, and legacy single `<hook_prompt hook_run_id=...>`
  parsing. This slice intentionally covers only the hook prompt contract inside
  `items.rs`, not the full turn-item enum.
- Focused validation: `python -m pytest tests/test_protocol_items.py -k hook_prompt -q`
  passed on 2026-06-16 with `6 passed, 27 deselected`.

### `src/openai_models.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/openai_models.rs`
- Python module: `pycodex/protocol/openai_models.py`
- Python tests: `tests/test_protocol_openai_models.py`
- Status: `complete_slice`
- Evidence: Rust model metadata behavior is mirrored for reasoning effort
  wire parsing, input modality defaults/explicit narrowing, personality
  instruction template replacement and placeholder stripping, ModelInfo serde
  defaults, context-window resolution and auto-compact limits, availability
  NUX preservation, model upgrade mapping, fast-mode support from service
  tiers/additional tiers, and request service-tier filtering/default omission.
  This pass fixed Python fast-mode detection so Rust `SPEED_TIER_FAST`
  service-tier IDs are accepted, not only the request-value alias.
- Focused validation: `python -m pytest tests/test_protocol_openai_models.py -q`
  passed on 2026-06-16 with `15 passed`.

### `src/permissions.rs` protected metadata helpers

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: The Rust protected workspace metadata constants and helper
  functions are mirrored for `.git`, `.agents`, and `.codex`,
  `is_protected_metadata_name`, `is_protected_metadata_directory_name`,
  path-like inputs, case-sensitive matching, and `pycodex.protocol` re-exports.
  This slice intentionally covers only the protected-metadata name contract at
  the top of `permissions.rs`, not the full filesystem sandbox policy module.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k protected_metadata -q`
  passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/user_input.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/user_input.rs`
- Python module: `pycodex/protocol/user_input.py`
- Python tests: `tests/test_protocol_ids_tool_user_input.py`
- Status: `complete_slice`
- Evidence: Rust `MAX_USER_INPUT_TEXT_CHARS`, `ByteRange`,
  `TextElement::new`, `map_range`, `set_placeholder`,
  `_placeholder_for_conversion_only`, UTF-8 byte-range placeholder fallback,
  and tagged `UserInput` variants for text, encoded image, local image, skill,
  and mention are mirrored. Serde evidence covers snake_case type tags,
  default empty `text_elements`, optional detail omission, local path string
  conversion, skill/mention round-trips, and invalid variant/field boundaries.
- Focused validation: `python -m pytest tests/test_protocol_ids_tool_user_input.py -k user_input -q`
  passed on 2026-06-16 with `13 passed`.

### `src/plan_tool.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/plan_tool.rs`
- Python module: `pycodex/protocol/plan_tool.py`
- Python tests: `tests/test_protocol_parse_command_plan_tool.py`
- Status: `complete_slice`
- Evidence: Rust `StepStatus` snake_case values, `PlanItemArg` step/status
  fields, `UpdatePlanArgs` required plan vector, default optional explanation,
  optional-field omission on serialization, and `deny_unknown_fields` behavior
  for both structs are mirrored. The plan tool types are also re-exported from
  `pycodex.protocol`, matching the protocol crate public surface.
- Focused validation: `python -m pytest tests/test_protocol_parse_command_plan_tool.py -k plan_tool -q`
  passed on 2026-06-16 with `7 passed`.

### `src/shell_environment.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/shell_environment.rs`
- Python module: `pycodex/protocol/shell_environment.py`
- Python tests: `tests/test_protocol_shell_environment.py`
- Status: `complete_slice`
- Evidence: Rust `populate_env`/`create_env_from_vars` behavior is mirrored for
  all/none/core inheritance, case-insensitive Unix and Windows core variable
  allowlists, default `*KEY*`/`*SECRET*`/`*TOKEN*` excludes, custom excludes,
  `set` overrides, include-only filtering, final `CODEX_THREAD_ID` insertion,
  Windows `PATHEXT` insertion when missing, and invalid input boundaries.
- Focused validation: `python -m pytest tests/test_protocol_shell_environment.py -q`
  passed on 2026-06-16 with `5 passed`.

### `src/mcp_approval_meta.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/mcp_approval_meta.rs`
- Python module: `pycodex/protocol/mcp_approval_meta.py`
- Python tests: `tests/test_protocol_mcp_dynamic_tools.py`
- Status: `complete_slice`
- Evidence: All Rust MCP approval metadata constants are mirrored exactly,
  including approval kind, request type, reviewer, persistence, source,
  connector, and tool metadata keys/values. The constants are also re-exported
  from `pycodex.protocol`, matching the crate-level public protocol surface.
- Focused validation: `python -m pytest tests/test_protocol_mcp_dynamic_tools.py -k mcp_approval_meta -q`
  passed on 2026-06-16 with `1 passed, 16 deselected`.

### `src/dynamic_tools.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/dynamic_tools.rs`
- Python module: `pycodex/protocol/dynamic_tools.py`
- Python tests: `tests/test_protocol_mcp_dynamic_tools.py`
- Status: `complete_slice`
- Evidence: Rust `DynamicToolSpec` camelCase serde shape, optional namespace,
  explicit `deferLoading`, legacy `exposeToContext` inversion, explicit
  `deferLoading` precedence, default `false`, `DynamicToolCallRequest`
  call/turn/tool/arguments fields, default and i64-bounded `startedAtMs`,
  optional namespace, `DynamicToolResponse`, and
  `DynamicToolCallOutputContentItem` tagged `inputText`/`inputImage` variants
  are mirrored. Python additionally records explicit invalid-shape boundaries
  for strings, bools, timestamps, content item tags, and response content.
- Focused validation: `python -m pytest tests/test_protocol_mcp_dynamic_tools.py -k dynamic_tool -q`
  passed on 2026-06-16 with `17 passed`.

### `src/config_types.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/config_types.rs`
- Python module: `pycodex/protocol/config_types.py`
- Python tests: `tests/test_protocol_config_types.py`
- Status: `complete_slice`
- Evidence: Rust enum wire names/defaults for auto-compact token scope,
  reasoning summary/effort, verbosity, sandbox mode, approvals reviewer,
  shell environment inherit policy, Windows sandbox level, personality, web
  search mode/context/location/config, service tier request values, forced login
  method, provider auth defaults/durations, trust level, alt-screen mode,
  collaboration mode kind aliases/visibility/request-user-input permission,
  collaboration mode updates/masks, and `ProfileV2Name` validation are mirrored.
  Rust cfg tests for mask clearing, mode aliases, approvals reviewer legacy
  aliasing, TUI-visible modes, and web-search merge behavior are covered.
- Focused validation: `python -m pytest tests/test_protocol_config_types.py -q`
  passed on 2026-06-16 with `17 passed, 8 subtests passed`.

### `src/auth.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/auth.rs`
- Python module: `pycodex/protocol/auth.py`
- Python tests: `tests/test_protocol_auth_account.py`
- Status: `complete_slice`
- Evidence: Rust `PlanType::{Known, Unknown}` untagged semantics,
  `PlanType::from_raw_value`, `KnownPlan` lowercase/renamed wire names,
  aliases for `hc`, `education`, and `edu`, display names, raw values,
  workspace-account grouping, `RefreshTokenFailedError`, and
  `RefreshTokenFailedReason` are mirrored through the Python semantic model.
  Python additionally records explicit invalid-shape boundaries for plan and
  refresh-token error construction.
- Focused validation: `python -m pytest tests/test_protocol_auth_account.py -k "auth_plan or known_plan or refresh_token" -q`
  passed on 2026-06-16 with `5 passed, 4 deselected`.

### `src/account.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/account.rs`
- Python module: `pycodex/protocol/account.py`
- Python tests: `tests/test_protocol_auth_account.py`
- Status: `complete_slice`
- Evidence: Rust account `PlanType` lowercase and explicitly renamed wire names,
  default `Free`, `is_team_like`, `is_business_like`,
  `is_workspace_account`, conversion from `auth::PlanType`/`KnownPlan`, unknown
  auth-plan fallback, and `ProviderAccount::{ApiKey, Chatgpt, AmazonBedrock}`
  variants are mirrored through the Python semantic model. Python additionally
  records explicit invalid-shape boundaries for parse/conversion and provider
  account construction.
- Focused validation: `python -m pytest tests/test_protocol_auth_account.py -q`
  passed on 2026-06-16 with `9 passed`.

### `src/error.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/error.rs`
- Rust tests: `codex/codex-rs/protocol/src/error_tests.rs`
- Python module: `pycodex/protocol/error.py`
- Python tests: `tests/test_protocol_error.py`
- Status: `complete_slice`
- Evidence: Rust usage-limit formatting across plan/workspace/promo/limit-name
  branches, retry timestamp formatting, unexpected-status JSON extraction,
  Cloudflare blocked simplification, request/cf-ray/identity detail rendering,
  protocol error mapping, retryability, `to_error_event`, and sandbox UI message
  selection/truncation behavior are mirrored. Python additionally keeps explicit
  semantic wrappers for HTTP/status/source variants and sandbox error payloads.
- Focused validation: `python -m pytest tests/test_protocol_error.py -q`
  passed on 2026-06-16 with `7 passed`.

### `src/exec_output.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/exec_output.rs`
- Rust tests: `codex/codex-rs/protocol/src/exec_output_tests.rs`
- Python module: `pycodex/protocol/exec_output.py`
- Python tests: `tests/test_protocol_exec_output.py`
- Status: `complete_slice`
- Evidence: Rust `StreamOutput<T>`, byte-output `from_utf8_lossy`,
  `ExecToolCallOutput::default`, smart byte decoding for UTF-8, CP1251, CP866,
  Windows-1252 punctuation, mixed ASCII/legacy Latin-1, pure Latin-1, invalid
  byte lossy fallback, and the smart-decoding-over-lossy regression are mirrored.
  Python additionally records explicit i32/u32/timedelta/type boundaries.
- Focused validation: `python -m pytest tests/test_protocol_exec_output.py -q`
  passed on 2026-06-16 with `13 passed`.

### `src/approvals.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/approvals.rs`
- Python module: `pycodex/protocol/approvals.py`
- Python tests: `tests/test_protocol_approvals.py`
- Status: `complete_slice`
- Evidence: The Python approvals semantic model mirrors the Rust module's
  current protocol surface for escalation permissions, exec/network policy
  amendments, network approval protocol aliases, guardian enums/actions/events,
  exec approval request events and default decision derivation, elicitation
  request/event/action shapes, apply-patch approval events, and app-server
  approval response compatibility helpers. Rust cfg-test behavior for guardian
  command/execve shapes is covered by round-trip cases, and timestamp/port/list
  boundaries are guarded with explicit Python errors.
- Focused validation: `python -m pytest tests/test_protocol_approvals.py -q`
  passed on 2026-06-16 with `24 passed, 6 subtests passed`.

### `src/request_user_input.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/request_user_input.rs`
- Python module: `pycodex/protocol/request_user_input.py`
- Python tests: `tests/test_protocol_protocol.py`
- Status: `complete_slice`
- Evidence: Rust `RequestUserInputQuestionOption`,
  `RequestUserInputQuestion`, `RequestUserInputArgs`,
  `RequestUserInputAnswer`, `RequestUserInputResponse`, and
  `RequestUserInputEvent` serde shapes are mirrored, including `isOther` and
  `isSecret` renamed/defaulted booleans, optional `options`, answer map shape,
  event `turn_id` default, list/tuple normalization, equality semantics, and
  explicit invalid-shape boundaries.
- Focused validation: `python -m pytest tests/test_protocol_protocol.py -k request_user_input -q`
  passed on 2026-06-16 with `2 passed, 62 deselected`.

### `src/request_permissions.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/request_permissions.rs`
- Python module: `pycodex/protocol/request_permissions.py`
- Python tests: `tests/test_protocol_request_permissions.py`
- Status: `complete_slice`
- Evidence: Rust `PermissionGrantScope` snake_case/default behavior,
  `RequestPermissionProfile::is_empty`, conversion to/from
  `AdditionalPermissionProfile`, `deny_unknown_fields`, request args optional
  reason skip, response default `scope`, `strict_auto_review` false skip,
  event `turn_id` default, optional reason/cwd serialization, and i64
  `started_at_ms` boundary are mirrored. Python additionally retains the
  app-server camelCase compatibility adapter without changing the internal Rust
  request-permissions shape.
- Focused validation: `python -m pytest tests/test_protocol_request_permissions.py -q`
  passed on 2026-06-16 with `8 passed`.

### `src/network_policy.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/network_policy.rs`
- Python module: `pycodex/protocol/network_policy.py`
- Python tests: `tests/test_protocol_small_modules.py`
- Status: `complete_slice`
- Evidence: Rust `NetworkPolicyDecisionPayload` camelCase serde shape,
  `decision`, `source`, optional `protocol`, `host`, `reason`, and `port`
  fields, `is_ask_from_decider`, network decision/source wire names, protocol
  normalization, and `u16` port boundaries are mirrored through the Python
  semantic model. Python also records explicit invalid-shape errors for decoded
  payloads.
- Focused validation: `python -m pytest tests/test_protocol_small_modules.py -k network_policy -q`
  passed on 2026-06-16 with `1 passed, 4 deselected`.

### `src/memory_citation.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/memory_citation.rs`
- Python module: `pycodex/protocol/memory_citation.py`
- Python tests: `tests/test_protocol_small_modules.py`
- Status: `complete_slice`
- Evidence: Rust `MemoryCitation` default/list shape,
  `MemoryCitationEntry` fields, camelCase serde keys (`lineStart`,
  `lineEnd`, `rolloutIds`), equality semantics, agent event embedding, and u32
  line-number boundaries are mirrored through the Python semantic model.
  Python also records explicit decoded-shape errors for invalid mappings and
  field types.
- Focused validation: `python -m pytest tests/test_protocol_small_modules.py -k memory_citation -q`
  passed on 2026-06-16 with `3 passed, 2 deselected`.

### `src/session_id.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/session_id.rs`
- Python module: `pycodex/protocol/ids.py`
- Python tests: `tests/test_protocol_ids_tool_user_input.py`
- Status: `complete_slice`
- Evidence: Rust `SessionId::new`, `Default`, `from_string`,
  `TryFrom<&str>`, `TryFrom<String>`, `From<SessionId> for String`,
  `From<ThreadId> for SessionId`, `From<SessionId> for ThreadId`, Display,
  serde string shape, equality, and non-zero default UUID behavior are mirrored
  through the Python semantic model. Python records explicit type-boundary
  errors for non-UUID construction, non-string parsing, and invalid thread-id
  conversion input.
- Focused validation: `python -m pytest tests/test_protocol_ids_tool_user_input.py -k session_id -q`
  passed on 2026-06-16 with `1 passed, 12 deselected`.

### `src/thread_id.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/thread_id.rs`
- Python module: `pycodex/protocol/ids.py`
- Python tests: `tests/test_protocol_ids_tool_user_input.py`
- Status: `complete_slice`
- Evidence: Rust `ThreadId::new`, `Default`, `from_string`,
  `TryFrom<&str>`, `TryFrom<String>`, `From<ThreadId> for String`,
  Display, serde string shape, equality, and non-zero default UUID behavior are
  mirrored through the Python semantic model. Python records explicit
  type-boundary errors for non-UUID construction and non-string parsing.
- Focused validation: `python -m pytest tests/test_protocol_ids_tool_user_input.py -k thread_id -q`
  passed on 2026-06-16 with `2 passed, 11 deselected`.

### `src/tool_name.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/tool_name.rs`
- Python module: `pycodex/protocol/tool_name.py`
- Python tests: `tests/test_protocol_ids_tool_user_input.py`
- Status: `complete_slice`
- Evidence: Rust `ToolName::new`, `plain`, `namespaced`,
  `From<String>`, `From<&str>`, Display namespace concatenation, serde-shaped
  object mapping, equality/hash dataclass semantics, and tuple-style ordering
  are mirrored. Python also records explicit type-boundary errors for invalid
  decoded shapes.
- Focused validation: `python -m pytest tests/test_protocol_ids_tool_user_input.py -k tool_name -q`
  passed on 2026-06-16 with `4 passed, 9 deselected`.

### `src/agent_path.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/agent_path.rs`
- Python module: `pycodex/protocol/agent_path.py`
- Python tests: `tests/test_protocol_agent_path.py`
- Status: `complete_slice`
- Evidence: Rust root/morpheus constructors, `as_str`, `name`, `is_root`,
  `join`, absolute/relative `resolve`, reserved name rejection, absolute path
  validation, trailing slash rejection, and relative reference validation are
  mirrored. Python also records explicit type-boundary errors for non-string
  inputs.
- Focused validation: `python -m pytest tests/test_protocol_agent_path.py -q`
  passed on 2026-06-16 with `6 passed, 11 subtests passed`.

### `src/num_format.rs`

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/num_format.rs`
- Python module: `pycodex/protocol/num_format.py`
- Python tests: `tests/test_protocol_num_format.py`
- Status: `complete_slice`
- Evidence: Rust `kmg` test examples are mirrored, including K/M/G threshold
  rounding, grouping above 1000G, negative SI clamping to zero, and deterministic
  en-US-style separator fallback. Python additionally documents the i64 boundary
  accepted by the Rust API.
- Focused validation: `python -m pytest tests/test_protocol_num_format.py -q`
  passed on 2026-06-16 with `4 passed, 14 subtests passed`.

### `src/models.rs` permission profile legacy sandbox conversion surface

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `PermissionProfile` legacy sandbox-policy conversion surface is mirrored for danger-full-access -> disabled, external sandbox -> external with network policy, read-only legacy policy -> managed read-only filesystem with enabled network, and workspace-write-for-cwd preserving writable roots/network/exclusion knobs. Existing Python parity coverage exercises this public model conversion boundary.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_profile_from_legacy_sandbox_policy -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` filesystem permissions legacy read/write roots

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemPermissions::from_read_write_roots`, `explicit_path_entries`, and `legacy_read_write_roots` behavior is mirrored for explicit read/write roots, empty-root omission as `None`, legacy `read`/`write` mapping serialization, and rejection of non-legacy shapes such as glob entries.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k "file_system_permissions_legacy_read_write_roots or file_system_permissions_reject_non_legacy_shapes" -q` passed on 2026-06-16 with `2 passed, 46 deselected`.

### `src/models.rs` additional permission profile mapping

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `AdditionalPermissionProfile` derives serde over optional `network` and `file_system` fields. Python mirrors the mapping shape, roundtrips nested `NetworkPermissions` and `FileSystemPermissions`, and rejects invalid nested non-mapping payloads instead of silently coercing them.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k additional_permission_profile_mapping_roundtrips -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` permission profile project roots materialization

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `PermissionProfile::materialize_project_roots_with_workspace_roots` materializes managed filesystem project-root placeholders through the runtime filesystem policy and preserves network policy, while disabled and external profiles are returned unchanged. Python mirrors those branch semantics.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_profile_materializes_project_roots -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/models.rs` permission profile built-in constructors and enforcement

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `PermissionProfile::read_only`, `PermissionProfile::workspace_write`, disabled/external variants, and built-in profile id constants are mirrored. Python preserves managed/disabled/external enforcement derivation and the corresponding filesystem/network sandbox policy surfaces.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_profile_builtin_constructors_and_enforcement -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` filesystem access mode helpers

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemAccessMode` lower-case serde with legacy `none` alias, `can_read`, `can_write`, and `file_system_access_mode_orders_by_conflict_precedence` semantics are mirrored. Python preserves `Read < Write < Deny` conflict precedence and rejects non-string access parsing.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k network_and_filesystem_access_helpers -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` legacy bridge explicit deny preservation

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `legacy_bridge_preserves_explicit_deny_entries` confirms `FileSystemSandboxPolicy::from_legacy_sandbox_policy_preserving_deny_entries` carries explicit deny entries from an existing restricted policy into the rebuilt policy. Python mirrors that preservation and keeps the policy's `glob_scan_max_depth` metadata intact.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k from_legacy_preserving_deny_entries -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` read-deny matcher exact roots and globs

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `ReadDenyMatcher` tests for exact path descendants, literal deny patterns, ordinary globs, separator-bounded glob segments, and globstar matches are mirrored by Python coverage for exact deny roots, descendants, matching/unmatched glob patterns, invalid literal-glob fallback, and root/nested `.env` globstar matches.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k read_deny_matcher_exact_roots_and_globs -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` read-deny matcher project-root globs

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `ReadDenyMatcher::build` consumes `FileSystemSandboxPolicy::get_unreadable_globs_with_cwd(cwd)`, whose project-root glob contract resolves symbolic project-root patterns before read-deny matching. Python mirrors `codex-project-roots://` parsing in `get_unreadable_globs_with_cwd` and verifies that root and nested `.env` files are denied while unrelated files are not.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k read_deny_matcher_resolves_project_root_globs -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` project-roots workspace materialization

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `materialize_project_roots_with_workspace_roots_expands_exact_and_glob_entries` is mirrored: symbolic project-root write entries expand once per workspace root, project-root subpaths such as `.git` are joined under each root, project-root glob patterns are resolved under each root, and unrelated literal path entries are preserved.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k materialize_project_roots_with_workspace_roots_expands_symbolic_entries -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` project-roots cwd materialization

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `materialize_project_roots_with_cwd_expands_symbolic_glob_entries` is mirrored and extended at the Python parity boundary for exact project-root entries and project-root subpaths. Absolute cwd expands symbolic entries to concrete paths/globs; relative cwd keeps the policy symbolic.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k materialize_project_roots_with_cwd_keeps_relative_cwd_symbolic -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` project-roots preserve-symbolic materialization

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxPolicy::with_materialized_project_roots_for_workspace_roots` clones and materializes project roots, then appends only non-duplicate concrete entries back to the original policy. Python mirrors this by preserving symbolic entries and avoiding duplicate materialized workspace-root entries.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k with_materialized_project_roots_preserves_symbolic_entries -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` additional readable roots

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxPolicy::with_additional_readable_roots` returns unchanged when full-disk read access already exists, skips paths already effectively readable through cwd/project-root resolution, and appends missing explicit read roots. Python mirrors this branch behavior.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k with_additional_roots_skips_existing_effective_access -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` additional writable roots

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxPolicy::with_additional_writable_roots` skips paths already effectively writable through cwd/project-root resolution and appends missing explicit write roots. Python mirrors this branch behavior.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k with_additional_roots_skips_existing_effective_access -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` legacy workspace writable roots exact-root behavior

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxPolicy::with_additional_legacy_workspace_writable_roots` returns unchanged for non-restricted policies, adds exact explicit writable roots using legacy `WorkspaceWrite` behavior even when symbolic project-root write already exists, and avoids duplicate exact-root write entries on repeated application. Python mirrors those helper semantics.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k with_additional_legacy_workspace_writable_roots_adds_exact_root -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` preserve deny-read restrictions

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `preserving_deny_entries_keeps_unrestricted_policy_enforceable` confirms `FileSystemSandboxPolicy::preserve_deny_read_restrictions_from` converts an unrestricted replacement into a restricted root-write policy when existing deny entries must be preserved, appends deny-read entries, and carries `glob_scan_max_depth` metadata. Python mirrors that helper behavior.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k preserve_deny_read_restrictions_from_existing_policy -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` semantic signature ignores entry order

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxPolicy::is_semantically_equivalent_to` compares `semantic_signature(cwd)` and the signature sorts resolved roots, making incidental entry ordering irrelevant. Python mirrors this behavior for reordered policies with the same effective filesystem access model.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k semantic_signature_ignores_entry_order -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` semantic signature sorting

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `semantic_signature(cwd)` builds deterministic signatures from sorted readable roots, writable roots, unreadable roots, and unreadable globs. Python mirrors stable ordering for writable roots and unreadable globs and collapses duplicate glob entries for deterministic comparison.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k semantic_signature_sorts_roots_and_globs -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` direct runtime enforcement classification

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxPolicy::needs_direct_runtime_enforcement` returns false for non-restricted policies, classifies unbridgeable legacy projections and protected metadata-name cases as requiring direct runtime enforcement, and otherwise compares semantic signatures against the legacy runtime projection. Python mirrors this classification boundary.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k direct_runtime_enforcement_detects_unbridgeable_and_metadata_cases -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` semantic writable-root detail normalization

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `sorted_writable_roots` sorts writable-root `read_only_subpaths`, sorts and deduplicates `protected_metadata_names`, and then sorts writable roots by root path. Python mirrors deterministic writable-root details, including default `.codex` read-only metadata and sorted protected metadata names.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k semantic_signature_normalizes_writable_root_details -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` semantic platform-default flag

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxPolicy::include_platform_defaults` returns true for restricted, non-full-read policies that include a readable `FileSystemSpecialPath::Minimal` entry, and `semantic_signature(cwd)` carries that flag. Python mirrors the same condition and signature field.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k semantic_signature_tracks_platform_defaults_flag -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/protocol.rs` legacy sandbox policy helpers

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/protocol.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `SandboxPolicy` helper semantics are mirrored for `DangerFullAccess`, `ReadOnly`, `ExternalSandbox`, and `WorkspaceWrite`: full-disk write access, full-network access, constructor defaults, and invalid field/type boundaries. Rust tests `external_sandbox_reports_full_access_flags` and `read_only_reports_network_access_flags` anchor the core flag behavior.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k legacy_sandbox_policy_helpers -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/protocol.rs` legacy sandbox policy mapping

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/protocol.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `SandboxPolicy` serde uses a kebab-case internal `type` tag and serde defaults for read-only, external-sandbox, and workspace-write variants. Python mirrors danger-full-access, read-only, external-sandbox, and workspace-write mapping roundtrips, including empty `writable_roots` omission and defaulted workspace flags.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k legacy_sandbox_policy_mapping_matches_upstream_contract -q` passed on 2026-06-16 with `1 passed, 47 deselected, 7 subtests passed`.

### `src/protocol.rs` writable root path writability

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/protocol.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `WritableRoot::is_path_writable` rejects paths outside the root, paths under configured `read_only_subpaths`, and paths whose first component under the root matches `protected_metadata_names`. Python mirrors that behavior and allows the root itself plus nested metadata-like names below ordinary subdirectories.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k writable_root_method_matches_upstream_contract -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` writable-root metadata protections

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxPolicy::get_writable_roots_with_cwd` computes `protected_metadata_names` for each writable root and passes them into `WritableRoot`. Python mirrors that derivation so `.git`, `.agents`, and `.codex` top-level metadata paths under writable roots are not writable, while ordinary source paths remain writable.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k writable_roots_include_metadata_name_protections -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` readable and unreadable roots cwd resolution

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxPolicy::get_readable_roots_with_cwd` resolves entries against cwd, keeps entries that can read and remain effectively readable, and deduplicates normalized absolute paths. Python mirrors this behavior and verifies that a specific readable path under a denied root is reported as readable while unreadable roots are empty because the more specific read entry overrides the root deny for that path.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k readable_unreadable_roots_resolve_with_cwd -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` workspace-write constructor entries

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxPolicy::workspace_write` constructs a restricted policy containing root read, symbolic project-roots write, optional `/tmp` and `$TMPDIR` writes, explicit writable roots, and default project metadata read carveouts for `.git`, `.agents`, and `.codex`. Python mirrors those entries, exclusion knobs, and type boundaries.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k "workspace_write_entries or workspace_write_exclusion_knobs" -q` passed on 2026-06-16 with `2 passed, 46 deselected`.

### `src/permissions.rs` filesystem special path mapping

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSpecialPath` serde maps legacy `current_working_directory` to `project_roots`, preserves optional project-root subpaths, and keeps future unknown special-path tokens representable. Python mirrors the alias, project-root subpath mapping, unknown-token boundaries, project-root glob prefix helper, and invalid field type errors.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k filesystem_path_mapping_roundtrips_and_accepts_legacy_alias -q` passed on 2026-06-16 with `1 passed, 47 deselected`.

### `src/permissions.rs` filesystem path mapping

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemPath` serde uses a snake_case internal `type` tag with `path`, `glob_pattern`, and `special` variants. Python mirrors those tagged shapes, preserves mapping roundtrips and constructor equivalence, and rejects invalid type/field combinations without fallback.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k filesystem_path_mapping_roundtrips_and_accepts_legacy_alias -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/permissions.rs` filesystem sandbox entry mapping

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxEntry` serializes as a struct containing `path: FileSystemPath` and `access: FileSystemAccessMode`. Python mirrors that mapping contract, keeps the legacy `access: "none"` alias mapped to deny, and rejects non-`FileSystemPath` or non-`FileSystemAccessMode` constructor values without fallback.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k filesystem_path_mapping_roundtrips_and_accepts_legacy_alias -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/models.rs` sandbox enforcement legacy mapping

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `SandboxEnforcement::from_legacy_sandbox_policy` maps `SandboxPolicy::DangerFullAccess` to `Disabled`, `ExternalSandbox` to `External`, and `ReadOnly` or `WorkspaceWrite` to `Managed`. Python mirrors that classification exactly.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k sandbox_enforcement_from_legacy_policy -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/permissions.rs` legacy workspace symbolic project-root projection

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxPolicy::from` projects legacy `SandboxPolicy::WorkspaceWrite` through `workspace_write`, preserving the symbolic project-roots entry instead of resolving it eagerly. Python mirrors that projection for `FileSystemSandboxPolicy.from_legacy_sandbox_policy`.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k legacy_workspace_projection_preserves_symbolic_project_root -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/permissions.rs` unknown special legacy bridge ignore

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust legacy bridge behavior ignores `FileSystemSpecialPath::Unknown` entries when projecting split filesystem policies back to legacy `SandboxPolicy`. Python mirrors this by not converting unknown special entries into legacy roots or permissions.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k unknown_special_paths_are_ignored_by_legacy_bridge -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/permissions.rs` legacy split-policy roundtrip

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxPolicy::from_legacy_sandbox_policy_for_cwd` and `to_legacy_sandbox_policy` define the split/legacy bridge for danger-full-access, external-sandbox, read-only, and workspace-write policies. Python mirrors the roundtrip identity for policy type, disk/network capability flags, and workspace-write roots/exclusion knobs.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k legacy_policy_roundtrips_through_split_policy -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/permissions.rs` legacy bridge rejects non-workspace writes

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxPolicy::to_legacy_sandbox_policy` returns an error when a split filesystem policy requests writes that cannot be represented by legacy workspace-write roots for the provided cwd. Python mirrors this by raising instead of silently widening, dropping, or translating unsupported write roots.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k to_legacy_rejects_non_workspace_write_roots -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/models.rs` permission profile legacy sandbox conversion

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `PermissionProfile::from_legacy_sandbox_policy` composes `SandboxEnforcement::from_legacy_sandbox_policy`, `FileSystemSandboxPolicy::from`, and `NetworkSandboxPolicy::from` to produce disabled, external, or managed permission profiles. Python mirrors this conversion, including read-only network preservation and workspace-write cwd roundtrip behavior.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_profile_from_legacy_sandbox_policy -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/models.rs` permission profile legacy preset defaults

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `permission_profile_presets_match_legacy_defaults` asserts `PermissionProfile::read_only()` equals conversion from the legacy read-only policy and `PermissionProfile::workspace_write()` equals conversion from the legacy workspace-write policy. Python mirrors those built-in preset defaults.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_profile_presets_match_legacy_defaults -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/models.rs` permission profile project-root materialization

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `PermissionProfile::materialize_project_roots_with_workspace_roots` delegates managed profiles to filesystem policy materialization while returning disabled and external profiles unchanged. Python mirrors that branch behavior and preserves the network side of managed profiles.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_profile_materializes_project_roots -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/models.rs` permission profile to-legacy bridge

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `PermissionProfile::to_legacy_sandbox_policy` returns `DangerFullAccess` for disabled profiles, `ExternalSandbox` for external profiles with their network policy, and delegates managed profiles through split filesystem/network legacy projection. Python mirrors those branches.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_profile_to_legacy_sandbox_policy -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/models.rs` permission profile canonical mapping

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `PermissionProfile` serializes as a snake_case internally tagged enum with `managed`, `disabled`, and `external` variants, and tagged deserialization is routed through `TaggedPermissionProfile`. Python mirrors the canonical tagged mapping roundtrip and rejects invalid network fields or unknown managed fields without fallback.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_profile_mapping_roundtrips_canonical_shapes -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/models.rs` permission profile runtime conversion

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `PermissionProfile::from_runtime_permissions` derives enforcement from filesystem sandbox kind, and `from_runtime_permissions_with_enforcement` maps external filesystem policies to external profiles, disabled unrestricted policies to disabled profiles, and restricted/unrestricted managed policies to managed profiles while preserving network and filesystem details. Python mirrors those branches.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_profile_from_runtime_permissions -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/models.rs` active permission profile identity

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `ActivePermissionProfile` stores stable profile identity with `id` and optional `extends`, skips serializing `None` extends, and `read_only()` returns the built-in `:read-only` id. Python mirrors those constructors, mapping shape, omission behavior, and id/extends type validation.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k active_permission_profile_read_only_identity -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/models.rs` permission profile built-in constructors

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `PermissionProfile::read_only`, `workspace_write`, disabled/external variants, and `enforcement`/`file_system_sandbox_policy`/`network_sandbox_policy` define the built-in profile runtime semantics. Python mirrors built-in ids, constructor output, managed/disabled/external enforcement, filesystem policy accessors, and network policy accessors.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_profile_builtin_constructors_and_enforcement -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/models.rs` managed filesystem runtime policy conversion

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `ManagedFileSystemPermissions::from_sandbox_policy` converts restricted sandbox policies to `Restricted`, unrestricted policies to `Unrestricted`, and treats external filesystem policies as unreachable because they belong to `PermissionProfile::External`. `to_sandbox_policy` reverses restricted/unrestricted managed permissions back to runtime filesystem policies. Python mirrors these conversions and rejects external policies explicitly.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k managed_file_system_permissions_roundtrip_runtime_policy -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/models.rs` additional permission profile mapping

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `AdditionalPermissionProfile` is a serde struct with optional `network: NetworkPermissions` and `file_system: FileSystemPermissions` overlay fields. Python mirrors the optional mapping roundtrip and rejects non-mapping nested network or filesystem payloads instead of silently falling back.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k additional_permission_profile_mapping_roundtrips -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/models.rs` permission profile legacy rollout shape

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `PermissionProfileDe` accepts both tagged `TaggedPermissionProfile` and untagged `LegacyPermissionProfile`; the legacy shape carries optional `network` and `file_system` overlays and converts through runtime permission construction. Python mirrors this legacy rollout compatibility and preserves filesystem entries plus `glob_scan_max_depth`.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_profile_deserializes_legacy_rollout_shape -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/models.rs` permission overlay empty helpers

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/models.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `NetworkPermissions::is_empty` treats missing `enabled` as empty, while `AdditionalPermissionProfile::is_empty` only returns true when both optional overlay fields are absent. Python mirrors that distinction so a present-but-empty nested permission object is still an explicit overlay.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k permission_overlay_empty_helpers -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/permissions.rs` full disk write narrowing detection

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `FileSystemSandboxPolicy::has_full_disk_write_access` reports unrestricted/external and root-write-only policies as full disk write, but `root_write_with_read_only_child_is_not_full_disk_write` proves root write plus a read-only child is a real narrowing entry that must keep child read access, require direct runtime enforcement, and reject lossy legacy projection. Python mirrors those branches.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k full_disk_write_detects_real_narrowing_entries -q` passed on 2026-06-16 with `1 passed, 47 deselected`.
### `src/permissions.rs` duplicate root deny full-disk-write guard

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `duplicate_root_deny_prevents_full_disk_write_access` proves a restricted split filesystem policy containing root write plus a duplicate root deny must not be treated as full-disk writable, and root access resolves to `Deny`. Python mirrors the same conflict-precedence branch.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k duplicate_root_deny_prevents_full_disk_write_access -q` passed on 2026-06-16 with `1 passed, 48 deselected`.
### `src/permissions.rs` same-specificity write override full-disk-write guard

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `same_specificity_write_override_keeps_full_disk_write_access` proves a read carveout is not a real full-disk-write narrowing entry when a later same-specificity write rule overrides it; the path resolves to `Write` and the policy remains full-disk writable. Python mirrors the same most-specific/latest-rule conflict behavior.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k same_specificity_write_override_keeps_full_disk_write_access -q` passed on 2026-06-16 with `1 passed, 49 deselected`.
### `src/permissions.rs` explicit `.codex` write metadata override

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `writable_roots_skip_default_dot_codex_when_explicit_user_rule_exists` proves an explicit user write rule for `.codex` wins over default project metadata protection: the workspace writable root does not retain `.codex` in `protected_metadata_names`, does not include the explicit `.codex` path in `read_only_subpaths`, and permits writing `.codex/config.toml`. Python mirrors the same branch.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k writable_roots_skip_default_dot_codex_when_explicit_user_rule_exists -q` passed on 2026-06-16 with `1 passed, 50 deselected`.
### `src/permissions.rs` split-only nested carveouts direct-enforcement guard

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `split_only_nested_carveouts_need_direct_runtime_enforcement` proves a symbolic project-roots write policy with a nested read-only carveout cannot be fully represented by the legacy sandbox projection and must stay in direct runtime enforcement. Python mirrors this classification branch.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k split_only_nested_carveouts_need_direct_runtime_enforcement -q` passed on 2026-06-16 with `1 passed, 51 deselected`.
### `src/permissions.rs` legacy projection entry-order direct-enforcement guard

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `legacy_projection_runtime_enforcement_ignores_entry_order` proves direct-runtime-enforcement classification depends on normalized filesystem semantics rather than incidental entry order. Python mirrors this by reversing a legacy workspace-write projection, confirming semantic equivalence, and comparing `needs_direct_runtime_enforcement` results.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k legacy_projection_runtime_enforcement_ignores_entry_order -q` passed on 2026-06-16 with `1 passed, 52 deselected`.
### `src/permissions.rs` legacy workspace projection relative-cwd guard

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `legacy_workspace_write_projection_accepts_relative_cwd` proves `FileSystemSandboxPolicy::from_legacy_sandbox_policy_for_cwd` accepts a relative cwd for legacy workspace-write policies and preserves the symbolic project-roots workspace-write shape rather than requiring absolute cwd materialization. Python mirrors that behavior.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k legacy_workspace_write_projection_accepts_relative_cwd -q` passed on 2026-06-16 with `1 passed, 53 deselected`.
### `src/permissions.rs` legacy additional writable-root metadata protection

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `with_additional_legacy_workspace_writable_roots_protects_metadata` proves adding a legacy workspace writable root must also preserve read-only protections for existing top-level `.git`, `.agents`, and `.codex` metadata paths below that root. Python mirrors this behavior through `with_additional_legacy_workspace_writable_roots` and default metadata carveout helpers.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k with_additional_legacy_workspace_writable_roots_protects_metadata -q` passed on 2026-06-16 with `1 passed, 54 deselected`.
### `src/permissions.rs` proactive missing `.codex` metadata protection

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `writable_roots_proactively_protect_missing_dot_codex` proves workspace writable roots proactively include `.codex` in read-only subpaths even when the directory does not exist yet, so future `.codex/config.toml` writes stay blocked. Python mirrors this behavior.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k writable_roots_proactively_protect_missing_dot_codex -q` passed on 2026-06-16 with `1 passed, 55 deselected`.
### `src/permissions.rs` missing symbolic metadata direct-enforcement guard

- Rust owner: `codex-protocol`
- Rust module: `codex/codex-rs/protocol/src/permissions.rs`
- Python module: `pycodex/protocol/models.py`
- Python tests: `tests/test_protocol_permission_models.py`
- Status: `complete_slice`
- Evidence: Rust `missing_symbolic_metadata_carveouts_need_direct_runtime_enforcement` proves legacy workspace-write profile projection and legacy runtime projection both require direct runtime enforcement when symbolic `.git`/`.agents` metadata protections or metadata-name protections cannot be represented by the legacy writable-root contract. Python mirrors both branches, including the internal legacy runtime helper.
- Focused validation: `python -m pytest tests/test_protocol_permission_models.py -k missing_symbolic_metadata_carveouts_need_direct_runtime_enforcement -q` passed on 2026-06-16 with `1 passed, 56 deselected`.
