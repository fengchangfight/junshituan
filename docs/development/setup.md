# 开发环境搭建

## 前置要求

- Python 3.10+
- Node.js 20+
- Docker Desktop (可选，用于 Milvus + PostgreSQL)

## 1. 克隆与安装

```bash
# 后端
cd backend
cp .env.example .env          # 填入 OPENAI_API_KEY
pip install -r requirements.txt

# 前端
cd frontend
npm install
```

## 2. 配置环境变量

编辑 `backend/.env`：

```env
# 必填
OPENAI_API_KEY=sk-your-deepseek-key

# DeepSeek (默认)
OPENAI_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro

# OpenAI 嵌入 (DeepSeek 不支持嵌入)
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=sk-your-openai-key

# 数据库 (SQLite 开发模式，零配置)
DATABASE_URL=sqlite+aiosqlite:///./data/junshituan.db

# Milvus (Lite 嵌入式，零配置)
MILVUS_LITE=true

# 其他
JWT_SECRET=dev-secret
CORS_ORIGINS=["http://localhost:3000"]
```

## 3. 启动服务

```powershell
# 后端
Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload" -WorkingDirectory "C:\Users\Administrator\test\junshituan\backend"

# 前端
Start-Process -FilePath "cmd" -ArgumentList "/c", "npm run dev" -WorkingDirectory "C:\Users\Administrator\test\junshituan\frontend"
```

## 4. 创建管理员

```bash
curl -X POST http://localhost:8000/api/auth/admin/create \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

## 5. 打开前端

- 用户端：http://localhost:3000
- 管理端：http://localhost:3000/admin/login

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
│       │   ├── pipeline.py     # LlamaIndex 摄入管道
│       │   └── milvus_store.py # Milvus 向量库封装
│       ├── memory/             # 记忆与上下文
│       │   ├── user_memory.py  # Hermes 风格持久记忆
│       │   ├── session_store.py # 会话持久化
│       │   └── context_manager.py # 上下文压缩管理
│       ├── budget_manager.py   # 预算管理
│       ├── council_service.py  # 议事厅编排
│       └── persona_engine.py   # Persona 引擎
├── data/
│   ├── personas/               # 军师 YAML 配置
│   ├── corpus/                 # 著作原文 (按 persona_id 分目录)
│   └── uploads/                # 上传文件
└── scripts/
    └── ingest.py               # CLI 摄入工具

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

### Q: SQLite 数据库在哪里？
`backend/data/junshituan.db` — 服务启动时自动创建。

### Q: 如何重置数据库？
删除 `backend/data/junshituan.db` 即可。

### Q: Milvus 启动失败？
检查 `MILVUS_LITE=true` 是否正确。Windows 下 Milvus Lite 可能不稳定，建议用 Docker 模式。

### Q: 前端 API 请求失败？
确认 `NEXT_PUBLIC_API_URL` 指向后端地址（默认 `http://localhost:8000`）。
