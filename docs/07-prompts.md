# AI Panel Studio 核心 Prompt 记录

> 本文仅记录项目开发中用于引导 AI 的核心提示词，按 SDD、DDD、TDD、E2E 与审核阶段整理。它不是开发过程思路或工作流说明；后者应作为独立交付物维护。

## 使用说明

- 每段 Prompt 均以当时已完成的文档或代码为上下文，避免让模型凭空假设项目状态。
- 所有 Prompt 都强调 72 小时、单人、可本地演示的 MVP 边界，防止无关的生产级扩张。
- 模型输出中的结构化内容必须由后端校验；任何用户可见内容均不得包含隐藏推理或 Chain-of-Thought。

---

## Prompt 1：SDD 阶段｜需求、领域模型与 API 契约

### 原始 Prompt

```text
请完整阅读《AI开发实习生远程作业：AI圆桌讨论 Web App MVP》需求附件。

你现在的任务不是开发项目，而是作为资深产品架构师和软件架构师，完成开发前的 SDD（Spec/Schema-Driven Development）阶段文档。

约束：
1. 当前阶段禁止生成具体业务实现代码，也不要假设任何功能已实现。
2. 以原始作业要求为最高优先级；存在歧义时，明确标注“设计假设”或“架构决策”。
3. 所有文档使用中文 Markdown，Mermaid 图应可直接渲染。
4. 控制在 72 小时内由单人完成、可测试、可本地演示的 MVP 范围内。
5. 技术基线为 React + TypeScript + Vite、FastAPI + SQLAlchemy + SQLite + Pydantic、SSE、DeepSeek V4 Pro、pytest 与 Playwright。

请分别生成以下四份可进入仓库、可指导后续实现的文档：
1. docs/01-prd.md：产品目标、用户流程、功能与非功能需求、异常、明确不做项、验收清单。
2. docs/02-domain-model.md：以 Discussion 为聚合边界，定义 Discussion、Participant、Utterance、Insight，包含状态机、ER 图、领域规则，以及运行时和持久化状态边界。
3. docs/03-api-contract.md：定义最小 REST + SSE 契约，覆盖讨论创建、阵容生成与确认、开始/停止、总结重试、快照和事件流；所有事件必须带 discussion_id，并定义统一错误格式。
4. docs/04-architecture.md：定义前后端、SQLite、SSE、LLM Provider、DiscussionRunner、CastGenerator、FloorScheduler、InsightExtractor 的职责与隔离策略。

必须保证每场 Discussion 的 Participants、Utterances、Insights、Runtime State 与 Event Stream 相互隔离；嘉宾公开状态只能是待机、准备发言、发言中及简短 public_focus，禁止请求、保存或展示 Chain-of-Thought。

最后列出不超过 5 项、确实需要开发者人工确认的事项。
```

**意图：** 先把产品边界、数据模型和前后端契约固定下来，让后续实现有可验证的单一事实来源。

**挑战与修正：** 初始需求包含“生产级质感”，容易诱导模型引入消息队列、复杂恢复或无限 Agent 调度。Prompt 明确限定单机 MVP 和“禁止假设实现”，把复杂度留在需求之外。

---

## Prompt 2：SDD 阶段｜MVP 精简与结构化输出安全边界

### 原始 Prompt

```text
请以已经完成的 PRD、领域模型、API 契约和架构文档为基线，进行一次“只减不扩”的 MVP 修订。

必须保留：创建讨论、生成并确认阵容、显式开始、实时 Transcript、嘉宾公开状态、共识/分歧、主持人总结、SSE、多 Discussion 隔离、TDD 与 Playwright 验收。

请删除不影响上述验收的复杂设计：进程重启恢复、SSE 事件编号/回放/去重、复杂离线状态机、确定性多分支发言评分、Insight 语义 upsert 历史。

将 FloorScheduler 收缩为：模型基于本场 Participants、Transcript 与活跃 Insights 动态选择下一位 speaker，并返回一条简短 public_focus。应用层只校验：首轮必须由主持人发言；被选嘉宾必须属于当前 Discussion；有其他候选人时不得连续选择同一人；讨论停止或达到 15 条公开发言时不再继续。

public_focus 必须是独立、可公开展示的字段；禁止请求、保存或输出 Chain-of-Thought、reasoning、intent 等隐藏推理字段。

Insight 每轮返回“当前完整活跃集合”，每类最多两项，前端直接替换展示。每次 SSE 连接先发送完整 snapshot；不实现事件回放或去重。

同步修订受影响文档，并明确指出仍存在的冲突；不要生成业务实现代码。
```

**意图：** 将文档从“看起来像生产系统”的设计收缩为可在作业期限内实现和演示的最小闭环。

**挑战与修正：** 多角色讨论容易被过度设计成复杂 Agent 框架。这里把“动态选人”和“公开关注点”拆开，既满足非机械轮流发言，也明确保护隐藏推理安全边界。

---

## Prompt 3：DDD 阶段｜演播厅 UI/UX 设计

### 原始 Prompt

