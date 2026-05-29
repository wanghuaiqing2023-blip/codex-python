# Codex Python Porting Guide

这份文档记录本项目的转写思路：如何把 Rust 版 Codex 逐步转成 Python，并尽量保持逻辑和功能一比一复刻。

它不是进度清单。进度清单放在 `PORTING_STATUS.md`。

这份文档更像一张“读源码和移植源码的地图”。

## 1. 核心原则

跨语言转写不是把语法从 Rust 改成 Python。

真正要迁移的是：

- 数据结构
- 协议形状
- 状态流转
- 错误语义
- 执行边界
- 异步/取消/恢复行为
- 工具调用和回灌链路

如果 Python 代码看起来更短、更顺手，但行为和 Rust 不一致，那不是成功的转写。

本项目的目标应该是：

```text
Python 版本能表达 Rust 版本表达的状态。
Python 版本拒绝 Rust 版本拒绝的输入。
Python 版本在关键链路上产生 Rust 版本等价的输出。
```

## 2. 总体策略：先骨架，再链路，再细节

不要一开始逐行翻译所有文件。

推荐顺序是：

1. 先建立骨架。
2. 再打通主链路。
3. 再补齐边界行为。
4. 最后处理性能、体验和细节差异。

原因很简单：大型项目不是一堆函数，而是一台机器。

如果先翻译零件，却不知道它们怎样连接，最后很容易得到一堆“看起来完成”的孤立代码。

## 3. 第一层：骨架

骨架回答一个问题：

```text
这个系统由哪些大层组成？
```

对 Codex 这类项目，可以先按下面的层次理解：

- `protocol`: 协议、事件、模型输入输出、wire shape。
- `core`: 会话、工具、权限、配置、状态机等核心逻辑。
- `exec`: 命令行/非交互执行入口。
- `app-server`: 面向桌面端、TUI 或外部客户端的服务协议。
- `tools`: shell、apply_patch、MCP、web search、browser 等工具系统。
- `tui`: 用户界面和交互体验。
- `rollout/history`: 会话历史、回放、持久化。

移植时优先从 `protocol` 开始，因为协议层是系统的骨头。

如果协议层不稳，后面的工具、会话、UI 都会建立在松动的地基上。

## 4. 第二层：链路

骨架知道“有哪些器官”，链路知道“血液怎样流动”。

比起按文件顺序迁移，更推荐按功能链路迁移。

一条主链路通常长这样：

```text
UserInput
-> ResponseInputItem
-> model request
-> ResponseItem
-> TurnItem / stream event
-> tool call
-> tool runtime
-> function_call_output
-> next model input
```

这条链路打通后，项目才会从“有很多零件”变成“像一台机器”。

读源码时也一样。不要先问“这个文件每一行什么意思”，而要先问：

```text
这个文件处在什么链路上？
它接收什么？
它输出什么？
它改变了什么状态？
它失败时怎样表达失败？
```

## 5. 第三层：边界

边界是跨语言转写里最容易出错、也最重要的地方。

边界包括：

- JSON 字段名
- enum/tagged union 形状
- 必填字段
- 可选字段
- 空数组是否保留
- `null` 和缺失字段是否等价
- 错误类型
- 字符串、整数、布尔值的严格程度
- 路径类型
- 是否允许未知 variant

Rust 通常在类型层面很严格。Python 默认比较宽松。

所以移植时要克制 Python 的宽松性。

不应该随便做这些事：

```python
str(value)
bool(value)
dict(value)
list(value)
value or ""
value or []
```

这些写法看起来方便，但很容易把 Rust 中本该报错的输入悄悄吞掉。

更好的做法是：

```python
if not isinstance(value, str):
    raise TypeError("field must be a string")
```

项目里最近对 `ResponseItem`、`ResponseInputItem`、`WebSearchAction`、`LocalShellAction` 的收紧，就是在补这种边界。

## 6. 第四层：行为

行为不是“这个函数返回差不多的东西”。

行为包括：

- 正常路径返回什么
- 错误路径返回什么
- 什么时候重试
- 什么时候中断
- 什么时候向模型回灌错误
- 什么时候向用户展示错误
- 什么时候记录 rollout
- 什么时候更新会话状态
- 什么时候取消异步任务

跨语言转写时，最危险的是只复刻成功路径。

真实系统的复杂度往往藏在失败路径里。

例如工具调用链路里，需要区分：

- 工具执行成功，结果回灌模型。
- 工具执行失败，但错误应该让模型看到。
- 工具执行失败，而且是 fatal，应该终止当前流程。
- 权限不足，需要请求用户审批。
- sandbox 拒绝，需要判断是否能重试。

这些行为如果不对齐，即使数据结构看起来对了，系统也不是一比一。

## 7. 第五层：测试和证据

测试不是为了证明 Python 代码“能跑”。

测试应该证明 Python 代码“像 Rust”。

优先测试这些内容：

- Rust 能接受的 shape，Python 也接受。
- Rust 会拒绝的 shape，Python 也拒绝。
- Rust 会保留的空字段，Python 也保留。
- Rust 会省略的可选字段，Python 也省略。
- Rust 的错误边界，Python 不要偷偷吞掉。
- Rust 的状态转换，Python 产生等价结果。

