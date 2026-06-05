# Rust 到 Python 大规模迁移策略讨论总结

> 本文总结了一次关于将约 56 万行 Rust 项目迁移到 Python 的工程化讨论。核心结论是：不要把迁移理解为逐行翻译，而应将其视为一次以模块边界、行为一致性和可回退替换为核心的大型再工程化项目。

## 1. 基本判断

对于一个约 56 万行的 Rust 项目，直接将 Rust 代码整体转换为 Python 并不现实，也不推荐。

更合理的目标不是：

```text
Rust 代码逐行翻译成 Python 代码
```

而是：

```text
将 Rust 系统的行为、接口和业务逻辑迁移到 Python 实现中
```

Rust 与 Python 的语言模型差异较大。Rust 强在性能、内存安全、并发控制、系统级抽象和零成本抽象；Python 强在开发效率、生态、脚本化、编排能力和数据/AI 集成。因此迁移时必须谨慎评估哪些模块适合 Python 化，哪些模块应该保留 Rust。

## 2. Codex 的角色

Codex 或类似 AI coding agent 可以在迁移中发挥重要作用，但不应被理解为能够独立完成 56 万行跨语言全自动迁移。

适合交给 Codex 的任务包括：

- 阅读大型代码库并解释模块关系；
- 生成迁移计划；
- 生成模块职责说明；
- 补充测试；
- 迁移单个低风险模块；
- 修复测试失败；
- 生成 adapter、wrapper、fixture；
- 生成 PR 供人工 review。

不建议直接要求：

```text
把整个 Rust 项目转换成 Python
```

更好的方式是分阶段、分模块下达任务，例如：

```text
请分析并迁移 Rust 项目中的 xxx 模块。
要求：
1. 先总结该模块职责、公共 API、数据结构和依赖关系。
2. 找出现有测试，并指出测试缺口。
3. 在迁移前补充行为一致性测试。
4. 将该模块实现为 Python 包中的对应模块。
5. 保持输入输出、错误语义和序列化格式一致。
6. 不要逐行翻译，要写成符合 Python 风格的实现。
7. 运行测试并修复失败。
8. 输出迁移差异、风险点和后续建议。
```

## 3. 总体迁移原则

本次讨论形成的核心原则是：

```text
模块为主，主链为辅。
```

进一步展开为：

```text
静态上按模块拆分，动态上按主链验证；
模块负责封装能力，主链负责验证协作。
```

也可以概括为：

```text
模块边界决定架构质量，主链验证运行正确性。
```

主链的目的不是替代模块边界，而是帮助发现动态运行时经过了哪些模块、模块之间有哪些真实依赖，以及验证模块之间的衔接是否正确。

## 4. 为什么不能只按主链迁移

按照执行主链转写有一定价值，例如从 CLI、API request、job scheduler 或 main pipeline 开始，一路追踪调用路径，可以较快跑通一条真实业务链路。

但如果完全按照主链迁移，容易出现以下问题：

- 沿路缺什么就写什么；
- parser 中混入 validator 逻辑；
- service 中重复实现 formatter；
- adapter 中混入 business logic；
- utils 变成跨模块逻辑堆积区；
- 模块边界被主链破坏；
- 后期 review、测试、维护困难。

因此主链应作为观察和验证工具，而不是代码组织方式。

正确做法是：

```text
沿主链发现缺口 → 回到对应模块补能力 → 再回主链验证
```

即：

```text
主链发现问题，模块解决问题。
```

## 5. 推荐迁移流程

建议采用如下闭环：

```text
模块盘点
  → 定义模块边界
  → 选择一条主链
  → 跟踪主链运行路径
  → 标记涉及模块
  → 检查模块接口是否足够
  → 回到模块内实现/迁移
  → 用主链测试验证衔接
  → 固化接口和依赖规则
```

阶段上可以分为：

| 阶段 | 方法 |
|---|---|
| 第 0 阶段：盘点 | 按模块分析 |
| 第 1 阶段：PoC | 按执行主链跑通一条 vertical slice |
| 第 2 阶段：规模迁移 | 按模块迁移 |
| 第 3 阶段：验收 | 按执行主链做端到端验证 |
| 第 4 阶段：替换 | 按主链逐步切流 |

一句话：

```text
用执行主链确定“先迁什么”，用模块边界确定“怎么迁”。
```

## 6. 模块边界与模块契约

