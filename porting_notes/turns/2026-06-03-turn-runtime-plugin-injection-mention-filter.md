# 2026-06-03 Turn Runtime: Plugin injection + skill mention filtering parity

## 目标
- 让 `exec -> context -> model request -> stream handling -> tool dispatch -> final answer` 的核心路径内，插件提及和技能辅助注入行为更贴近 Rust 实现。

## 变更
- 修改 `pycodex/core/turn_runtime.py`:
  - `_build_plugin_injections`:
    - 除 `display_name` 匹配外，补充基于 `mcp_server_names` 与 `app_connector_ids` 的匹配；
    - 插件可见 apps 使用 connector 显示名渲染，保持与 Rust `connector_display_label` 语义一致。
  - `_response_item_skill_text`:
    - 只从 `type == "message"` 且 `content` 中 `type == "input_text"` 的条目读取文本；
    - 避免将其他类型条目误参与显式 app 提及推断。

## 依据
- 上游 Rust 参考：
  - `codex/codex-rs/core/src/plugins/injection.rs`
  - `codex/codex-rs/core/src/session/turn.rs` 中 `collect_explicit_app_ids_from_skill_items` 的 `ContentItem::InputText` 遍历语义。

## 风险与边界
- 这是核心路径内的兼容对齐；未扩展 MCP/插件生态的发现与安装子系统。
- 本轮未新增测试执行（按当前任务约束）。建议在有空窗期补一条回归测试覆盖 `SkillInstructions`/`PluginInstructions` 文本注入里的 app 提及行为。
