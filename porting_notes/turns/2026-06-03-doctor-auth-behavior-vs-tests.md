# 2026-06-03 Doctor auth behavior and CLI test parity note

## 发现
- 当前 `pycodex` 的 `doctor` 执行链路会在有可解析 `CODEX_HOME` 时执行 `doctor_auth_check`。
- 当环境没有 OpenAI/Codex 身份凭据且没有配置有效 `auth.json` 时，`doctor_auth_check` 会返回 `fail`（`no Codex credentials were found`）。
- 在未显式设置 `OPENAI_API_KEY` / `CODEX_ACCESS_TOKEN` 的环境中，`main(["doctor"...])` 会因为 `auth` 的 `fail` 计入 `failed_count` 而返回非零码。

## 影响范围
- `tests/test_cli_parser.py` 中多处 `doctor` 场景只补丁了 `doctor_terminal_check`、更新信息或若干特定检查项，未提供环境凭据。
- 这类场景当前会因全局 `failed_count` > 0 导致退出码与既有断言不一致（预期 0）。

## 讨论
- Rust 上游 `find_codex_home` 的默认行为是 `~/.codex`，未设 `CODEX_HOME` 时同样不会报错，因此 `doctor_auth_check` 参与上游路径也是成立的；是否应当保留 `auth` 失败导致非零是语义对齐问题。
- 需要在后续决策中统一：
  - 继续严格对齐上游：保持 `auth` fail 即退出码 1；
  - 或将解析测试视角改为按无凭据环境补齐 `OPENAI_API_KEY`/`CODEX_ACCESS_TOKEN`。

## 后续建议
1. 明确目标分支的默认期望（严格对齐 vs 测试稳定性）。
2. 依据决议在 `pycodex/cli/parser.py::_run_doctor` 或 `tests/test_cli_parser.py` 的医生测试组内统一处理。