每个模块在迁移前都应形成明确的 module contract。模块契约至少应回答：

- 模块职责是什么？
- 对外暴露哪些接口？
- 输入输出数据结构是什么？
- 依赖哪些模块？
- 禁止依赖哪些模块？
- 错误如何向外传播？
- 是否有副作用？
- 是否涉及并发、异步、IO、FFI 或性能核心？
- 是否应该保留 Rust？
- 验收标准是什么？

示例：

```text
Module: config_loader

Responsibilities:
- 读取配置文件
- 合并环境变量
- 校验配置字段
- 输出标准 Config 对象

Public API:
- load_config(path: str) -> Config

Inputs:
- config file path
- env vars

Outputs:
- Config

May depend on:
- models.config
- utils.path

Must not depend on:
- business_engine
- storage
- api

Errors:
- ConfigNotFound
- ConfigParseError
- ConfigValidationError

Side effects:
- reads file system
- reads environment variables
```

## 7. 模块内部是否需要文件映射

需要，但不应机械地做 Rust 文件与 Python 文件的一一对应。

推荐原则是：

```text
模块级一一对应，文件级有映射关系，但允许重组。
```

也就是说：

```text
Rust crate / module  →  Python package / subpackage
Rust file            →  Python file，通常需要记录对应关系
但不强制一对一
```

文件映射的目的不是照搬结构，而是：

- 防止漏迁；
- 方便 review；
- 方便追踪行为来源；
- 方便测试对照；
- 方便以后查 bug；
- 帮助 Codex 理解上下文。

示例映射表：

| Rust 文件 | Python 文件 | 说明 |
|---|---|---|
| `src/parser/token.rs` | `parser/tokenizer.py` | token 定义与词法逻辑 |
| `src/parser/ast.rs` | `parser/ast_nodes.py` | AST 节点定义 |
| `src/parser/error.rs` | `parser/exceptions.py` | 错误类型 |
| `src/parser/mod.rs` | `parser/__init__.py` | 对外 API 聚合 |
| `src/parser/visitor.rs` | `parser/visitors.py` | visitor 逻辑 |

推荐规则：

```text
对外 API 尽量稳定，内部文件允许重组；
但所有重组必须有映射表。
```

## 8. 模块依赖规则

模块之间应建立显式依赖规则。例如：

```text
models       不依赖任何业务模块
config       可以依赖 models/utils
parser       可以依赖 models/config
validator    可以依赖 models/rules
business     可以依赖 parser/validator/models
storage      可以依赖 models/config
api/cli       可以依赖 business/config/formatter
```

同时明确禁止：

```text
storage 不允许调用 api
models 不允许调用 business
formatter 不允许读数据库
validator 不允许写文件
utils 不允许引用业务模块
```

这些规则应写入 Codex 指令、模块契约和 CI 检查中。

## 9. 如何保证 Python 模块与 Rust 模块行为一致

核心不是看代码像不像，而是建立行为对照验证体系：

```text
Rust 是当前真值源，Python 是候选实现。
所有输入、输出、错误、副作用、性能边界都要可对比。
```

推荐方法是：

```text
golden tests + differential tests + 主链集成测试
```

### 9.1 行为契约

迁移前先定义行为契约：

- 输入是什么？
- 输出是什么？
- 错误有哪些？
- 错误信息是否需要完全一致？
- 边界条件是什么？
- 是否读写文件、网络、环境变量、数据库？
- 是否依赖时间、随机数、全局状态？
- 序列化格式是否必须兼容？
- 顺序是否重要？
- 浮点误差允许多少？
- 性能最低要求是什么？

### 9.2 Golden Tests

使用 Rust 实现生成标准答案。

```text
case_001_input.json
case_002_input.json
case_003_input.json
```

Rust 生成：

```text
case_001_output.json
case_002_output.json
case_003_output.json
```

Python 对同样输入必须产生同样输出。

验收标准：

```text
same input + same config + same environment
→ Rust output == Python output
```

### 9.3 Differential Testing

自动生成大量输入，让 Rust 和 Python 同时运行并比较结果：

```text
生成输入
  → 调 Rust 实现
  → 调 Python 实现
  → 比较输出
  → 记录差异
```

伪代码：

```text
input_n
  rust_result = rust_module(input_n)
  python_result = python_module(input_n)

assert normalize(rust_result) == normalize(python_result)
```

