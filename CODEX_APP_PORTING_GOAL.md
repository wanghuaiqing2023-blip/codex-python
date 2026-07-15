# Codex App Porting Goal

## 文件用途

这是给 Codex App 使用的完整目标指令文件。

当需要让 Codex App 继续推进本项目时，可以把本文件作为长期目标上下文使用。它不仅描述“要做什么”，也规定“如何选择下一步”“如何判断 crate/module 是否完成”“什么时候必须停止当前切片”，避免项目陷入凭感觉反复扫描或无限局部修补。

## 目标指令

本项目的长期目标是：将上游 Rust 版 OpenAI Codex 从 `codex/` 行为保持地迁移到 Python 版 `pycodex/`，优先完成核心与常用用户路径，并尽量避免复杂 Python 第三方依赖。

请在后续工作中始终以这个目标为最高约束：

> 以 Rust 源码树作为权威坐标，以知识图谱作为导航索引，以 crate/module 行为边界作为主要对齐单位，将现有 Python 实现逐步归位、补齐、验证，并让常用 Codex 功能在 Python 中达到可用且可解释的行为一致性。

## 给 Codex App 的完整执行指令

请继续推进 `C:\Users\27605\codex-python` 项目。项目目标是把 `codex/` 中的 Rust Codex 核心行为迁移到 `pycodex/`，并让 Python 版本在常用路径上尽量保持与 Rust Codex 一致的用户可见行为。

工作时必须使用中文向用户沟通。不要使用含糊的内部黑话；如果必须使用 crate、module、shim、golden test、parity test 等术语，要说明它们在本项目中的含义。

每轮任务必须以 Rust 源码树为坐标，而不是只以 Python 文件或临时主链为坐标。推荐坐标层级是：

```text
Rust workspace
  -> Rust crate
    -> Rust module
      -> Rust function/type/item
        -> behavior contract
          -> Python package/module/item
            -> focused validation
```

知识图谱 `codex/.understand-anything/knowledge-graph.json` 只能作为导航索引，用于定位 Rust crate/module/function、依赖关系和高影响节点。最终行为判断必须来自 Rust 源码本身。不要把整个知识图谱加载进上下文；只做小范围查询。

每次只选择一个最小且能闭合的行为切片。优先选择能推进常用路径的切片：

```text
exec -> context -> model request -> stream handling -> tool dispatch -> final answer
```

但主链只是选择任务和验证协作的路径，不是唯一的架构边界。真正的进度必须落到 Rust crate/module tree 上。

每轮开始前，先明确：

1. 本轮对应的 Rust crate 是什么。
2. 本轮对应的 Rust module 是什么。
3. 本轮涉及哪些关键 Rust function/type/item。
4. Python 目标位置是什么。
5. 这个切片为什么能推进核心路径。
6. 本轮成功条件是什么。
7. 本轮停止条件是什么。

然后执行：

1. 用知识图谱定位相关 Rust 节点和依赖。
2. 读取少量权威 Rust 源码确认行为。
3. 读取对应 Python 代码。
4. 判断是移动归位、补实现、补测试、合并重复实现，还是只记录缺口。
5. 一次性完成必要修改。
6. 运行 focused validation，只验证本轮 touched behavior。
7. 仅在 module 状态发生实质变化时更新 `PORTING_STATUS.md`，并把持久证据保存在模块
   `README.md`、Rust-derived tests 或专项 alignment 文档中。
8. 向用户汇报 Rust 坐标、Python 坐标、完成内容、验证证据和剩余缺口。

不要一上来全局扫描仓库。不要反复扫描已经判定完成的模块。不要因为相邻边界有趣就扩大范围。不要深挖 MCP、plugin、marketplace、cloud、telemetry、daemon、remote control 等延后扩展区域，除非核心路径确实依赖它们。

如果发现旧 Python 文件还没有归位，应先找到它最接近的 Rust crate/module/function 对应关系，再决定移动、拆分、合并或保留为 compatibility shim。新路径测试通过后，旧路径不能长期保留为并行实现。

如果发现重复实现，应保留更接近 Rust 坐标的位置，把调用方迁移到统一实现，并记录归并结果。

## 工作语言

