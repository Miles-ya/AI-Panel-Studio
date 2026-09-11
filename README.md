# AI Panel Studio

> **License: Evaluation Only.** This repository is provided solely for recruitment and technical assessment. Commercial and production use are not permitted. See [LICENSE](LICENSE).

AI 圆桌讨论 Web App MVP。用户创建议题、生成并确认主持人与专家阵容，然后在演播厅观看实时公开发言、共识与分歧提炼，以及主持人自然语言总结。

## 已实现能力

- 创建 Discussion，设置议题与 2–8 名专家人数。
- 通过 DeepSeek 或确定性的 Fake Provider 生成主持人和专家阵容，并在开始前确认阵容。
- 通过 REST 获取讨论快照；通过 SSE 接收嘉宾公开状态、发言、共识/分歧和结束事件。
- 演播厅以横向嘉宾舞台轨道、Transcript、共识/分歧与总结的阅读顺序展示讨论；已结束讨论可回放。
- 使用 SQLite 持久化 Discussion、Participant、Utterance 和 Insight；首次初始化会写入 5 场完整的已结束样例讨论。
- 前端包含异常状态和布局回归测试；Playwright E2E 使用 Fake Provider 与临时 SQLite 数据库，不调用真实模型或修改开发数据库。

## 项目结构

```text
backend/                 FastAPI、领域逻辑、SQLite、LLM Provider 与 SSE
backend/.env.example     后端环境变量的唯一模板
backend/tests/           pytest 单元与集成测试
frontend/                React + Vite 前端、客户端状态与演播厅 UI
e2e/                     Playwright UI 回归与真实前后端流程测试
docs/                    PRD、领域模型、API、架构和 UI 设计文档
```

## 快速开始

要求：Node.js、Python 3.12+，以及 [uv](https://docs.astral.sh/uv/)。

```bash
npm install
cd backend && uv sync --all-extras && cp .env.example .env && cd ..
npm run dev
```

后端默认在 `http://127.0.0.1:8000` 运行；Vite 会在终端输出前端地址。首次访问后端时会创建默认 SQLite 数据库并写入 5 场可直接旁观的完整样例，每场均含阵容、4 条公开发言、共识、分歧和总结。初始化是幂等的，不会覆盖既有讨论。

也可以分别启动：

```bash
npm run dev:backend
npm run dev:frontend
```

## 后端配置与模型模式

只以 [backend/.env.example](backend/.env.example) 为后端配置模板；复制为 `backend/.env` 后再填写值。模型 API Key 只能保留在后端环境变量中，不能提交到 Git 或暴露给浏览器。

默认的真实模型模式：

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-pro
```

本地演示或测试可使用不访问网络、无需 API Key 的确定性 Fake Provider：

```env
LLM_PROVIDER=fake
FAKE_LLM_SUMMARY_MODE=success
```

`FAKE_LLM_SUMMARY_MODE=fallback_once` 可用于手工验证总结重试流程。`DATABASE_URL` 默认指向 `sqlite:///./data/ai_panel_studio.db`（相对于 `backend/` 运行目录）；需要隔离数据时可改为其他 SQLite 路径。

前端默认连接 `http://127.0.0.1:8000`。仅当前后端部署在不同地址时，才在前端运行环境中设置：

```env
VITE_API_BASE_URL=https://your-api.example.com
```

## API 概览

所有接口以 `/api` 为前缀，完整请求与事件载荷见 [docs/03-api-contract.md](docs/03-api-contract.md)。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/discussions` | 列出讨论 |
| `POST` | `/discussions` | 创建草稿 |
| `GET` | `/discussions/{id}` | 获取完整讨论快照 |
| `POST` | `/discussions/{id}/generate-cast` | 生成或重新生成阵容 |
| `POST` | `/discussions/{id}/confirm` | 确认阵容 |
| `POST` | `/discussions/{id}/start` | 开始讨论 |
| `POST` | `/discussions/{id}/stop` | 停止讨论并收束总结 |
| `POST` | `/discussions/{id}/retry-summary` | 重试降级的总结 |
| `GET` | `/discussions/{id}/events` | 订阅 SSE 实时事件 |

## 开发与质量命令

```bash
# 后端 pytest
npm run test:backend

# 前端 lint、typecheck 与 production build
npm run test:frontend

# Playwright：自动启动 Fake Provider 后端和指向它的前端
npm run test:e2e

# 全部质量检查
npm run quality
```

## 后续改进项

- 为真实 DeepSeek 凭据增加受控的端到端验收环境；默认测试继续使用 Fake Provider。
- 增加生产部署所需的鉴权、持久化备份、可观测性和更严格的跨域策略。
- 在不改变公开 API 与状态机的前提下，持续扩充无障碍与不同视口的人工验收。

## 设计文档

- [产品需求](docs/01-prd.md)
- [领域模型](docs/02-domain-model.md)
- [API 契约](docs/03-api-contract.md)
- [架构](docs/04-architecture.md)
- [UI 设计](docs/05-ui-design.md)