其中 `normalize` 用于处理允许差异，例如：

- 字段顺序；
- 路径分隔符；
- 浮点精度；
- 错误栈；
- 时间格式；
- 随机 ID。

### 9.4 错误行为一致性

Rust 中的：

```text
Result<T, E>
Option<T>
panic
自定义 error enum
```

迁到 Python 后可能变成：

```text
return None
raise Exception
custom exception
```

必须建立错误映射表：

| Rust Error | Python Exception |
|---|---|
| `ConfigNotFound` | `ConfigNotFoundError` |
| `InvalidToken` | `InvalidTokenError` |
| `ParseError { line, col }` | `ParseError(line, col)` |
| `PermissionDenied` | `PermissionDeniedError` |

测试时不仅要看是否失败，还要看：

- 错误类型是否一致；
- 错误码是否一致；
- 错误字段是否一致；
- 错误发生位置是否一致；
- 错误是否被上层正确转换。

### 9.5 序列化兼容

如果模块涉及 JSON、YAML、TOML、protobuf、binary、数据库字段或 API response，应单独验证：

```text
Rust serialize → Python deserialize
Python serialize → Rust deserialize
Rust output bytes == Python output bytes
```

需要特别注意：

- 字段顺序；
- 默认值；
- `null` 与 missing field；
- 数字类型；
- 时间格式；
- 枚举命名；
- 大小写；
- binary endian；
- 路径格式。

### 9.6 副作用隔离

如果模块有副作用，例如读写文件、访问数据库、发网络请求、修改环境变量、写日志、更新缓存、产生随机数、读取当前时间，不应直接比较真实副作用。

推荐将副作用抽象成 adapter，测试 adapter 调用是否一致。

例如不要直接比较：

```text
Rust 模块实际写文件
Python 模块实际写文件
```

而应比较：

```text
Rust 记录 FileWrite(path, content)
Python 记录 FileWrite(path, content)
然后比较 FileWrite 是否一致
```

即比较“意图”，而不是让测试环境被真实副作用污染。

## 10. 主链测试

模块单测只能证明模块内部行为正确，不能证明模块之间衔接正确。

因此还需要主链级测试：

```text
真实输入
  → config
  → parser
  → validator
  → business
  → formatter
  → output
```

比较内容包括：

- Rust 主链最终输出；
- Python 主链最终输出；
- 中间关键 checkpoint 输出；
- 错误传播路径；
- 副作用记录。

建议主链测试加入 checkpoint：

```text
checkpoint_1: config loaded
checkpoint_2: parsed request
checkpoint_3: validation result
checkpoint_4: business result
checkpoint_5: formatted response
```

这样一旦出现不一致，可以定位是哪个模块边界出了问题。

## 11. 行为差异登记表

不是所有差异都必须消灭。有些差异可能是有意的，例如 Python 版本错误信息更清晰，或者内部数据结构不同。

但所有差异都必须登记：

```text
差异编号：
模块：
Rust 行为：
Python 行为：
是否允许：
原因：
影响范围：
是否需要主链验证：
批准人：
```

原则是：

```text
未登记的差异都是 bug。
```

## 12. 是否可以逐个 Python 模块替换 Rust 模块

现实可行，而且是推荐路线之一。但前提是 Rust 模块和 Python 模块之间必须有稳定边界和可调用桥接层。

这不是简单地：

```text
删除一个 Rust 文件，换成一个 Python 文件
```

而是：

```text
模块级替换 + 双实现共存 + 同接口调用 + 分阶段切换
```

推荐结构：

```text
Rust 原模块
Python 新模块
统一接口 / adapter
feature flag / 配置开关
对照测试框架
```

## 13. Python 调 Rust 的方案及其隐含假设

“Python 调 Rust，逐步减少 Rust”方案隐含一个前提：

```text
先把系统的控制权转移到 Python 外壳/编排层，
然后逐步替换被 Python 调用的 Rust 模块。
```

这天然更适合从高层模块开始，而不是从 Rust 内部深层模块开始。

结构大致如下：

```text
Python 主控层 / orchestration layer
  → 调用 Rust 高层模块 A
  → 调用 Rust 高层模块 B
  → 调用 Rust 高层模块 C
```

逐步变成：

```text
Python 主控层
  → Python 模块 A
  → Rust 模块 B
  → Rust 模块 C
```

再继续：

