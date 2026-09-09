# AI Panel Studio MVP REST + SSE API 契约

> SDD 阶段基线｜v1.0。所有时间为 ISO 8601 UTC，ID 为 UUID 字符串，JSON 使用 `application/json`。

## 1. 通用约定

- API 前缀为 `/api`；MVP 不设计用户认证。
- 子资源只通过 Discussion 聚合访问，所有查询受 `discussion_id` 约束。
- Discussion 状态：`DRAFT`、`CAST_READY`、`RUNNING`、`FINISHED`、`FAILED`；Participant 状态：`idle`、`preparing`、`speaking`。
- 成功列表响应使用 `items`；时间均为 UTC；错误不包含密钥、提示词或隐藏推理。专家人数范围为 2–8，默认 4；每场最多 15 条公开发言。

### 统一错误格式

```json
{"error":{"code":"DISCUSSION_STATE_CONFLICT","message":"当前讨论状态不允许启动。","details":{"current_status":"DRAFT","required_status":"CAST_READY"}}}
```

`details` 可为 `{}`。常见映射：`400` 格式错误，`404` 不存在，`409` 状态/并发冲突，`422` 语义校验失败，`502` 模型上游失败，`503` 服务不可用。

## 2. REST 接口

### GET /api/discussions

- **用途**：首页读取全部 Discussion（含已结束讨论）。
- **Path 参数 / Request Body**：无。
- **Response 200**：

```json
{"items":[{"id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","topic":"企业应如何在 AI 自动化与员工发展之间取舍？","expert_count":4,"status":"RUNNING","participant_count":5,"updated_at":"2026-09-09T08:01:10Z"},{"id":"8db8ef39-0a18-4e6e-a90c-414b3e5ab067","topic":"AI 对教育公平的影响","expert_count":4,"status":"FINISHED","participant_count":5,"updated_at":"2026-09-09T07:30:00Z"}]}
```

- **失败情况**：`503` 存储不可用。默认按 `updated_at` 倒序返回全部状态。

### POST /api/discussions

- **用途**：创建草稿讨论。
- **Path 参数**：无。
- **Request Body**：`topic` 必填；`expert_count` 可选，缺省时后端写入默认值 4。

```json
{"topic":"企业应如何在 AI 自动化与员工发展之间取舍？","expert_count":4}
```

- **Response 201**：

```json
{"id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","topic":"企业应如何在 AI 自动化与员工发展之间取舍？","expert_count":4,"max_public_utterances":15,"status":"DRAFT","cast_confirmed":false,"cast_confirmed_at":null,"summary":null,"summary_status":"pending","error_code":null,"created_at":"2026-09-09T08:00:00Z","updated_at":"2026-09-09T08:00:00Z","started_at":null,"finished_at":null,"participants":[]}
```

- **失败情况**：`422 INVALID_TOPIC` 或 `INVALID_EXPERT_COUNT`（专家数不在 2–8）。

### GET /api/discussions/{discussion_id}

- **用途**：演播厅初始化、刷新和 SSE 每次连接后的权威聚合快照。
- **Path 参数**：`discussion_id`（UUID）。
- **Request Body**：无。
- **Response 200**：

```json
{"id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","topic":"企业应如何在 AI 自动化与员工发展之间取舍？","expert_count":4,"max_public_utterances":15,"status":"RUNNING","cast_confirmed":true,"cast_confirmed_at":"2026-09-09T08:00:08Z","summary":null,"summary_status":"pending","error_code":null,"created_at":"2026-09-09T08:00:00Z","updated_at":"2026-09-09T08:01:10Z","started_at":"2026-09-09T08:00:10Z","finished_at":null,"participants":[{"id":"p-mod","discussion_id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","role":"moderator","name":"林澄","profession":"科技记者","title":"前商业栏目主编","stance":"优先厘清决策边界","color":"#2563EB","runtime_status":"idle","public_focus":null},{"id":"p-002","discussion_id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","role":"expert","name":"周启明","profession":"组织发展顾问","title":"前人力战略负责人","stance":"自动化必须与员工转岗机制同步设计","color":"#F59E0B","runtime_status":"preparing","public_focus":"正在回应当前问题"},{"id":"p-003","discussion_id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","role":"expert","name":"沈言","profession":"财务战略顾问","title":"前企业转型负责人","stance":"应先验证可量化的投资回报","color":"#10B981","runtime_status":"idle","public_focus":null},{"id":"p-004","discussion_id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","role":"expert","name":"许宁","profession":"技术治理研究员","title":"AI 风险与合规顾问","stance":"应优先界定可审计的风险边界","color":"#EC4899","runtime_status":"idle","public_focus":null},{"id":"p-005","discussion_id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","role":"expert","name":"韩璟","profession":"运营转型顾问","title":"前共享服务负责人","stance":"从可逆流程开始试点","color":"#8B5CF6","runtime_status":"idle","public_focus":null}],"utterances":[{"id":"u-001","discussion_id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","participant_id":"p-mod","sequence":1,"content":"今天我们讨论自动化与员工发展的平衡。先请各位界定企业真正要优化的目标。","created_at":"2026-09-09T08:00:12Z"}],"insights":[{"id":"i-001","discussion_id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","type":"consensus","content":"自动化的评价不应只看短期降本。","active":true,"created_at":"2026-09-09T08:01:00Z","updated_at":"2026-09-09T08:01:00Z"}]}
```

