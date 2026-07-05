# schema_fixtures.rs Alignment Status

Rust module: `codex/codex-rs/app-server-protocol/src/schema_fixtures.rs`

Python module: `pycodex/app_server_protocol/schema_fixtures.py`

Status: complete for the module-scoped schema fixture I/O and normalization contract.

## Covered

- `SchemaFixtureOptions` with `experimental_api`.
- Reading full schema fixture trees under `typescript/` and `json/`, plus
  labeled subtrees.
- Recursive file collection with deterministic relative-path ordering.
- JSON fixture parsing, canonical object-key ordering, and stable sorting for
  arrays of scalars, `$ref` objects, or titled objects.
- TypeScript fixture normalization for CRLF/CR line endings and generated
  header removal.
- Empty-output-directory preparation and write fixture entrypoints with
  injected generator callbacks.

## Intentional Adaptations

- Rust calls crate-level `generate_ts_with_options` and
  `generate_json_with_experimental`; Python leaves actual schema generation to
  the future `export.rs` port and requires explicit generator callbacks.
- TypeScript fixture generation for tests is exposed but raises
  `NotImplementedError` until the export/type visitor boundary is ported.

## Validation

- `python -m py_compile pycodex/app_server_protocol/schema_fixtures.py pycodex/app_server_protocol/__init__.py`
- Focused smoke covered JSON canonicalization, schema array sort keys,
  TypeScript line/header normalization, recursive tree reading, empty-dir
  preparation, injected generator callbacks, and package exports.

Full crate tests remain deferred until the `codex-app-server-protocol`
functional code surface is complete.