```text
Python 主控层
  → Python 模块 A
  → Python 模块 B
  → Rust 模块 C
```

因此它更像是：

```text
从入口、编排、业务服务层开始替换，再逐步向下沉。
```

## 14. 为什么不推荐 Rust 主控大量调用 Python

如果要在 Rust 主程序内部替换底层模块，例如：

```text
Rust main
  → Rust service
      → Rust parser
          → Python lexer
```

这就不是 Python 调 Rust，而是 Rust 调 Python。

技术上可行，但通常复杂度较高：

- Rust ↔ Python 类型转换复杂；
- 调用频率高时性能差；
- 错误语义不好传递；
- 生命周期和内存管理麻烦；
- 异步/线程模型容易冲突；
- 部署和调试复杂。

尤其底层模块通常调用频率高、数据结构细、性能敏感，Rust 调 Python 往往不划算。

## 15. 推荐替换方向

建议迁移顺序大致为：

```text
入口层 / CLI / API
  ↓
编排层 / workflow / use case
  ↓
业务服务层
  ↓
规则 / parser / formatter / validator
  ↓
性能核心 / 底层 IO / 并发核心
```

不建议一开始就替换：

```text
小函数、高频调用、深层依赖、细粒度对象、性能敏感、生命周期复杂
```

这些模块更适合保留 Rust，或者封装成 Python extension。

## 16. 推荐架构：Python Facade + Rust Extension + 渐进替换

更准确的方案是：

```text
第一阶段：建立 Python facade
第二阶段：Python facade 调用 Rust 高层能力
第三阶段：逐个把 Rust 高层能力替换为 Python 模块
第四阶段：被多个高层能力共享的 Rust 中低层模块，继续保留为 Rust extension
第五阶段：只有当收益明确时，再重写中低层模块
```

Rust 不一定要全部消失。很多中低层模块可以长期作为 Python 的 native extension 存在。

## 17. Dual-run / Shadow Mode

真正稳的方式不是替换后才发现问题，而是先双跑：

```text
输入
  → Rust 模块
  → Python 模块
  → 比较输出
  → 如果一致，使用 Python 输出
  → 如果不一致，记录差异并回退 Rust
```

也可以先做 shadow mode：

```text
生产仍使用 Rust 输出
Python 只在旁边运行并记录差异
```

然后逐步切换：

```text
shadow → canary → partial rollout → full rollout
```

## 18. 模块替换的准入条件

一个模块能被替换，至少要满足：

```text
1. 模块有明确 public API
2. 输入输出数据结构稳定
3. 错误类型有映射
4. 副作用可隔离
5. 有 golden tests
6. 有 differential tests
7. 有主链 checkpoint 测试
8. Python 实现性能可接受
9. 有 feature flag 可回退
```

如果一个模块没有稳定边界，强行替换会很痛苦。

## 19. 适合优先迁移的模块

优先替换：

- 纯函数模块；
- 配置解析模块；
- 格式化模块；
- 校验模块；
- 序列化/反序列化模块；
- 规则判断模块；
- 低频业务逻辑模块；
- CLI 辅助模块；
- 高层业务编排模块。

暂缓替换：

- 高性能核心；
- 并发调度；
- 底层 IO；
- unsafe / FFI 相关；
- 复杂缓存；
- 数据库事务边界；
- 实时流处理；
- 大规模数据处理。

## 20. 每个模块的完成标准

模块不能只说“代码写完了”，应该满足：

```text
1. module_contract.md 完成
2. Rust → Python 文件映射完成
3. API 映射完成
4. 错误映射完成
5. golden tests 通过
6. differential tests 通过
7. 边界条件测试通过
8. 序列化兼容测试通过
9. 主链相关 checkpoint 通过
10. 已知差异已登记
```

## 21. 最终建议

对于 56 万行 Rust→Python 迁移，推荐采用：

```text
模块级 strangler migration：
Rust 实现先包成可替换实现，Python 实现逐个接管，
主链负责验证，feature flag 负责回退。
```

最重要的一句话是：

```text
任何沿主链发现的功能缺口，都必须回到所属模块实现；
任何模块实现完成后，都必须回到主链验证协作正确性。
```

以及：

```text
不要靠人工读代码判断一致性，
要靠同输入、双实现、自动对比来判断一致性。
```

这套方法可以最大程度避免重复实现、边界污染、迁移失控和后期维护困难。
