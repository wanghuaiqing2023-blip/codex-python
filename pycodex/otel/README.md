# pycodex.otel

Rust crate: `codex-otel`

Rust anchor: `codex/codex-rs/otel`

This package mirrors the public crate interface exported from
`otel/src/lib.rs`.  Telemetry config, metric names, W3C trace-context
validation, and timer shapes are ported; OpenTelemetry exporter startup is an
explicit disabled/unported boundary.
