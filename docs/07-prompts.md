文档生成

```markdown
请完整阅读我上传的《AI开发实习生远程作业：AI圆桌讨论 Web App MVP》附件。

你现在的任务不是开发项目，而是作为一名资深产品架构师和软件架构师，完成本项目开发前的 SDD（Spec/Schema-Driven Development，契约/模型驱动开发）阶段文档。

非常重要：

1. 当前阶段禁止生成具体业务实现代码。
2. 不要假设项目中已经实现了任何功能。
3. 不要为了让文档显得完整而虚构开发结果。
4. 所有需求首先以附件中的招聘方原始作业要求为准。
5. 如果原始需求存在歧义，请明确写出“假设”与“设计决策”，不要偷偷替需求方做决定。
6. 文档必须服务于后续 Claude Code 开发，而不是写成泛泛的产品分析文章。
7. 所有文档使用中文 Markdown。
8. Mermaid 图必须保证语法尽量可直接渲染。
9. 控制 MVP 范围，避免主动扩展作业没有要求的复杂功能。
10. 技术方案优先考虑：可在 72 小时内由单人借助 AI 完成、结构清晰、易测试、易演示。

目前计划技术栈为：

前端：

* React
* TypeScript
* Vite
* Tailwind CSS
* shadcn/ui

后端：

* FastAPI
* Python
* SQLAlchemy
* SQLite
* Pydantic

实时通信：

* SSE

AI：

* DeepSeek V4 Pro
* Claude Code 作为主要 AI Coding 工作流

测试：

* pytest
* Playwright

如果你认为某个技术选型与业务需求明显冲突，请指出，但不要随意替换技术栈。

请分别生成以下 4 个 Markdown 文档。

---

# 文档一：docs/01-prd.md

定位：MVP 产品需求说明书。

必须包含：

## 1. 产品概述

* 产品名称
* 一句话定位
* 核心价值
* 目标用户
* 用户核心问题

## 2. MVP 目标

明确说明本次远程作业的 MVP 需要验证什么。

重点不是打造完整商业产品，而是验证：

* 用户是否能够快速创建一场 AI 圆桌
* AI 是否能生成差异化主持人与专家
* 多专家讨论是否具有非机械轮流的实时感
* 用户能否实时看到观点碰撞、共识与分歧
* 多个 Discussion 是否能够独立运行

## 3. 核心用户流程

请使用 Mermaid flowchart 表示：

首页
→ 发起讨论
→ 输入话题与人数
→ AI生成阵容
→ 用户确认
→ 进入演播厅
→ AI讨论进行
→ 实时更新Transcript/状态/共识分歧
→ 主持人总结
→ 讨论结束

同时用文字说明每一步。

## 4. 功能需求

按照模块分别描述：

### 首页

### 创建讨论

### 嘉宾生成

### 阵容确认

### 演播厅

### 专家实时状态

### Transcript

### 实时共识

### 实时分歧

### 主持人总结

### 多讨论并行

每个功能写：

* 目的
* 输入
* 核心行为
* 输出
* 关键异常情况

## 5. 非功能需求

至少包括：

* API Key 安全
* 多 Discussion 数据隔离
* 实时性
* 响应式布局
* 独立区域滚动
* 错误处理
* 可测试性
* 本地运行
* AI 输出结构稳定性

## 6. MVP 明确不做

主动控制范围。

例如根据原始题目判断是否不做：

* 用户账号
* 权限系统
* 云端部署
* 支付系统
* 长期记忆
* 音视频
* 真人语音
* 复杂社交功能
* 复杂搜索
* 真正无限自治 Agent

只保留本次验收需要的能力。

## 7. 验收标准

把招聘方需求转化成可以检查的 checklist。

每条尽量写成：
“当……时，系统应当……”

---

# 文档二：docs/02-domain-model.md

定位：领域模型与数据模型设计。

首先分析核心领域概念。

至少考虑以下实体：

* Discussion
* Participant
* Utterance
* Insight

如果确实有必要，可以加入其他轻量实体，但必须解释为什么需要。

## 1. 领域边界

说明 Discussion 为什么是主要聚合边界。

强调：

每一场 Discussion 的：

* Participants
* Utterances
* Insights
* Runtime State
* Event Stream

必须与其他 Discussion 隔离。

## 2. Discussion 生命周期

建议考虑：

DRAFT
→ CAST_READY
→ RUNNING
→ FINISHED

判断是否需要 FAILED / STOPPED 等状态。

请使用 Mermaid stateDiagram-v2。

说明：

* 每个状态允许做什么
* 什么事件触发状态转换
* 不合法状态转换如何处理

## 3. 实体定义

为每个实体给出：

* 职责
* 字段
* 数据类型
* 是否必填
* 约束
* 字段含义

Participant 至少考虑：

* id
* discussion_id
* role
* name
* profession
* title
* stance
* color
* runtime_status
* public_focus

Utterance 至少考虑：

* id
* discussion_id
* participant_id
* sequence
* content
* created_at

Insight 至少考虑：

* id
* discussion_id
* type
* content
* active
* created_at
* updated_at

请自行判断这些字段是否合理，并优化，而不是机械照抄。

## 4. ER 图

使用 Mermaid erDiagram。

必须明确：
Discussion
与
Participant
Utterance
Insight

之间关系。

## 5. 领域规则

至少明确：

* 每场讨论必须有且只有一个主持人
* 专家人数满足创建参数
* Participant 只能属于一个 Discussion
* Utterance 必须属于一个 Discussion 和一个 Participant
* Insight 只能属于一个 Discussion
* 不同 Discussion 数据禁止互相引用
* 已结束 Discussion 不继续自动生成发言

补充你认为真正必要的规则。

## 6. 运行时状态与持久化状态

特别区分：

数据库中需要持久化的数据

与

运行过程中存在于内存中的：

* DiscussionRunner
* SSE subscriber
* 当前 speaking participant
* pending task
  等。

避免把所有运行时信息都强行塞入 SQLite。

---

# 文档三：docs/03-api-contract.md

定位：前后端 API 契约。

设计一套最小、清晰、适合 MVP 的 REST + SSE API。

优先考虑以下接口，但请根据需求进行合理调整：

GET /api/discussions

POST /api/discussions

GET /api/discussions/{discussion_id}

POST /api/discussions/{discussion_id}/generate-cast

POST /api/discussions/{discussion_id}/confirm

POST /api/discussions/{discussion_id}/start

POST /api/discussions/{discussion_id}/stop

GET /api/discussions/{discussion_id}/events

每个接口必须写：

* 用途
* 请求方法
* URL
* Path 参数
* Request Body
* Response Body
* HTTP Status
* 失败情况

所有 JSON 示例必须是结构化、可直接指导 Pydantic Schema 实现的。

特别设计 SSE Event Contract。

至少考虑：

participant.status.changed

utterance.created

insights.updated

discussion.finished

discussion.error

每种事件给出：

event name

data schema

JSON 示例

明确所有事件必须包含 discussion_id。

说明前端如何根据 event type 更新局部状态。

另外定义统一错误格式，例如：

{
"error": {
"code": "...",
"message": "...",
"details": {}
}
}

最后提供一个：

“API 与领域模型对应关系表”。

---

# 文档四：docs/04-architecture.md

定位：系统架构与核心 AI 调度设计。

## 1. 总体架构

使用 Mermaid flowchart。

建议架构层次：

React Frontend

↓

FastAPI REST API

↓

Application / Domain Services

↓

Discussion Orchestrator

↓

LLM Provider

↓

DeepSeek V4 Pro

并包含：

SQLite

SSE Event Stream

## 2. 目录结构建议

给出前后端目录结构。

要求：

* 不要过度分层
* 但需要体现 domain / service / llm / runtime / api 的职责差异
* 适合一个 72 小时 MVP

## 3. LLM Provider 抽象

设计：

LLMProvider

DeepSeekLLMProvider

FakeLLMProvider

说明为什么测试环境不能直接依赖真实大模型 API。

## 4. AI 核心模块

重点设计三个核心模块：

### CastGenerator

负责：
话题
→ 主持人 + 专家阵容

### FloorScheduler

负责：
当前 Discussion 状态

* 最近 Transcript
* 专家立场
* 最近发言历史

→ 决定下一位发言者及发言意图

禁止机械固定轮询。

内部可以存在：

* answer
* supplement
* challenge
* rebuttal
* question

但这些内部事件不得直接出现在 Transcript。

### InsightExtractor

负责：
根据新增发言持续增量维护：

* Consensus
* Disagreement

避免每轮简单无限新增重复观点。

## 5. DiscussionRunner

重点设计每个 Discussion 独立 Runner。

说明类似：

Discussion A
→ Runner A
→ Event Stream A

Discussion B
→ Runner B
→ Event Stream B

如何保证并行运行时不串场。

## 6. 单轮讨论流程

用 Mermaid sequenceDiagram 表示：

Runner
→ FloorScheduler
→ LLM
→ Speaker
→ 保存 Utterance
→ InsightExtractor
→ SQLite
→ SSE
→ Frontend

## 7. 专家状态设计

只允许向用户展示：

* 待机
* 准备发言
* 发言中

以及公开的：
public_focus

例如：
“正在关注：方案实际落地成本”

禁止展示隐藏 Chain-of-Thought。

请明确这一安全边界。

## 8. 多讨论隔离

分别从以下层面说明：

* Database
* Application Service
* DiscussionRunner
* SSE
* Frontend State

如何通过 discussion_id 隔离。

## 9. AI 输出 Schema

解释为什么：
嘉宾生成
发言调度
共识分歧

应该要求大模型输出结构化 JSON，再在服务端进行 Pydantic 校验。

说明失败时的：

* validation
* retry
* fallback

策略。

不要设计无限重试。

## 10. 风险与权衡

至少分析：

* LLM 非确定性
* 多讨论同时调用模型产生的并发问题
* SSE 断线
* AI 返回非法 JSON
* AI 发言过长
* 专家立场趋同
* 机械轮流发言
* 共识/分歧无限重复
* 页面状态和后端不同步
* SQLite 并发限制

每一项写：
风险
→ MVP 应对方案
→ 后续生产环境如何改进

---

最后，请增加一个单独章节：

# 架构决策记录（ADR 摘要）

用表格列出至少 8 个重要决策。

格式：

| 决策 | 选择 | 原因 | 被放弃方案 |
| -- | -- | -- | ----- |

至少覆盖：

* React
* FastAPI
* SQLite
* SSE 而非 WebSocket
* Discussion 作为隔离边界
* 独立 DiscussionRunner
* LLMProvider 抽象
* Structured Output
* pytest
* Playwright

---

输出要求：

不要把四篇文档混成一篇长文章。

按照下面形式输出：

===== docs/01-prd.md =====

完整内容

===== docs/02-domain-model.md =====

完整内容

===== docs/03-api-contract.md =====

完整内容

===== docs/04-architecture.md =====

完整内容

每篇文档应达到真正可以放进 Git 仓库、供后续 Claude Code 阅读并据此开发的程度。

不要使用“后续可以考虑……”来逃避当前必须做出的 MVP 决策。

但对于原始作业没有明确规定、需要我们自行选择的地方，请明确标注：

> 设计假设

或：

> 架构决策

不要伪装成招聘方原始要求。

最后额外输出：

## 需要开发者人工确认的事项

仅列出你认为在正式开始编码前，开发者本人必须判断的 5 个以内关键问题，不要列无关问题。

```