测试名称最好能说明对应的 Rust 行为。

例如：

```text
test_response_input_items_reject_non_rust_shapes
test_web_search_action_rejects_non_rust_field_shapes
test_local_shell_call_rejects_non_rust_shapes
```

这种测试对未来读代码的人也有帮助，因为它直接告诉读者：

```text
这里不是随便写的，这是为了贴近 Rust 的行为。
```

## 8. 推荐的移植流程

每次移植一个模块或一条链路时，可以按这个流程走：

1. 找到 Rust 源文件和 Python 目标文件。
2. 标出 Rust 里的公开数据结构、enum、函数、错误类型。
3. 判断这一块属于哪条功能链路。
4. 先移植数据结构和 wire shape。
5. 再移植构造函数、解析函数、序列化函数。
6. 再移植核心行为。
7. 最后补测试和 `PORTING_STATUS.md`。

不要先追求“写得漂亮”。

先追求：

```text
行为可解释。
边界可证明。
差异可记录。
```

## 9. 读 Rust 源码的路线

如果只是打开一个大型 Rust 项目，很容易迷路。

建议按这个顺序读：

1. 先读 `protocol`。
2. 找到核心输入输出类型。
3. 找到一次 turn 的生命周期。
4. 找到工具调用怎样进入系统。
5. 找到工具结果怎样返回模型。
6. 找到错误怎样冒泡。
7. 找到历史和事件怎样记录。
8. 最后再看 UI 和交互层。

读源码时可以一直问这几个问题：

```text
这个类型在哪里被创建？
这个类型在哪里被消费？
它会被序列化吗？
它会跨进程/跨线程/跨客户端传递吗？
它失败时用什么表达？
```

凡是会跨边界传递的类型，都应该优先移植和测试。

## 10. Python 移植时的纪律

Python 版本应该尽量使用标准库，避免引入复杂第三方库。

这不是为了“纯洁”，而是为了降低长期维护成本。

推荐：

- `dataclasses`
- `enum`
- `pathlib`
- `json`
- `asyncio`
- `typing`
- `subprocess`
- `tempfile`
- `hashlib`
- `base64`
- `urllib`

谨慎：

- 大型框架
- 魔法序列化库
- 隐式类型转换库
- 与 Rust 行为不一致的便捷封装

Python 的优势是表达直接，调试方便。

Python 的风险是太容易“顺手兼容”。

这个项目里，宁愿多写几行显式检查，也不要让错误输入悄悄通过。

## 11. 什么叫“一比一复刻”

一比一不是逐行对应。

一比一应该指：

```text
相同输入，在相同状态下，产生等价输出。
相同错误，在相同边界上，以等价方式表达。
相同事件，在相同生命周期中出现。
相同配置，导致相同决策。
```

所以 Python 代码可以不长得像 Rust。

但它必须在关键行为上像 Rust。

例如 Rust 的 enum 到 Python 里可以是 dataclass 加 `type` 字段。

关键不是形式一样，而是：

- 允许的 variant 一样。
- 必填字段一样。
- 可选字段一样。
- 未知 variant 的处理一样。
- 序列化结果一样。

## 12. 进度记录方式

建议长期保留两份文档：

```text
PORTING_STATUS.md
PORTING_GUIDE.md
```

`PORTING_STATUS.md` 记录：

- 已移植什么
- 收紧了什么
- 还缺什么
- 哪些地方是临时实现

`PORTING_GUIDE.md` 记录：

- 如何阅读项目
- 如何移植项目
- 如何判断行为是否对齐
- 后续开发者应该遵守哪些原则

一个是工程账本。

一个是地图。

两者都重要。

## 13. 当前项目的推荐下一步

目前建议从零散补洞逐渐切换到主链路推进。

优先级可以是：

1. `UserInput -> ResponseInputItem`
2. `ResponseInputItem -> model request`
3. `ResponseItem -> TurnItem`
4. `tool call -> tool runtime`
5. `tool output -> next model input`
6. `rollout/history`
7. `session state machine`
8. `app-server / TUI`

这条链路打通后，项目会明显从“很多模块已移植”变成“Python Codex 可以开始跑真实工作流”。

## 14. 一个实用判断标准

每完成一个模块，可以问：

```text
如果 Rust 删除了这个模块，Codex 会坏在哪里？
Python 现在是否也承担了同样职责？
Rust 里这个模块有哪些输入边界？
Python 是否同样拒绝非法输入？
Rust 里这个模块有哪些输出承诺？
Python 是否给出等价输出？
有没有测试证明这一点？
有没有状态文档记录这一点？
```

如果这些问题答得清楚，这一块就不是“翻译了一些代码”，而是真正被移植进了系统。

## 15. 最后一句话

跨语言转写的本质，是把一套系统的“行为契约”搬到另一种语言里。

语法只是表层。

真正要保护的是：

```text
结构不迷路。
链路能闭环。
边界够严格。
行为有证据。
差异被记录。
```

这也是阅读大型源码时最有效的路线。
