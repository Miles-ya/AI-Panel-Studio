# AI Panel Studio

> **License: Evaluation Only.** This repository is provided solely for recruitment and technical assessment. Commercial use and production use are not permitted.

See [LICENSE](LICENSE) for the full terms.

AI 圆桌讨论 Web App MVP。用户输入议题并生成主持人与专家阵容，在实时演播厅中观看多角色讨论、共识与分歧提炼。

## 项目结构

```text
frontend/   前端应用：页面、组件、客户端状态与 SSE 展示
backend/    后端应用：API、领域逻辑、SQLite、LLM 调用与事件流
docs/       产品、领域模型、API 契约和架构文档
```

## 当前状态

项目已完成 MVP 的产品与工程设计文档，前后端目录已建立，具体技术实现待补充。

## 设计文档

- `docs/01-prd.md`：产品需求与验收标准
- `docs/02-domain-model.md`：领域实体、状态机与业务不变量
- `docs/03-api-contract.md`：REST API 与 SSE 事件契约
- `docs/04-architecture.md`：分层架构、实时机制与测试策略

## 本地开发

首次安装依赖：

```bash
npm install
cd backend && uv sync --all-extras && cd ..
```

在 `backend/.env` 配置模型密钥后，从项目根目录一键启动前后端：

```bash
npm run dev
```

也可以单独启动：

```bash
npm run dev:backend
npm run dev:frontend
```

后端会自动读取 `backend/.env`，默认运行在 `http://127.0.0.1:8000`；前端地址会显示在终端中。

## 安全说明

模型 API Key 只能配置在后端环境变量中，不得提交到 Git 或暴露给浏览器端。