```
继续生成 `docs/05-ui-design.md`。
基于前面已经完成的 PRD、领域模型、API 契约和架构文档，进入 DDD 阶段，完成 AI Panel Studio 的 UI/UX 设计文档。
重点设计首页、创建讨论、嘉宾确认、演播厅、结束状态，以及超宽屏、普通桌面、窄屏下的响应式布局。演播厅要有“AI 圆桌直播/演播厅”的感觉，Transcript 是视觉中心，专家状态、共识和分歧实时可见。
同时定义核心组件、状态反馈、Loading/Error、独立滚动、Transcript 自动滚动、颜色与排版规则，以及 UI UX Pro Max 后续实现时需要遵守的设计约束。
不要写实现代码，不要修改前面已经确定的产品流程和技术架构。
```



```
继续生成 `docs/06-testing-strategy.md`。
基于前面所有已完成文档，进入 TDD + E2E 测试设计阶段。
重点设计 CastGenerator、FloorScheduler、InsightExtractor、DiscussionRunner、多 Discussion 隔离、SSE、API 和 Chain-of-Thought 安全相关测试。
需要体现 Red → Green → Refactor 的真实 TDD 流程，并设计 FakeLLMProvider，使核心测试不依赖真实 DeepSeek API。
E2E 使用 Playwright，至少覆盖完整讨论流程、多 Discussion 隔离、响应式和一个关键错误场景。
当前只是开发前测试策略，不得虚构任何测试已经执行、通过或达到某个覆盖率。
```







