# Personality Migration Profile Override Wiring

Date: 2026-06-03

Target slice:
- `pycodex/core/personality_migration.py`
- `tests/test_core_personality_migration.py`

Issue:
- `maybe_migrate_personality` 中存在 `override_profile` 参数，但在实现里仅做字符串校验，未真正应用。
- 结果是：当存在会话且 `override_profile` 指向带有 `personality` 的配置档时，迁移仍会继续尝试写入默认 personality，背离参数语义。

Fix:
- 在 `maybe_migrate_personality` 中，若传入 `override_profile`，先从配置中读取该 profile 的映射（通过 `config_profile`）并与当前配置合并。
- 将人格显式设置和 model-provider 回退决策都改为基于该合并后的有效配置，使 profile 覆盖参与迁移决策。

Verification:
- 增加测试：`test_override_profile_personality_blocks_migration`
- 覆盖场景：存在会话、`override_profile` 指向带有 `personality` 的 profile 时，返回 `SKIPPED_EXPLICIT_PERSONALITY`。
