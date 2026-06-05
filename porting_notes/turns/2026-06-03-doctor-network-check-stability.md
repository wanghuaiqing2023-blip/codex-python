# 2026-06-03 — `doctor` 测试中的网络可达性稳定性修复

- 现象：`test_main_doctor_*` 在离线/受限环境下会失败，核心原因是 `doctor_provider_reachability_check` 实际探测 `https://api.openai.com/v1`，超时后返回 `fail`，导致 `doctor` 命令退出码变成 `1`。
- 现有测试层已有多处 patch（如 updates、terminal、installations、search 等），但未覆盖 `doctor_provider_reachability_check`。
- 处理方式：
  - 在 `tests/test_cli_parser.py` 的 `TopLevelCliParserTests.setUp/tearDown` 中，对 `test_main_doctor_*` 统一 patch `pycodex.cli.parser.doctor_provider_reachability_check`。
  - mock 返回 `status="warn"`，`details` 保留 `reachability mode: ...` 键值，以兼容 `config_failure` 场景中的结构化断言。
  - 仍保持真实行为不变（仅影响测试桩），便于后续上游核心行为与网络探测逻辑回归时单独验证。
- 验证：
  - `python -m pytest -q tests/test_cli_parser.py -k "main_doctor_"` 通过（16 passed）。
