# 军师团 (Junshituan) — AI Advisory Council

> 召集历史智者，组建专属顾问团。

一个 AI 赋能的虚拟议事厅。选择 1-5 位历史/现代名人组成顾问团，向他们提问——每位军师以各自独特的思维框架、语言风格和著作知识独立作答，仿佛你真的在与诸葛亮、孙子、王阳明围坐议事。

![军师选择](军师board.png)

---

## 特性

- **智能军师引擎**：每位军师拥有完整的 AI 人格配置——思维框架、语言风格、核心信条、知识边界，以及可选的深度认知操作系统（心智模型、决策启发式、表达 DNA、自查 checkpoint）
- **一键智能创建**：只需输入名字（如「黑格尔」「鲁迅」），LLM 自动补全全部配置
- **知识库消化**：上传著作(.md/.txt)→ 向量化摄入(Milvus)→ 回答时检索原文
- **混合检索**：Dense (BGE) + Sparse (BM25) 混合搜索，权重 6:4
- **流式群聊**：SSE 流式输出，多位军师同时作答，类 Teams 侧边栏显示军师状态
- **四级权限**：超级管理员 / 管理员 / 只读 / 用户

![对话界面](chatsample1.png)

---

## 技术架构

```text
┌─ Frontend (Next.js 14) ─────────────────────────────┐
│  军师选择 → 创建议事厅 → 流式群聊 ← 议事记录管理        │
└──────────────────────────┬──────────────────────────┘
                           │ REST + SSE
┌─ Backend (FastAPI) ──────┼──────────────────────────┐
│  /api/advisors  /api/auth  /api/council  /api/admin  │
│  PersonaEngine  SkillEngine   AgentRegistry          │
│  BudgetManager  MemoryExtractor                      │
└──────────────────────────┬──────────────────────────┘
                           │
┌─ Data Layer ─────────────┼──────────────────────────┐
│  PostgreSQL  ─   Milvus (向量库)  ─  docstore       │
└──────────────────────────────────────────────────────┘
```

| 组件 | 技术 |
|---|---|
| 前端 | Next.js 14 · TypeScript · Tailwind CSS · Framer Motion |
| 后端 | FastAPI · LangGraph · llama-index · SQLAlchemy async |
| 向量库 | Milvus 2.4 (Dense + Sparse hybrid) |
| 数据库 | PostgreSQL 16 |
| 嵌入 | BGE-small-zh-v1.5 (本地, free) / OpenAI text-embedding-3-small |
| LLM | DeepSeek V4 / 兼容 OpenAI 接口 |

---

## 快速开始

### 前置条件
- Docker Desktop
- Python 3.10+
- Node.js 18+

### 1. 启动基础设施

```bash
cp docker/.env.docker .env
# 编辑 .env 填入 OPENAI_API_KEY

docker compose up -d       # PostgreSQL + Milvus + etcd + MinIO
```

### 2. 启动后端

```bash
cd backend
cp .env.example .env
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev                 # http://localhost:3000
```

### 4. 创建管理员

```bash
curl -s -X POST http://localhost:8000/api/auth/admin/create \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Windows PowerShell:
iwr -Uri http://localhost:8000/api/auth/admin/create -Method Post `
  -ContentType "application/json" -Body '{"username":"admin","password":"admin123"}'
```

### 5. 打开页面

- 用户端: http://localhost:3000
- 管理端: http://localhost:3000/admin/login
- Milvus GUI (attu): http://localhost:8001

---

## 管理后台

登录管理后台后可以：

1. **智能创建军师** — 输入名字，AI 自动生成完整人格配置
2. **上传文档** — 给军师提供著作 (.md/.txt)
3. **消化知识库** — 将文档向量化摄入 Milvus
4. **AI 充实** — 让 LLM 丰富思维框架、信条等配置
5. **AI 生成 Skill** — 自动生成深度认知操作系统
6. **能力预览** — 弹窗查看/编辑军师完整配置
7. **发布** — 军师出现在前台供用户选择

---

## 配置

主要配置项 (`backend/.env`)：

| 字段 | 说明 | 默认值 |
|---|---|---|
| `OPENAI_API_KEY` | LLM API 密钥 | — |
| `OPENAI_BASE_URL` | LLM API 地址 | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | 模型名称 | `deepseek-v4-pro` |
| `LOCAL_EMBEDDING` | 使用本地嵌入模型 | `true` |
| `DATABASE_URL` | PostgreSQL 连接串 | `postgresql+asyncpg://...` |
| `JWT_SECRET` | JWT 签名密钥 | 修改默认值 |

---

## License

MIT