- 与用户沟通使用中文。
- 技术术语可以保留英文，但必须解释其含义。
- 避免使用临时黑话，例如“某个 N 节点”。应使用正式术语，例如“执行入口阶段”“上下文组装模块”“工具调度模块”。

## 项目背景

- Rust 权威源码目录：`codex/`
- Python 迁移目标目录：`pycodex/`
- Rust 知识图谱：`codex/.understand-anything/knowledge-graph.json`
- 项目原则文档：`PORTING_PROJECT_PRINCIPLES.md`
- 当前状态文档：`PORTING_STATUS.md`
- 持久证据位置：模块 `README.md`、Rust-derived tests 和专项 alignment 文档

本项目不是机械翻译文件，而是行为迁移。Python 代码可以使用更简单的实现方式，但用户可见行为、核心数据契约、错误语义、事件顺序、工具调用结果应尽量与 Rust Codex 保持一致。

## 最高原则

### 1. Rust 源码树是共同坐标

所有迁移、归位、测试和进度沟通，都应尽量落在这棵树上：

```text
Rust workspace
  -> crate
    -> module
      -> function/type/item
        -> behavior contract
          -> Python package/module/item/test
```

其中：

- `workspace` 是 Rust 项目的顶层 Cargo 工作区。
- `crate` 是 Rust 的包级编译单元，是天然的一级对齐坐标。
- `module` 是 Rust 源码中的模块边界，通常是最重要的行为对齐单位。
- `function/type/item` 是局部对比定位单位，不要求所有函数都一比一迁移，但关键函数必须能解释其 Python 对应物。
- `behavior contract` 是行为契约，即该模块对外承诺的输入、输出、副作用、错误、事件和状态变化。

### 2. 知识图谱是导航，不是裁判

使用 `codex/.understand-anything/knowledge-graph.json` 来定位 Rust 文件、模块、符号和依赖关系，但最终行为必须以 Rust 源码为准。

推荐顺序：

1. 用知识图谱定位相关 crate/module/function。
2. 读取少量权威 Rust 源码确认行为。
3. 映射到 Python 目录和模块。
4. 实现最小可闭合行为切片。
5. 针对该切片写或补充测试。
6. 更新状态文档和过程记录。

### 3. module 是常规最小验收单位

函数级对齐太细，crate 级对齐太粗。常规情况下，迁移验收单位应是 Rust module 级行为契约。

函数级对齐只用于：

- 关键入口函数。
- 高风险边界函数。
- 数据转换函数。
- 权限、安全、沙箱、工具执行、事件映射等容易产生行为差异的函数。
- bug 定位时的局部比较。

### 4. 主链不是架构边界

`exec -> context -> model request -> stream handling -> tool dispatch -> final answer` 是核心用户路径，用于发现运行时缺口和验证模块协作。

但它不是唯一进度结构，也不应该替代 Rust crate/module 树。

正确做法是：

- 用主链选择当前最有价值的行为切片。
- 用 Rust crate/module 定义对齐边界。
- 用测试确认该模块行为是否闭合。
- 用状态文档记录是否完成。

### 5. 旧 Python 成果必须归位，而不是作废

之前已经实现的大量 Python 代码应尽量保留并归入与 Rust 对应的 Python 目录结构中。

处理旧文件时遵循：

1. 先找到它在 Rust 中最接近的 crate/module/function 对应关系。
2. 再决定移动、拆分、合并或保留为 compatibility shim。
3. 新路径测试可通过后，再删除旧路径。
4. 旧路径不能长期保留为并行实现，否则会增加混乱和重复实现风险。

## 当前优先范围

优先实现常用核心功能：

- CLI 入口，尤其是 `codex exec`。
- 交互式任务执行的核心路径。
- 上下文组装：项目说明、当前目录、环境元数据、配置、模型选择、会话状态。
- 模型请求构造、响应流处理、工具调用循环、最终回答生成。
- 工具系统：shell 命令、文件读写、补丁应用、工具结果返回。
- 审批与安全：危险命令判断、权限请求、沙箱策略近似、用户可理解的错误。
- CLI/core runtime 必需的 app-server 协议事件兼容。

暂缓深度实现：

- MCP runtime。
- plugin marketplace。
- plugin install/cache 完整流程。
- skills/plugin discovery 的深层扩展行为。
- multi-agent/sub-agent 编排。
- cloud task / remote task。
- telemetry / analytics / update check。
- app-server daemon、proxy、remote control、websocket transport、schema generation。

