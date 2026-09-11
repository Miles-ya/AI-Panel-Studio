# AI Panel Studio 开发过程思路与工作流说明

## 1. 我是怎么拆这件事的

这个项目最容易犯的错误，是让 AI 一次性把“AI 圆桌讨论”从前端、后端到实时事件全部写出来。看起来很快，实际上很难验证：需求会被补全、接口会漂移，异步逻辑和页面状态也会一起失控。

所以我把工作拆成 SDD、DDD、TDD、联调和 E2E 几段。每一段只处理一个问题，完成后跑对应检查、做一次 Git commit，然后停止。下一段在新的对话里开始，重新带上必要文档和上一步结果。

这样做的目的不是增加流程，而是让 AI 每次只面对明确、有限、可以验收的上下文。

## 2. 先用 SDD 把“能做什么”说清楚

开发一开始没有写业务代码，先把需求落成文档：PRD、领域模型、ER 图、REST/SSE 契约、架构和测试策略。

这一步把几个容易模糊的地方提前定死了：

- `Discussion` 是一场讨论的边界，嘉宾、发言、Insight、Runner 和事件都只能属于同一个 `discussion_id`；
- 状态只允许 `DRAFT → CAST_READY → RUNNING → FINISHED / FAILED`；
- SQLite 只保存 Discussion、Participant、Utterance、Insight 四类核心数据；
- 发言人不是机械轮流，而是由模型结合本场 Transcript 和 Insights 动态选择；
- 应用层只保留首轮主持人、同场归属、避免无意义连续发言、停止和 15 条上限这些必要限制；
- `public_focus` 是给用户看的简短公开关注点，不请求、不保存、更不展示隐藏推理；
- SSE 每次重连直接发完整 snapshot，不做事件编号、回放或去重。

这些文档相当于后续开发的“护栏”。当 AI 给出一个看似合理、但文档里没有的方案时，我会优先回到契约确认，而不是让实现继续扩张。

## 3. 再用 DDD 先把演播厅做出来

后端还没接入时，先完成了静态的中文演播厅界面。这个阶段重点不是堆组件，而是先回答一个问题：用户打开页面时，感觉是在聊天，还是在看一场正在发生的圆桌讨论？

因此页面把 Transcript 放在视觉中心，嘉宾状态卡、共识与分歧、总结卡作为辅助信息。宽屏、普通桌面和窄屏都使用各自独立的滚动区域；用户翻看历史发言时，页面不会强行拉回底部，而是提示“有新发言”。

这一阶段先使用受控 mock 数据。这样视觉层、组件层级、响应式布局和状态呈现可以独立验收，不会因为后端接口还在变化而反复推倒重来。

## 4. 核心逻辑严格按 TDD 推进

后端没有直接从“功能实现”开始，而是按最小切片做 Red → Green：先写并运行失败测试，提交 `test:`；再用最小代码让测试通过，提交 `feat:`。

主要切片依次是：

1. Discussion 生命周期和基础 API；
2. 嘉宾阵容生成与原子替换；
3. LLM 动态选人与公开安全；
4. Runner、Insights、停止、15 条收束和总结降级；
5. SSE snapshot 与多 Discussion 隔离。

测试全部使用 Fake 或 Scripted Provider，不访问真实 DeepSeek。模型回复、时间和异步推进顺序都可以控制，所以 pytest 既能验证 LLM 输出是否越界，也能重复验证多场讨论不会串数据。

Git 历史保留了测试驱动实现的过程，例如：

```text
test: specify discussion lifecycle behavior
feat: implement discussion lifecycle and base API

test: specify cast generation guarantees
feat: implement validated cast generation

test: specify LLM speaker selection safety
feat: implement LLM-driven speaker selection

test: specify live runner and completion behavior
feat: implement live runner and controlled completion
```

中间发现测试 fixture 自己违反领域规则时，也没有为了让测试通过去放宽业务约束，而是新增独立 `test:` 修正提交。例如 Runner fixture 补齐了 `1 moderator + 2 experts`、合法 UUID、真实 SQLite 发言序号和正确事件顺序。这样测试始终是在描述真实业务，而不是迁就实现。

## 5. 联调时只解决“真实数据怎么流动”

静态页面完成后，才把 mock 换成真实 REST 和 SSE。

讨论 ID 由 URL 决定：`/` 是首页，`/create` 是创建页，`/discussions/:id` 是具体讨论。进入详情页时，前端先通过 REST 读取完整快照，再连接同一场讨论的 SSE；每次收到 `discussion.snapshot` 都直接覆盖本场状态。

路由切换时会取消旧的 REST 请求、关闭旧 EventSource，也会忽略迟到响应。这样用户从 A 场切到 B 场时，不会被 A 场慢到的请求覆盖页面。

为了能稳定演示，后端还提供了显式 Fake LLM 模式。Fake 场景按 `discussion_id` 独立，不共享全局脚本队列，因此两场讨论同时运行时，阵容、发言、Insights 和总结都不会互相影响。

## 6. 过程中遇到的几个实际问题

### 6.1 AI 容易把 MVP 做复杂

一开始很容易想到重启恢复、事件回放、客户端去重、复杂调度评分等机制。但这些能力不影响本次作业验收，反而会把上下文和测试量迅速放大。

最后的处理方式是回到 MVP 边界：保留完整 snapshot、最小选人约束和单进程 Runner；明确不做恢复、回放、事件 ID、离线状态机和 Insight 历史语义合并。

### 6.2 SSE 与异步测试不能靠等待运气

FastAPI TestClient 在当前环境里出现过 AnyIO 门户挂起；持续 SSE 流也不能等待连接“自然结束”。

后来的测试把有限 REST 响应和持续事件流分开处理：REST 用异步 ASGI 客户端；SSE 通过 EventHub 门闩和 `body_iterator` 消费首帧与后续帧，并给每次等待设置超时。这样测试失败时能明确知道是事件没来，还是契约不对。

### 6.3 测试数据本身也会犯错

Runner 的早期测试曾出现单 expert fixture、非 UUID participant ID，以及把 `utterance.created` 当成第一条事件等问题。

解决方式不是跳过这些测试，而是先修正测试：用临时 SQLite 创建完整合法阵容，用真实 Repository 验证事务提交，用事件类型筛选流中的目标事件。修正后再继续 Green，避免把测试问题误判成生产问题。

## 7. 我对工程化 AI 开发的理解

我理解的工程化 AI 开发，不是让模型写更多代码，而是让模型每次写的代码都处在清楚、可验证的边界里。

在这个项目中，文档限制需求边界，设计限制 UI 表达，失败测试限制业务实现，Fake Provider 限制模型非确定性，Git commit 限制每一阶段的改动范围。AI 可以提升实现效率，但不能替代领域规则、接口契约和验收证据。

最终交付会用 pytest、前端 lint/typecheck/build、Playwright E2E、Prompt 记录和 Git 演进共同证明：这不是一次性生成的演示代码，而是按可审查流程逐步完成的 MVP。
