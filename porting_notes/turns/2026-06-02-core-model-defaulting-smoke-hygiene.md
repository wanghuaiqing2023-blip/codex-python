# 2026-06-02 Core model default + smoke suite hardening

## Progress
- 切换了核心本地 HTTP 路径默认模型为 `gpt-5.3-Codex-Spark`，包括 `DEFAULT_OPENAI_MODEL` 以及 `debug models` 默认列表/示例文案，避免出现旧默认值。
- 修复了 `tests/test_cli_core_smoke_suite.py` 中的不存在测试名（`test_main_exec_review_core_env_...` -> `test_main_review_core_env_...`），恢复 core smoke suite 可加载。
- 新增 CLI 主流程回归测试：`test_main_debug_models_returns_supported_default_models`，验证 `debug models` 输出中包含 `gpt-5.3-Codex-Spark`，并保持成功返回。

## 验证
- `python -m unittest tests.test_cli_core_smoke_suite` 通过（30/30）。
- `python -m unittest tests.test_exec_core_runtime_smoke_suite` 通过。
- `python -m unittest tests.test_core_smoke_suite` 通过（与 core CLI 套件联跑）。
- `python -m unittest tests.test_local_http_core_smoke_suite` 通过。
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_debug_models_returns_supported_default_models` 通过。

## 下一步
- 继续对 core 默认模型影响面做横向回归（如交互入口/配置文件默认落点）并补齐相关断言。
