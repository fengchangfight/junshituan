# 开发环境搭建

## 前置要求

- Python 3.10+
- Node.js 20+
- Docker Desktop

## 1. 启动数据库 (Docker)

```bash
# 在项目根目录
docker compose up -d postgres milvus etcd minio
```

首次启动会拉取镜像，之后秒启。确认服务正常：

```bash
docker compose ps
# postgres, etcd, minio, milvus 都应该显示 Up / healthy
```

## 2. 安装后端

```bash
cd backend

# 创建独立虚拟环境
python -m venv venv
.\venv\Scripts\Activate.ps1    # Windows PowerShell
# source venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
cp .env.example .env
```

## 3. 配置环境变量

编辑 `backend/.env`，唯一必填是 DeepSeek API Key，其余保持默认：

```env
# ── 必填 ────────────────────────────────────────────
OPENAI_API_KEY=sk-your-deepseek-key

# ── LLM ─────────────────────────────────────────────
OPENAI_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro

# ── Database ────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://junshituan:junshituan_secret@localhost:5432/junshituan

# ── Milvus (Docker) ─────────────────────────────────
MILVUS_HOST=localhost
MILVUS_PORT=19530

# ── Embedding (本地 BGE，免费，CPU) ──────────────────
LOCAL_EMBEDDING=true
LOCAL_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
# 首次启动自动下载 ~400MB 模型

# ── 预算 ────────────────────────────────────────────
MAX_BUDGET_PER_SESSION_CNY=15.0

# ── 其他 ────────────────────────────────────────────
JWT_SECRET=dev-secret
CORS_ORIGINS=["http://localhost:3000"]
```

### 切换到外部嵌入 API（备用）

若需更换嵌入方案：

```env
LOCAL_EMBEDDING=false
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=sk-your-openai-key
```

代码无需改动，切换后需重新消化知识库。

## 4. 安装前端

```bash
cd frontend
npm install
```

## 5. 启动服务

```powershell
# 后端（使用 venv 的 python）
Start-Process -FilePath "C:\Users\Administrator\test\junshituan\backend\venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload" -WorkingDirectory "C:\Users\Administrator\test\junshituan\backend"

# 前端
Start-Process -FilePath "cmd" -ArgumentList "/c", "npm run dev" -WorkingDirectory "C:\Users\Administrator\test\junshituan\frontend"
```

或者激活 venv 后直接跑：
```powershell
cd backend
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 6. 创建管理员

```bash
curl -s -X POST http://localhost:8000/api/auth/admin/create \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Windows PowerShell:
Invoke-WebRequest -Uri http://localhost:8000/api/auth/admin/create `
  -Method POST -ContentType "application/json" `
  -Body '{"username":"admin","password":"admin123"}'
```

## 7. 打开

- 用户端：http://localhost:3000
- 管理端：http://localhost:3000/admin/login
- Milvus GUI (Attu)：http://localhost:8001（如果启动了 attu 容器）

---

## 目录结构

```
backend/
├── app/
│   ├── main.py                 # FastAPI 入口
│   ├── api/                    # API 路由层
│   │   ├── advisors.py         # 公共军师接口
│   │   ├── council.py          # 会话/聊天接口
│   │   ├── auth.py             # 认证接口
│   │   └── admin/advisors.py   # 管理员 KB 管理
│   ├── core/                   # 核心模块
│   │   ├── config.py           # 全局配置 (Pydantic Settings)
│   │   ├── llm_client.py       # LLM 客户端封装
│   │   ├── embedding.py        # 嵌入服务 (本地BGE / API切换)
│   │   └── security.py         # JWT 认证中间件
│   ├── db/
│   │   └── database.py         # SQLAlchemy 异步引擎
│   ├── models/
│   │   ├── db_models.py        # SQLAlchemy ORM 模型
│   │   └── schemas.py          # Pydantic 请求/响应模型
│   └── services/
│       ├── agent/              # LangGraph Agent 系统
│       │   ├── base_agent.py   # Agent 状态机模板
│       │   ├── sub_agent.py    # 子 Agent 池
│       │   └── agent_registry.py # Agent 生命周期管理
│       ├── ingestion/          # 知识摄入
│       │   ├── pipeline.py     # 摄入管道 (dense + BM25)
│       │   └── milvus_store.py # Milvus 向量库
│       ├── memory/             # 记忆与上下文
│       │   ├── user_memory.py  # 持久记忆
│       │   ├── session_store.py # 会话持久化
│       │   └── context_manager.py # 上下文压缩
│       ├── budget_manager.py   # 预算管理
│       ├── council_service.py  # 议事厅编排
│       ├── persona_engine.py   # Persona 引擎
│       └── skill_engine.py     # Skill 引擎 (v2)
├── data/
│   ├── personas/               # 军师 YAML 配置
│   ├── skills/                 # 军师 Skill YAML (v2)
│   ├── corpus/                 # 著作原文 (按 persona_id 分目录)
│   └── uploads/                # 上传文件
└── scripts/
    ├── ingest.py               # CLI 摄入工具
    └── distill_skill.py        # Skill 蒸馏工具 (v2)

frontend/
├── src/
│   ├── app/
│   │   ├── page.tsx            # 首页：军师大厅
│   │   ├── council/page.tsx    # 群聊会议室
│   │   └── admin/              # 管理后台
│   │       ├── page.tsx        # 管理面板
│   │       ├── login/page.tsx  # 登录
│   │       └── advisors/       # 知识库管理
│   │           ├── page.tsx    # 军师列表
│   │           └── [id]/page.tsx # 单个军师 KB
│   ├── components/
│   │   ├── AdvisorCard/        # 军师选择卡片
│   │   └── ChatRoom/           # 聊天组件
│   └── lib/
│       ├── api.ts              # API 客户端
│       └── types.ts            # TypeScript 类型
├── tailwind.config.ts          # Tailwind 主题
└── next.config.js
```

## 常见问题

### Q: pip 安装报依赖冲突？
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Q: Milvus 连不上？
```bash
docker compose ps milvus    # 确认是 healthy 状态
docker compose logs milvus  # 查看日志
```

### Q: Docker 服务启动后后端还是连不上数据库？
确认 `.env` 中 `DATABASE_URL` 的 host 是 `localhost`（本地开发），不是 `postgres`（Docker 内部）。

### Q: 嵌入模型首次启动慢？
`LOCAL_EMBEDDING=true` 时首次启动下载 BGE 模型 (~400MB)。后续秒开。

### Q: 如何清空数据库重来？
```bash
# PostgreSQL
docker compose exec postgres psql -U junshituan -d junshituan -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# 重启后端自动重建表
```

### Q: 前端 API 404？
确认 `NEXT_PUBLIC_API_URL=http://localhost:8000`（`frontend/.env.local` 可覆盖）。
