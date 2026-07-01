# Docker 部署指南

## 服务架构

```
docker-compose.yml
│
├── postgres (16-alpine)     → :5432    关系数据库
├── etcd (v3.5)              → :2379    Milvus 元数据
├── minio (RELEASE)          → :9000    Milvus 对象存储
├── milvus (v2.4)            → :19530   向量数据库
│   └── attu (v2.4)          → :8001    Milvus GUI (可选)
├── backend (FastAPI)        → :8000    后端 API
└── frontend (Next.js)       → :3000    前端页面
```

## 快速启动

```bash
# 1. 配置环境变量
cp docker/.env.docker .env
# 编辑 .env 填入：
#   OPENAI_API_KEY=sk-your-deepseek-key
#   EMBEDDING_API_KEY=sk-your-openai-key

# 2. 启动所有服务
docker compose up -d

# 3. 查看启动日志
docker compose logs -f backend

# 4. 创建管理员账户
curl -s -X POST http://localhost:8000/api/auth/admin/create \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Windows PowerShell:
Invoke-WebRequest -Uri http://localhost:8000/api/auth/admin/create -Method Post -ContentType "application/json" -Body '{"username":"admin","password":"admin123"}'

# 5. 打开页面
#    用户端: http://localhost:3000
#    管理端: http://localhost:3000/admin/login
#    Milvus GUI: http://localhost:8001
```

## 仅启动数据库（本地开发前后端）

```bash
docker compose up -d postgres milvus etcd minio

# 然后本地启动前后端
# 记得修改 .env 中的 DATABASE_URL 和 MILVUS_HOST
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_KEY` | 空 | DeepSeek/OpenAI API Key |
| `OPENAI_BASE_URL` | `https://api.deepseek.com/v1` | LLM API 地址 |
| `LLM_MODEL` | `deepseek-v4-pro` | 模型名称 |
| `EMBEDDING_BASE_URL` | `https://api.openai.com/v1` | 嵌入 API 地址 |
| `EMBEDDING_API_KEY` | 空 | 嵌入 API Key |
| `MAX_BUDGET_PER_SESSION_CNY` | `15.0` | 每会话预算上限 |
| `JWT_SECRET` | — | JWT 签名密钥 |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | 前端 API 地址 |

## 常用命令

```bash
# 停止所有服务
docker compose down

# 停止并清理数据卷
docker compose down -v

# 重建某服务
docker compose up -d --build backend

# 查看日志
docker compose logs -f

# 进入容器
docker compose exec backend bash
docker compose exec postgres psql -U junshituan -d junshituan
```

## 数据持久化

| 数据 | Docker Volume | 主机路径 |
|------|--------------|----------|
| PostgreSQL | `postgres_data` | Docker 管理 |
| Milvus | `milvus_data` | Docker 管理 |
| 军师配置 | 绑定挂载 | `./backend/data/personas` |
| 上传文件 | 绑定挂载 | `./backend/data/uploads` |

## 升级与维护

```bash
# 拉取最新镜像
docker compose pull

# 重新构建并启动
docker compose up -d --build

# 数据库迁移（如果修改了模型）
docker compose exec backend python -c "from app.db.database import init_db; import asyncio; asyncio.run(init_db())"
```
