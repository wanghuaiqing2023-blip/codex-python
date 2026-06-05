# 人格迁移：override_profile 缺失 profile 回退行为补齐

- 变更文件：
  - `tests/test_core_personality_migration.py`
- 修复点：
  - 新增 `test_override_profile_missing_profile_allows_migration_by_top_level_logic`。
  - 新增 `test_override_profile_missing_profile_still_skips_without_sessions`。
  - 用例覆盖 `override_profile` 指向不存在 profile 时，应按主配置逻辑继续执行迁移（有会话时写入 `personality = pragmatic` 并创建迁移 marker）。
  - 同一场景在无会话情况下应走 `SKIPPED_NO_SESSIONS`，保持与未指定 override 的原语义一致。
- 目的：
  - 避免将“未知 profile”误判为显式人格约束，保持 `exec -> context -> model request -> tool` 主路径的默认行为不被 profile 解析失败污染。
- 后续边界：
  - `config_profile` 对 `profiles` 不为映射对象时返回空映射。
  - `profiles` 中目标 profile 条目不是映射时返回空映射。
  - `override_profile` 若为非字符串，按现有类型校验抛 `TypeError`（既不回退也不静默降级）。
  - 覆盖 `config.toml` 从磁盘读取且 `override_profile` 命中时的行为，确保仍按 profile personality 显式阻断迁移。
