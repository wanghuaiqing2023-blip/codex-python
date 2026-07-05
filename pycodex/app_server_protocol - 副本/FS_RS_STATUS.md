# app-server-protocol `protocol/v2/fs.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/fs.rs`

Python target: `pycodex/app_server_protocol/fs.py`

Status: implemented module contract.

## Covered Rust items

- `FsReadFileParams`
- `FsReadFileResponse`
- `FsWriteFileParams`
- `FsWriteFileResponse`
- `FsCreateDirectoryParams`
- `FsCreateDirectoryResponse`
- `FsGetMetadataParams`
- `FsGetMetadataResponse`
- `FsReadDirectoryParams`
- `FsReadDirectoryEntry`
- `FsReadDirectoryResponse`
- `FsRemoveParams`
- `FsRemoveResponse`
- `FsCopyParams`
- `FsCopyResponse`
- `FsWatchParams`
- `FsWatchResponse`
- `FsUnwatchParams`
- `FsUnwatchResponse`
- `FsChangedNotification`

## Notes

- Path fields enforce the Rust `AbsolutePathBuf` contract by accepting only
  absolute path strings or `Path` values.
- Payloads accept Rust serde camelCase keys and emit Rust wire names through
  `to_camel_mapping()`.
- Empty response structs serialize to `{}`.
- `FsCopyParams.recursive` defaults to `False` and is omitted from serialized
  mappings unless true, matching Rust's `skip_serializing_if`.

## Validation

- Compile check: `python -m py_compile pycodex/app_server_protocol/fs.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: parsed read/write file, empty responses, create directory,
  metadata, directory entries, remove, copy defaults, watch/unwatch, and change
  notifications.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