- **失败情况**：`404 DISCUSSION_NOT_FOUND`。

### POST /api/discussions/{discussion_id}/generate-cast

- **用途**：首次生成或原子替换主持人与专家阵容。
- **Path 参数**：`discussion_id`；**Request Body**：无。
- **Response 200**：完整 Discussion 快照，状态 `CAST_READY`，Participant 恰有一名主持人和 `expert_count` 名专家，且 `cast_confirmed=false`。
- **失败情况**：仅 `DRAFT` 或 `CAST_READY` 可调用；其他状态 `409`。当为 `CAST_READY` 时，服务端先生成并完整校验，成功后单事务替换旧 Participant 并重置确认字段；`502/503` 或校验失败时旧阵容和确认状态必须保持不变。

### POST /api/discussions/{discussion_id}/confirm

- **用途**：确认当前阵容。
- **Path 参数**：`discussion_id`；**Request Body**：`{}`。
- **Response 200**：

```json
{"id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","status":"CAST_READY","cast_confirmed":true,"cast_confirmed_at":"2026-09-09T08:00:08Z","studio_path":"/discussions/d2a4e4d6-252e-4a1d-8bbc-6c8974da7001"}
```

- **失败情况**：`409` 不是 `CAST_READY`、阵容不完整或已确认。确认持久化确认字段但不自动发言，开始由 `/start` 显式触发。

### POST /api/discussions/{discussion_id}/start

- **用途**：启动独立 Runner。
- **Path 参数**：`discussion_id`；**Request Body**：`{}`。
- **Response 202**：

```json
{"id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","status":"RUNNING","started_at":"2026-09-09T08:00:10Z"}
```

- **失败情况**：仅 `CAST_READY + cast_confirmed=true` 可启动；未确认、已运行或已结束为 `409`。首条发言通过 SSE 推送。

### POST /api/discussions/{discussion_id}/stop

- **用途**：请求受控结束讨论。
- **Path 参数**：`discussion_id`；**Request Body**：`{}`。
- **Response 202**：`{"id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","status":"RUNNING","stop_requested":true}`。
- **失败情况**：`404`；`409` 非 `RUNNING`。Runner 在安全点收束，最终用 `discussion.finished` 通知。

### POST /api/discussions/{discussion_id}/retry-summary

- **用途**：对已降级的结束讨论重新生成主持人总结，不重启 Runner 或生成新发言。
- **Path 参数**：`discussion_id`；**Request Body**：`{}`。
- **Response 202**：`{"id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","status":"FINISHED","summary_status":"pending","retry_requested":true}`。
- **失败情况**：`404`；`409` 非 `FINISHED` 或 `summary_status` 不是 `fallback`；`503` 无法受理。成功或再次降级结果通过 `discussion.finished` 事件返回。

### GET /api/discussions/{discussion_id}/events

- **用途**：订阅一场讨论实时事件。
- **Path 参数**：`discussion_id`；**Request Body**：无。
- **Response 200**：`Content-Type: text/event-stream`、`Cache-Control: no-cache`；连接后先发 `discussion.snapshot`。
- **失败情况**：连接前 `404`；运行中以 `discussion.error` 报告。浏览器重连后服务端再次发送完整 snapshot；MVP 不提供事件回放、Last-Event-ID 或事件去重协议。

## 3. SSE Event Contract

事件格式为 `event: <name>` 与 `data: <JSON>`。每条 data 必含 `discussion_id`；客户端只更新该 ID 的局部状态，未知或跨场事件丢弃。MVP 的每次连接都从完整 snapshot 开始，不定义事件编号、回放或去重协议。

### discussion.snapshot

每次订阅的完整初始化快照。`discussion` 必须与 `GET /api/discussions/{discussion_id}` 的完整聚合 DTO 完全同构（包含确认字段、Participants、Utterances、Insights、总结字段），不可维护另一套缩减模型。前端连接或重连时以该 snapshot 覆盖本场状态。

