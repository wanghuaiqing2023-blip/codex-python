# Session→Turn resolved-config analytics closure (2026-06-03)

## 目标切片
- 使用真实 `InMemoryCodexSession` 验证 sandbox 策略从会话设置到 turn 采样 analytics 的闭环传播，避免仅在 fake session 上验证优先级规则。

## 变更
- 在 `tests/test_core_session_runtime.py` 新增
  `test_in_memory_session_run_user_turn_sampling_tracks_resolved_config_from_settings_projection`。
- 用例流程：
  1. `InMemoryCodexSession` 实例化并设置基础上下文。
  2. `update_settings(sandbox_policy=SandboxPolicy.read_only(network_access=True))`。
  3. 读取 `thread_config_snapshot()` 作为期望源。
  4. 通过 `run_user_turn_sampling_from_session` 执行一次采样。
  5. 通过 `analytics_events_client.track_turn_resolved_config` 捕获 payload，断言：
     - `permission_profile` 与 snapshot 的 `permission_profile.to_mapping()` 一致。
     - `sandbox_network_access` 为 `True`。
- 同步记录到 `PORTING_STATUS.md`。

## 价值
- 强化主执行链路上的配置解析行为一致性：`thread_config_snapshot -> new_default_turn -> 采样`。
- 该测试不引入新行为，只锁定现有实现的配置分发语义，帮助后续大改时不回退。