这些扩展区域可以保留轻量兼容 shim，但不要把它们计入核心完成度。

## crate 级成功条件

一个 Rust crate 对应的 Python 区域可以标记为“已完成当前阶段”，必须满足以下条件：

1. 已登记该 crate 在 Python 中的对应目录或明确标记为暂缓/不实现。
2. crate 下的主要 Rust modules 已建立对应关系。
3. 该 crate 在核心用户路径中的职责已经明确。
4. 核心路径依赖的 modules 至少达到 module 级行为契约闭合。
5. 非核心 modules 已标记为 deferred、shim、out_of_scope 或 follow-up debt。
6. 不存在同一行为在多个 Python 位置重复实现且无人解释的情况。
7. `PORTING_STATUS.md` 中记录了当前状态、证据和剩余缺口。

crate 级完成不表示源码逐行完全迁移，而表示：在当前项目目标下，该 crate 的核心职责、Python 对应物、已实现范围、测试证据和延后范围都已经清楚。

## crate 级停止条件

处理某个 crate 时，一旦满足以下条件，应停止继续扩大该 crate 的本轮范围：

1. 已确认该 crate 是否属于当前核心目标。
2. 已登记它的 Python 对应目录，或明确标记为 `deferred`、`shim`、`out_of_scope`。
3. 已列出当前核心路径会触达的主要 modules。
4. 本轮选定 module 的行为切片已经实现、验证或记录缺口。
5. 未触达的 modules 已登记为后续债务，而不是继续顺手展开。
6. `PORTING_STATUS.md` 已记录该 crate 当前阶段状态。

crate 级停止的含义是：本轮对这个 crate 的推进已经有明确边界，不能因为 crate 内还有其他 module 就继续无休止扫描。

## module 级成功条件

一个 Rust module 对应的 Python module 可以标记为“已完成当前阶段”，必须满足以下条件：

1. Rust module 的对外行为边界已经明确。
2. Python module 的对应位置已经确定，并符合 Rust tree 对齐原则。
3. 核心 public functions/types/data contracts 已有 Python 对应物，或明确说明为何不需要一比一实现。
4. 输入、输出、错误、事件、状态变化、副作用已经与 Rust 行为对比过。
5. 至少存在一种验证证据：
   - Rust 自带测试的 Python parity test。
   - Python focused unit test。
   - deterministic golden fixture。
   - 明确的局部 smoke test。
   - 对不可运行路径的源码级行为说明。
6. 已记录缺失测试、暂缓分支和兼容 shim。
7. 该 module 的完成不会依赖无限扫描或凭感觉重复验证。

module 级完成不要求覆盖所有极端边界，但必须覆盖核心行为、常见用户路径和高风险边界。

## module 级停止条件

处理某个 module 时，一旦满足以下条件，应停止当前 module 切片：

1. Rust module 的 authoritative source 已经读完本轮必要范围。
2. module 对外行为契约已经明确。
3. Python 对应 module 已经确定。
4. 本轮目标行为已经实现或明确记录为缺口。
5. 已运行 focused validation，或说明无法验证的原因。
6. 相邻 module 的问题已经登记为 follow-up debt，而不是纳入本轮。
7. 如果 module 状态发生实质变化，权威状态和持久证据已经同步更新。

module 级停止的含义是：当前行为契约已经闭合，不再凭感觉进行第二次、第三次扫描。

## function/type 级成功条件

函数或类型不是默认验收单位，但在关键位置必须能进行局部对齐。

以下情况应建立函数级或准函数级对应关系：

- CLI 参数解析与命令分发。
- 配置归一化。
- session/context 构造。
- 模型请求构造。
- 响应事件映射。
- 工具规格生成。
- 工具名称查找与 handler 调用。
- shell 命令安全判断。
- 权限请求、审批、取消、fallback。
- 文件修改和补丁应用。
- 退出码和错误展示。

函数级完成条件：

1. Rust 函数或类型名称已确认。
2. Python 函数、类或组合实现已确认。
3. 如果不是一比一实现，必须说明映射原因。
4. 至少有局部测试或调用方测试覆盖其关键行为。
5. bug 修复时可以通过这组映射快速定位对比范围。

