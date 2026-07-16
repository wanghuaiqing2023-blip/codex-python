# pycodex.extension_api

Rust crate: `codex-extension-api`

Rust anchor: `codex/codex-rs/ext/extension-api`

This package mirrors the public crate interface exported from
`ext/extension-api/src/lib.rs`. The Python modules preserve the Rust ownership
coordinates: `state` owns scoped extension data, `registry` owns contributor
registration, `contributors` owns lifecycle/tool/context contracts, and
`capabilities` owns host-provided sinks and injectors.