```text
基于已经确认的 PRD、领域模型、API 契约和架构，进入 DDD（Design-Driven Development）阶段，生成 docs/05-ui-design.md。

请设计 AI Panel Studio 的中文 Web UI，覆盖：首页、发起讨论、嘉宾确认、演播厅、讨论结束和错误状态。

演播厅必须有“AI 圆桌直播/演播厅”的沉浸感：
- Transcript 是视觉中心，显示姓名、职业/Title 与和嘉宾一致的色彩标识；不得显示举手或内部调度事件。
- 每位嘉宾有独立状态小窗，展示待机/准备发言/发言中，以及可公开的 public_focus；不得展示隐藏思考过程。
- 共识与分歧在讨论中持续更新，而非结束后一次性出现。
- 主持人总结必须是自然语言；不得向页面输出 JSON 原文。

请定义信息架构、页面状态、视觉语言、颜色与排版、核心组件契约、Loading/Error 反馈、可访问性，以及超宽屏、普通桌面、窄屏的响应式规则。

整个页面不应依赖页面级长滚动；Transcript、嘉宾区和观点区应在各自容器内独立滚动。不要写具体实现代码，也不要改变既有产品流程与技术架构。
```

**意图：** 让前端实现有明确的体验目标和组件边界，避免只根据接口字段拼接出普通后台页面。

**挑战与修正：** “实时感”容易被误解为大量动效或暴露内部 Agent 事件。Prompt 把重点落在状态、Transcript 和洞察的可见变化，同时严格禁止展示隐藏推理。

---

## Prompt 4：TDD / E2E 阶段｜测试策略与质量闭环

### 原始 Prompt

```text
基于已完成的产品、领域、API、架构与 UI 文档，进入 TDD + E2E 阶段，生成 docs/06-testing-strategy.md。

请设计覆盖核心业务风险的测试策略，包含：
- CastGenerator：阵容数量、角色、颜色和立场差异的校验与纠错；
- FloorScheduler：首轮主持人、同场归属、避免连续同人、停止和发言上限；
- InsightExtractor：共识/分歧集合替换与失败降级；
- DiscussionRunner：状态流转、主持人收束、总结、异常和并发隔离；
- SQLite 持久化、REST API、SSE 事件契约和多 Discussion 隔离；
- Chain-of-Thought 不可暴露的安全测试。

必须体现 Red → Green → Refactor 的 TDD 工作流，并设计 FakeLLMProvider，使单元和集成测试不依赖真实 DeepSeek API、网络或 API Key。

E2E 使用 Playwright，至少规划以下场景：完整讨论流程、多 Discussion 隔离、响应式与独立滚动、总结失败后的降级与重试。

当前仅在编写开发前测试策略：不得虚构测试已经执行、通过或达到任何覆盖率。
```

**意图：** 先定义最可能出错的 AI 调度、事件流与隔离行为，再以可重复的测试反推实现。

**挑战与修正：** 真实模型输出不稳定、也会产生费用，因此明确采用 FakeLLMProvider 作为自动化测试边界，真实 DeepSeek 只用于开发者手工烟雾测试。

---

## Prompt 5：审核阶段｜文档一致性与 MVP 可实现性审查

### 原始 Prompt

```text
请以“技术面试官 + 软件架构 Reviewer”的视角审核 AI Panel Studio 项目文档。

背景：这是一个 72 小时 AI 开发实习生远程作业，重点考察 SDD、DDD、TDD、E2E 的工程化过程，而不是复杂生产系统。

请检查：
1. PRD、领域模型、API、架构、UI 和测试策略之间是否存在字段、状态、接口或事件冲突。
2. 是否遗漏作业明确要求：阵容生成与确认、非机械轮流发言、实时状态、Transcript、实时共识/分歧、主持人总结、SSE、多 Discussion 隔离、中文响应式 UI。
3. 是否存在 Redis、消息队列、复杂 Agent Framework、复杂缓存或恢复机制等不适合 MVP 的过度设计。
4. Discussion 状态机、expert_count 范围、发言上限、Participant/Utterance/Insight 字段、REST/SSE 契约、总结降级、FakeLLMProvider 边界是否一致。
5. 是否始终遵守 Chain-of-Thought 不可请求、持久化或展示的原则。

按以下结构输出：总体结论、必须修改的问题、建议简化的问题、文档冲突、遗漏的招聘要求、最终 MVP 边界、开发前 Checklist（不超过 20 项）。

只给出可执行的精确建议；不要为显得专业而增加题目外的新功能。最后明确结论：可以开始开发，或建议先修改文档后再开发。
```

**意图：** 在编码前主动发现契约冲突、范围膨胀和“文档看似完整但不可落地”的问题。

**挑战与修正：** AI 容易在审核时顺带发明功能。Prompt 将审核范围限定为原始作业、既有文档一致性和 MVP 可实现性，要求只提出精确修改建议。

---

## Prompt 使用的阶段映射

| Prompt | 阶段 | 主要产物 | 核心约束 |
| --- | --- | --- | --- |
| Prompt 1 | SDD | PRD、领域模型、API、架构 | 契约先行、Discussion 隔离 |
| Prompt 2 | SDD 修订 | MVP 收缩后的设计基线 | 只减不扩、隐藏推理不可见 |
| Prompt 3 | DDD | UI/UX 设计 | 演播厅体验、响应式与独立滚动 |
| Prompt 4 | TDD + E2E | 测试策略 | FakeLLMProvider、可重复验收 |
| Prompt 5 | 审核 | 开发前一致性审查 | 避免过度工程与需求遗漏 |