## function/type 级停止条件

处理关键函数或类型时，一旦满足以下条件，应停止当前局部对齐：

1. Rust function/type 的输入、输出、错误、状态变化或副作用已确认。
2. Python 对应函数、类或组合实现已确认。
3. 如果不是一比一对应，已经说明为什么是组合映射或语义映射。
4. 关键分支已有测试或被调用方测试覆盖。
5. 若发现更大范围问题，已提升为 module follow-up，而不是继续在函数层级扩张。

## 停止条件：避免无休止扫描

每个 crate/module/function 切片必须有明确停止条件。不能凭感觉反复扫描。

一次切片在满足以下条件后应停止：

1. 本轮选定的 Rust 源码已读完。
2. Python 对应实现已确认或修改完成。
3. 本轮必要的 focused test 已通过，或无法验证的原因已记录。
4. 状态文档已更新。
5. 剩余问题已作为 follow-up debt 记录，而不是继续扩大范围。

如果发现新问题，按以下规则处理：

- 如果新问题直接阻断当前切片验收，则纳入本轮。
- 如果新问题属于相邻模块但不阻断当前切片，则记录到后续任务。
- 如果新问题属于 MCP/plugin/marketplace/cloud 等延后区域，则只保留 shim 或文档缺口。
- 如果新问题会改变目录结构或对齐原则，应暂停并与用户确认。

## 验证策略

优先使用 Rust 源码自带测试作为行为来源。

测试来源分为：

- Rust source tests：Rust 源文件或测试文件中已有的单元/集成测试。
- Python parity tests：根据 Rust 测试语义写出的 Python 对齐测试。
- Golden tests：以 Rust 行为输出作为母体的固定样例测试。
- Differential tests：同一输入分别运行 Rust 和 Python，比较行为输出。
- Focused smoke tests：针对 CLI 或 runtime 小路径的可运行验证。

测试原则：

- 不追求一次性全量测试。
- 每次只验证本轮 touched behavior。
- 测试注释中应尽量注明行为来源，例如对应 Rust 文件、函数或测试名。
- 如果 Rust 测试无法直接运行或脚手架成本过高，可以先写 Python parity test，并记录来源。

## 进度状态定义

建议使用简单状态，避免过细：

- `candidate`：候选对应关系，尚未确认。
- `gap`：确认存在实现或测试缺口。
- `implemented`：已经实现核心行为，但未充分验证。
- `verified`：已有针对性测试或可靠证据验证。
- `deferred`：当前目标暂缓。
- `shim`：只做兼容外壳，不做完整实现。
- `out_of_scope`：明确不属于当前目标。

## 每轮工作标准流程

每次开始新任务时，按以下顺序执行：

1. 明确本轮只处理哪个 Rust crate/module/function 行为切片。
2. 用知识图谱定位对应 Rust 节点和依赖关系。
3. 读取少量权威 Rust 源码。
4. 读取对应 Python 代码。
5. 判断是移动归位、补实现、补测试，还是只记录缺口。
6. 一次性完成必要修改。
7. 运行 focused validation。
8. 仅在 module 状态发生实质变化时更新 `PORTING_STATUS.md`，并更新模块证据。
9. 向用户说明：本轮完成了什么、对应 Rust 坐标是什么、测试证据是什么、还剩什么。

## 选择下一步任务的算法

在选择下一步时，先回答：

> 基于 Rust 依赖图，哪个 crate/module/function 切片能用最小安全改动，最大程度推进 `exec -> context -> model request -> stream handling -> tool dispatch -> final answer` 的常用路径？

排序优先级：

1. 直接阻断核心用户路径的模块。
2. 高 fan-in/fan-out 的共享数据契约和工具调度模块。
3. 权限、安全、沙箱、文件写入等高风险模块。
4. 已有 Rust 测试可作为 parity source 的模块。
5. 旧 Python 文件尚未归位且容易造成重复实现的模块。
6. 只需 shim 的延后扩展区域。

不要因为某个边界有趣就无限扩展。主路径可运行和模块契约闭合优先。

## 重复实现规避规则

任何新实现前都必须确认是否已有公共模块承担该职责。

重点检查：

