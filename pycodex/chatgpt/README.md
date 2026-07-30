# codex-chatgpt

This package mirrors `codex/codex-rs/chatgpt` at baseline
`1c7832ffa37a3ab56f601497c00bfce120370bf9`.

The module ownership is one-to-one: `apply_command`, the private
`chatgpt_client`, `connectors`, `get_task`, and `workspace_settings`. HTTP,
authentication, connector directory, plugin, and Git behavior remain owned by
their corresponding dependency packages and are composed here as in Rust.
