# 2026-06-02 Core Runtime Smoke Suite

## Scope

- 目标：给 core 运行时主路径补齐可直接执行的 smoke 入口，和已有的 local HTTP smoke 组织方式对齐。

## Added

- 新增 `tests/test_exec_core_runtime_smoke_suite.py`
  - 收敛 `test_exec_core_runtime.py` 中对核心决策路径高价值场景：
    - core runtime 构建器 auth 错误改写
    - resume 目标解析（命名会话）
    - `exec` 新会话持久化
    - `review` 持久化
    - `resume` 非持久化路径
    - `resume` 找不到目标时新建 turn 持久化
    - `resume` 预解析命中回退去重
- 新增 `tests/test_core_smoke_suite.py`
  - 组合调用 `core_cli_smoke_suite()` 与 `core_exec_runtime_smoke_suite()`
  - 对应命令 `python -m unittest tests.test_core_smoke_suite`

## Why this helps

- 把你关心的“实际命令可验证闭环”拆成了最小且稳定的复用入口：
  - `exec`
  - `review`
  - `resume`
  - 与 runtime 决策边界

## Follow-up

- 如需继续收口到“一键核心回归”，可以把该套件加入默认的 CI/本地回归脚本入口（如果仓库已有统一 run script）。
