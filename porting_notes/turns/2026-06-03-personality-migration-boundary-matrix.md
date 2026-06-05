# 人格迁移（personality_migration）边界行为矩阵

## 关键输入维度
- `marker`：是否已存在 `.personality_migration`
- `override_profile`：是否传入、是否有效、是否可解析
- 配置来源：内存 `config_toml`，或磁盘 `config.toml`（当 `config_toml=None`）
- 是否有顶层 `personality`
- 是否存在 `profiles` 与可命中的 profile 条目
- 是否存在可用会话记录（active/archived）

## 已覆盖分支（含测试）

| 场景 | 预期状态 | 验证测试 |
| --- | --- | --- |
| marker 已存在且有 override_profile | `SKIPPED_MARKER` | `test_marker_takes_precedence_even_with_override_profile` |
| marker 已存在且不传 `config_toml` | `SKIPPED_MARKER`，不改写配置 | `test_marker_takes_precedence_even_without_config_argument` |
| marker 已存在 | `SKIPPED_MARKER`，不改写配置 | `test_skips_when_marker_exists` |
| 顶层 `personality` 已存在 | `SKIPPED_EXPLICIT_PERSONALITY`，不重写 personality | `test_skips_when_personality_explicit` |
| 顶层 `personality` 已存在 + override_profile 存在 | `SKIPPED_EXPLICIT_PERSONALITY`，保持顶层 personality 不变 | `test_top_level_personality_blocks_even_with_override_profile` |
| 空字符串 `override_profile` | 等价于未传递 override，按顶层/主逻辑处理（此例有会话且仅 profile 命中）| `test_blank_override_profile_uses_top_level_profile_behavior` |
| `config_toml=None` 且磁盘顶层 personality 存在 + override_profile 存在 | `SKIPPED_EXPLICIT_PERSONALITY`（保持磁盘顶层配置不变） | `test_override_profile_from_disk_config_respects_disk_top_level_personality` |
| 空字符串 `override_profile` + 顶层 personality 显式存在 | `SKIPPED_EXPLICIT_PERSONALITY`，保持顶层 personality 不变 | `test_top_level_personality_blocks_blank_override_profile` |
| `model_provider` 显式配置 + 有会话 | `APPLIED`（模型提供者配置不阻断迁移） | `test_model_provider_setting_does_not_block_migration_when_sessions_exist` |
| `model_provider` 显式配置 + 无会话 | `SKIPPED_NO_SESSIONS` | `test_model_provider_setting_respects_no_sessions_path` |
| 不存在 override profile + `model_provider` 存在 + 有会话 | `APPLIED` | `test_missing_override_profile_respects_model_provider_with_sessions` |
| 不存在 override profile + `model_provider` 存在 + 无会话 | `SKIPPED_NO_SESSIONS` | `test_missing_override_profile_respects_model_provider_without_sessions` |
| 直接覆盖 profile 命中 `profiles.{name}.personality`（内存） | `SKIPPED_EXPLICIT_PERSONALITY` | `test_override_profile_personality_blocks_migration` |
| override profile 命中空映射，且有会话时 | `APPLIED` | `test_empty_profile_does_not_block_personality_migration` |
| override 指向不存在的 profile，且有会话 | 按主流程执行迁移 | `test_override_profile_missing_profile_allows_migration_by_top_level_logic` |
| override 指向不存在的 profile，且无会话 | `SKIPPED_NO_SESSIONS` | `test_override_profile_missing_profile_still_skips_without_sessions` |
| 无 `personality` 且有 active/archived 会话 | `APPLIED` | `test_applies_when_sessions_exist_and_no_personality` / `test_applies_when_only_archived_sessions_exist_and_no_personality` |
| `profiles` 配置不合法（整体非映射） | 回退为空配置 `{}` | `test_config_profile_with_non_mapping_profiles_returns_empty` |
| profile 条目不合法（不是 mapping） | 回退为空配置 `{}` | `test_config_profile_with_non_mapping_profile_entry_returns_empty` |
| 非字符串 `override_profile` | `TypeError` | `test_non_string_override_profile_rejected` |
| 通过磁盘 `config.toml` 传入 override profile | `SKIPPED_EXPLICIT_PERSONALITY` | `test_override_profile_from_disk_config_is_honored` |
| 顶层 profile 与 override 的优先级关系：override 优先于顶层 profile 名称解析 | override 生效 | `test_config_profile_uses_override_before_top_level_profile` |
| CLI 执行入口触发迁移并应用 | 迁移成功后本次执行需重读配置 | `pycodex/cli/parser.py::_run_noninteractive_exec` |

## 与上游 Rust 一致性的校验结论
- Rust 的 `personality_migration.rs` 关键顺序是：`marker -> personality -> 会话记录检查 -> 写入 personality`。
- 当前 `pycodex` 在该顺序上额外加入 `override_profile` 的 profile 合并层，旨在补齐 CLI profile 上下文行为。