- 工具规格和注册是否应进入 tools/spec 或 registry 相关模块。
- 工具分派是否应进入 tools/handlers 或 tool router 相关模块。
- shell 命令安全判断是否应进入 shell safety 相关模块。
- session/turn/context 是否已在 state/session/context_manager 相关模块中实现。
- HTTP transport 或 app-server 兼容逻辑是否只是 shim，不应散落在 core 逻辑里。

如果发现重复实现：

1. 保留更接近 Rust 对应坐标的位置。
2. 将调用方迁移到统一实现。
3. 新路径测试通过后删除旧路径。
4. 在状态文档中记录归并结果。

## 对 Codex app 的执行要求

当 Codex app 继续执行本项目时，请遵守：

- 不要一上来全局扫描整个仓库。
- 不要把知识图谱整体加载进上下文。
- 不要反复扫描已经判定完成的模块。
- 不要用主链状态替代模块对齐状态。
- 不要新增复杂第三方依赖，除非用户明确批准。
- 不要深挖延后扩展区域，除非核心路径依赖它。
- 不要长期保留旧路径和新路径并行实现。
- 每轮只做一个小而闭合的行为切片。
- 变更代码后运行 focused tests。
- 重要的 module 状态变化必须更新 `PORTING_STATUS.md`；持久证据必须落在模块
  `README.md`、Rust-derived tests 或专项 alignment 文档中。

## 单轮汇报模板

每轮完成后，请使用下面的信息结构向用户汇报：

```text
本轮切片
- Rust crate:
- Rust module:
- Rust function/type/item:
- Python target:

完成内容
- 

验证证据
- 

停止原因
- 

剩余缺口
- 
```

其中“停止原因”必须具体说明为什么本轮不继续扩展，例如“当前 module 的目标行为已测试通过，相邻 plugin 分支登记为 deferred”。

## 预期最终形态

项目完成当前阶段时，应达到：

1. Python 目录结构能清楚表达 Rust crate/module 对应关系。
2. 常用 `codex exec` 路径可用。
3. 常用交互式 agent loop 可用。
4. 上下文、模型请求、流处理、工具调用、最终回答形成闭环。
5. shell/file/patch 等常用工具行为稳定。
6. 审批、安全、沙箱的常见行为与 Rust 接近。
7. 延后扩展区域有明确 shim 或 gap 文档。
8. 每个核心 crate/module 都能说明完成状态和测试证据。
9. 后续 bug 修复可以通过 Rust tree 坐标快速局部定位，而不是重新扫描整个项目。

## 可直接使用的目标提示词

请继续推进 `C:\Users\27605\codex-python` 项目。目标是将 `codex/` 中的 Rust Codex 行为保持地迁移到 `pycodex/`，优先完成核心和常用用户路径。

请以 Rust 源码树为权威坐标，以 `codex/.understand-anything/knowledge-graph.json` 为导航索引。每轮选择一个最小的 crate/module/function 行为切片，先确认 Rust 源码行为，再映射或修正 Python 实现，然后运行 focused validation。只有 module 状态发生实质变化时才更新 `PORTING_STATUS.md`，并把持久证据写入模块 `README.md`、Rust-derived tests 或专项 alignment 文档。

验收单位优先使用 Rust module 级行为契约。crate 级用于全局进度，function/type 级用于关键边界和 bug 定位。不要只按主链无限扫描；主链只用于选择和验证核心路径，真正的进度应落到 Rust crate/module tree 上。

当前优先路径是：`exec -> context -> model request -> stream handling -> tool dispatch -> final answer`。优先处理直接阻断这条路径的模块、高 fan-in/fan-out 的共享契约、权限/安全/沙箱/工具执行等高风险模块，以及尚未归位且可能导致重复实现的旧 Python 文件。

MCP、plugin、marketplace、cloud、telemetry、daemon、remote control 等扩展区域暂不深度实现。只有在核心路径需要时才做轻量 compatibility shim，并将缺口记录为 deferred/gap。

每个 crate/module/function 切片都必须有明确成功条件和停止条件。crate 级成功意味着职责、Python 对应物、核心 module 状态、测试证据和延后范围都清楚；module 级成功意味着行为契约、Python 对应、关键分支和验证证据都闭合；function/type 级只用于关键边界和 bug 定位。满足本轮停止条件后必须停止，不要凭感觉反复扫描。