审核（新对话）

```
请审核我接下来提供的 AI Panel Studio 项目文档。

背景：这是一个 AI 开发实习生的 72 小时远程作业，目标是完成一个基础但可运行的 MVP。招聘方重点考察 SDD、DDD、TDD、E2E的工程化开发过程，而不是要求做复杂生产系统。

请你以“技术面试官 + 软件架构 Reviewer”的视角进行审核。

审核目标不是润色文字，而是检查：

1. 文档之间是否存在前后矛盾。
2. 是否有功能、字段、状态、API 在不同文档中定义不一致。
3. 是否存在过度工程化，不符合 72 小时 MVP。
4. 是否偷偷扩展了原始作业没有要求的功能。
5. 是否有“文档里承诺了，但后续实现成本明显过高”的设计。
6. 是否有技术方案本身不合理或实现风险过高。
7. 是否遗漏招聘方明确要求的功能或交付物。
8. 是否存在 AI 常见的“看起来专业但实际上没有必要”的设计。
9. 是否有文档提前声称某功能、测试、结果已经实现或通过。
10. SDD → DDD → TDD → E2E 的逻辑链条是否成立。
11. 是否能够支持以下最小 MVP：

- 创建 Discussion
- 根据话题生成主持人和专家
- 确认阵容
- 开始讨论
- 非机械轮流发言
- 实时 Transcript
- 专家状态
- 实时共识 / 分歧
- 多 Discussion 隔离
- 主持人总结
- SSE 实时更新

12. 是否存在为了“生产级”而引入 Redis、消息队列、复杂 Agent Framework、复杂恢复机制、复杂缓存等不必要设计。

审核时请特别检查以下一致性：

- Discussion 状态机
- expert\_count 范围
- 最大讨论发言次数
- Participant 字段
- Utterance 字段
- Insight 字段
- API URL
- Request / Response Schema
- SSE Event 名称和 payload
- DiscussionRunner 生命周期
- Runtime State 与 SQLite 持久化边界
- 首页是否展示 FINISHED Discussion
- Confirm Cast 与 Start Discussion 的关系
- Summary 生成失败时的降级方案
- 多 Discussion 的 discussion\_id 隔离
- FakeLLMProvider 的测试边界
- Chain-of-Thought 不可展示原则

请坚持以下原则：

- 这是面试 MVP，不是正式商业产品。
- 优先简单、清晰、可运行、可测试。
- 能用一个简单方案解决的，不建议复杂架构。
- 不要因为“更专业”而增加实现负担。
- 如果某个设计虽然正确，但对于本次作业明显过度，也要指出。
- 不要擅自增加新功能。

请按下面格式输出。

# 一、总体结论

给出：

- 整体是否可以进入开发
- 最大的 3 个问题
- 当前复杂度是否适合 72 小时 MVP

# 二、必须修改的问题

只列会导致：

- 实现冲突
- 功能错误
- 无法验收
- 明显偏离题目
- 工作量失控

的问题。

每个问题写：

- 问题位置
- 当前定义
- 为什么有问题
- 建议统一成什么

# 三、建议简化的问题

找出过度工程设计。

每项说明：

当前方案\
→ 建议删减后的 MVP 方案

# 四、文档之间的冲突

按：

PRD\
Domain Model\
API Contract\
Architecture\
UI Design\
Testing Strategy

逐项检查。

如果没有冲突，明确写“未发现明显冲突”。

# 五、遗漏的招聘要求

只根据原始作业要求检查是否有遗漏。

不要自行增加要求。

# 六、最终建议的 MVP 边界

用非常简洁的方式重新列出：

必须实现\
可选\
明确不做

# 七、开发前最终 Checklist

给出一个不超过 20 项的 checklist。

只有这些项确认无误后才建议正式开始写代码。

最后请给出结论：

“可以开始开发”

或

“建议先修改文档后再开发”。

注意：

不要直接重写整套文档。

优先指出问题和精确修改建议。

如果只是措辞问题而不影响实现，不要浪费篇幅。

审核重点是：一致性、可实现性、MVP 边界和招聘题覆盖率。
```


























```

```




```

```




```

```



```

```



```

```