```json
{"discussion_id":"c31f16e4-7bb1-4a37-a21b-d281ce70d9a4","discussion":{"id":"c31f16e4-7bb1-4a37-a21b-d281ce70d9a4","topic":"AI 对教育公平的影响","expert_count":2,"max_public_utterances":15,"status":"RUNNING","cast_confirmed":true,"cast_confirmed_at":"2026-09-09T08:10:08Z","summary":null,"summary_status":"pending","error_code":null,"created_at":"2026-09-09T08:10:00Z","updated_at":"2026-09-09T08:11:10Z","started_at":"2026-09-09T08:10:10Z","finished_at":null,"participants":[{"id":"p-cmod","discussion_id":"c31f16e4-7bb1-4a37-a21b-d281ce70d9a4","role":"moderator","name":"程远","profession":"教育记者","title":"教育科技栏目主编","stance":"先厘清公平的衡量标准","color":"#2563EB","runtime_status":"idle","public_focus":null},{"id":"p-c002","discussion_id":"c31f16e4-7bb1-4a37-a21b-d281ce70d9a4","role":"expert","name":"顾岚","profession":"教育政策研究员","title":"区域教育发展顾问","stance":"优先缩小资源可及性差距","color":"#F59E0B","runtime_status":"preparing","public_focus":"正在聚焦资源可及性"},{"id":"p-c003","discussion_id":"c31f16e4-7bb1-4a37-a21b-d281ce70d9a4","role":"expert","name":"罗川","profession":"学习科学研究者","title":"数字学习项目负责人","stance":"应同时检验学习效果差异","color":"#10B981","runtime_status":"idle","public_focus":null}],"utterances":[],"insights":[]}}
```

前端以其覆盖本场状态；无需维护事件回放或去重缓存。

### participant.status.changed

```json
{"discussion_id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","participant":{"id":"p-002","runtime_status":"preparing","public_focus":"正在聚焦转岗成本"},"occurred_at":"2026-09-09T08:01:12Z"}
```

前端按 participant ID 合并状态和 `public_focus`，不渲染未定义隐藏字段。

### utterance.created

```json
{"discussion_id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","utterance":{"id":"u-002","discussion_id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","participant_id":"p-002","sequence":2,"content":"若只以节省工时衡量，企业会低估转岗与复训成本。自动化应先从可逆、可衡量的流程开始。","created_at":"2026-09-09T08:01:15Z"}}
```

前端按 `sequence` 排列，并从 Participant 映射姓名、职业/Title、颜色。

### insights.updated

```json
{"discussion_id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","insights":[{"id":"i-001","discussion_id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","type":"consensus","content":"自动化的评价不应只看短期降本。","active":true,"created_at":"2026-09-09T08:01:16Z","updated_at":"2026-09-09T08:01:16Z"}],"occurred_at":"2026-09-09T08:01:16Z"}
```

该事件携带本场完整活跃集合；前端直接替换 Insights，再按 `type` 分区显示。

### discussion.finished

```json
{"discussion_id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","status":"FINISHED","summary":"本场讨论的共同判断是：自动化应服务于可衡量的业务价值，并配套员工转岗机制；分歧仍集中在投入节奏。","summary_status":"succeeded","finished_at":"2026-09-09T08:04:00Z"}
```

前端写入总结和状态，停止运行中动效；绝不显示模型 JSON 原文。

### discussion.error

```json
{"discussion_id":"d2a4e4d6-252e-4a1d-8bbc-6c8974da7001","final_status":"FAILED","error":{"code":"LLM_RESPONSE_VALIDATION_FAILED","message":"本轮讨论生成失败，系统已停止该讨论。","details":{}},"occurred_at":"2026-09-09T08:03:40Z"}
```

该事件只用于不可恢复 Runner/模型选择/发言失败；服务端必须先持久化 `FAILED` 再发送。前端保留现有内容并展示错误。Insight 提炼失败不发该事件、不改变 `RUNNING`。

## 4. API 与领域模型对应关系

| API / 事件 | 读取/写入领域对象 | 状态约束 |
| -- | -- | -- |
| `GET /discussions` | Discussion 列表投影 | 所有状态 |
| `POST /discussions` | Discussion | 创建 `DRAFT` |
| `GET /discussions/{id}` | Discussion 聚合快照 | 任意存在状态 |
| `generate-cast` | Discussion、Participant | `DRAFT` 首次生成；`CAST_READY` 原子替换并重置确认 |
| `confirm` | Discussion 确认字段 | 仅 `CAST_READY + cast_confirmed=false` |
| `start` | Discussion、DiscussionRunner | 仅 `CAST_READY + cast_confirmed=true` → `RUNNING` |
| `stop` | Runner、Discussion | 仅 `RUNNING`，最终 `FINISHED` |
| `retry-summary` | Discussion summary | 仅 `FINISHED` 且 `summary_status=fallback` |
| `participant.status.changed` | Participant 最新公开状态 | `RUNNING` |
| `utterance.created` | Utterance | `RUNNING` |
| `insights.updated` | Insight | `RUNNING` |
| `discussion.finished` | Discussion summary/status | `RUNNING` → `FINISHED` |
