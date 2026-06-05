# 2026-06-02 Core CLI Smoke Suite Added

## Why this matters

之前的回归入口以 `local_http` 为主，核心内存执行路径虽然已有大量单测碎片，但没有一个“可直接跑的、可复用”的最小 smoke 套件入口。为了支持你提到的“实际功能持续验证”，先补齐一个专门针对核心运行时切换/执行闭环的 smoke 模块。

## Added

- 新增 `tests/test_cli_core_smoke_suite.py`
- 套件覆盖 `TopLevelCliParserTests` 中以下高频路径：
  - `exec`：`PYCODEX_EXEC_CORE=1` 与 API key 默认走 core
  - `exec resume`：core resume 找到目标与找不到目标（降级新会话）两条主路径
  - `review`：core runner 与 API key 默认
  - 裸 prompt 在 core-only 下走非交互 core exec
  - core 缺少 API key 的错误边界

## Follow-up

- 下一步可按同样方式补一组 `pycodex.core` 运行时 smoke（非 CLI 入口）入口文件，和该 CLI 套件配合跑成“常用命令”短跑路径。
