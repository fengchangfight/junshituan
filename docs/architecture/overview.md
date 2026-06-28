# 系统架构总览

## 项目定位

军师团是一个基于大语言模型的虚拟顾问系统。用户将历史人物（哲学家、军事家、企业家等）组成"议事团"，向他们提问，每个军师按照该人物的思维方式、语言风格和知识体系进行回答。

## 技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| 前端 | Next.js 14 + Tailwind CSS + Framer Motion | 军师大厅、群聊会议室、管理后台 |
| 后端 | Python FastAPI | REST API + SSE 流式响应 |
| Agent | LangGraph | 每个军师对应一个状态机 Agent |
| 向量库 | Milvus | 知识库检索（RAG） |
| 关系库 | PostgreSQL / SQLite | 用户、会话、记忆持久化 |
| LLM | DeepSeek API (OpenAI 兼容) | 对话生成、推理、嵌入 |
| 容器 | Docker Compose | 一键部署 |

## 系统分层

```
┌──────────────────────────────────────────────────┐
│                前端 (Next.js)                      │
│  /              → 军师大厅 (选择军师)              │
│  /council       → 群聊会议室 (WeChat风格)          │
│  /admin         → 管理后台 (知识库管理)            │
└────────────────────┬─────────────────────────────┘
                     │ HTTP + SSE
┌────────────────────▼─────────────────────────────┐
│              API 层 (FastAPI)                      │
│  /api/advisors  → 军师列表                        │
│  /api/council   → 会话管理 + 聊天                  │
│  /api/auth      → 认证                             │
│  /api/admin     → 知识库管理                       │
└────────┬───────────────────────────┬──────────────┘
         │                           │
┌────────▼──────────┐    ┌───────────▼──────────────┐
│   Agent 系统      │    │   知识库系统              │
│  ─────────────────│    │  ────────────────────────│
│  LangGraph 状态机 │    │  LlamaIndex 摄入管道     │
│  子Agent 派发     │    │  Milvus 向量检索         │
│  上下文压缩       │    │  文档管理 (md/txt仅限)   │
└────────┬──────────┘    └───────────┬──────────────┘
         │                           │
┌────────▼───────────────────────────▼──────────────┐
│              持久化层                              │
│  ────────────────────────────────────────────────│
│  PostgreSQL/SQLite: 用户/会话/记忆                 │
│  Milvus:         向量索引                          │
│  LangGraph Checkpointer: Agent 状态快照           │
└───────────────────────────────────────────────────┘
```

## 核心数据流

```
用户提问
  │
  ▼
CouncilService.ask_council()
  │
  ├─ 1. 预算检查 (BudgetManager)
  ├─ 2. 加载用户记忆 (UserMemoryService)
  ├─ 3. 并行调用各军师 Agent
  │     │
  │     ▼
  │   AdvisorAgentGraph (LangGraph)
  │     │
  │     ├─ understand  → 解析问题
  │     ├─ retrieve    → Milvus 检索知识
  │     ├─ reason      → LLM 推理分析
  │     ├─ sub_agent   → 派发子任务 (可选)
  │     └─ respond     → 生成回答
  │
  ├─ 4. SSE 流式推送到前端
  ├─ 5. 提取新记忆 (Memory extraction)
  ├─ 6. 压缩旧上下文 (Context compression)
  └─ 7. 持久化预算状态
```

## 目录结构

```
junshituan/
├── docs/                    # 项目文档
├── frontend/                # Next.js 前端
│   ├── src/
│   │   ├── app/             # 页面路由
│   │   │   ├── page.tsx         # 军师大厅
│   │   │   ├── council/page.tsx # 群聊会议室
│   │   │   └── admin/           # 管理后台
│   │   ├── components/      # UI 组件
│   │   └── lib/             # API 客户端、类型
│   └── Dockerfile
├── backend/                 # Python FastAPI 后端
│   ├── app/
│   │   ├── api/             # API 路由
│   │   │   └── admin/       # 管理端 API
│   │   ├── core/            # 配置、安全、LLM客户端
│   │   ├── db/              # 数据库连接
│   │   ├── models/          # 数据模型 (SQLAlchemy + Pydantic)
│   │   └── services/        # 核心业务逻辑
│   │       ├── agent/       # LangGraph Agent 系统
│   │       ├── ingestion/   # 知识摄入管道
│   │       └── memory/      # 记忆、会话、上下文管理
│   ├── data/
│   │   ├── personas/        # 军师 YAML 配置
│   │   └── corpus/          # 著作原文语料
│   └── Dockerfile
├── docker/                  # Docker 配置
├── docker-compose.yml       # 服务编排
└── AGENTS.md                # AI Agent 操作规则
```
