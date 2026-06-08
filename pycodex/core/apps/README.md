# pycodex.core.apps

Rust counterpart:

```text
Rust crate: codex-core
Rust module path: codex/codex-rs/core/src/apps
```

`codex-core::apps` is a small module namespace. In the current Rust source,
`mod.rs` declares the `render` module for tests, and `render.rs` owns the
`render_apps_section` helper. Python keeps the core crate coordinate here while
delegating the shared render helper implementation to `pycodex.core.plugins.render`.
