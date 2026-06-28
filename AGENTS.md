# AGENTS.md - 军师团项目配置须知

> 完整文档在 [docs/](./docs/) 目录中。
> 架构设计：[docs/architecture/overview.md](./docs/architecture/overview.md)

## Windows PowerShell 服务器启动规则

**严禁使用 `Start-Process -NoNewWindow` 启动长时间运行的服务器进程**（如 uvicorn, next dev），这会导致进程附着在当前 shell 并使工具调用挂起。

### 正确做法：

1. **启动后端测试**（带超时自动终止）：
```powershell
$job = Start-Job -ScriptBlock { Set-Location -LiteralPath "C:\Users\Administrator\test\junshituan\backend"; python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 }
Start-Sleep -Seconds 3
try { Invoke-WebRequest -Uri "http://localhost:8000/api/health" -UseBasicParsing } catch { }
Stop-Job $job; Remove-Job $job
```

2. **生产启动**（新窗口，不阻塞）：
```powershell
Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload" -WorkingDirectory "path\to\backend"
```

3. **前端开发**（新窗口，不阻塞）：
```powershell
Start-Process -FilePath "cmd" -ArgumentList "/c", "npm run dev" -WorkingDirectory "path\to\frontend"
```

### 其他规则
- 不要在一个 bash 调用中同时启动服务器 + 测试请求，应分两步
- 测试完服务器后务必清理后台进程

---

## Docker 部署

### 服务架构
```
docker-compose.yml
├── postgres (16-alpine)  → :5432
├── etcd (v3.5)            → :2379 (Milvus 依赖)
├── minio (RELEASE)         → :9000 (Milvus 依赖)
├── milvus (v2.4)          → :19530 (向量库)
├── attu (v2.4)            → :8001 (Milvus GUI)
├── backend (FastAPI)      → :8000
└── frontend (Next.js)     → :3000
```

### 启动命令
```bash
# 1. 配置环境变量
cp docker/.env.docker .env
# 编辑 .env 填入 OPENAI_API_KEY

# 2. 启动所有服务
docker compose up -d

# 3. 仅启动数据库（本地开发用）
docker compose up -d postgres milvus etcd minio

# 4. 创建管理员账户
curl -X POST http://localhost:8000/api/auth/admin/create \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 5. 打开前端
#    用户端: http://localhost:3000
#    管理端: http://localhost:3000/admin/login
#    Milvus GUI: http://localhost:8001
```

---

## 项目命令

| 位置 | 命令 | 说明 |
|------|------|------|
| frontend/ | `npm run dev` | 前端开发 |
| frontend/ | `npm run build` | 前端构建 |
| backend/ | `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` | 后端开发 |
| backend/ | `python scripts/ingest.py [--persona <id>]` | 知识摄入 |
| backend/ | `pip install -r requirements.txt` | 安装Python依赖 |
| frontend/ | `npm install` | 安装Node依赖 |

---

## 知识库管理（.md / .txt 限定）

### 文件命名规则
- 文件名 = 唯一标识（`{persona_id}:{filename}` → SHA256 哈希前24位）
- 同名文件覆盖上传 → ID不变 → `updated_at` 更新 → `status = pending_reingest`
- 仅接受 `.md` 和 `.txt` 格式

### 管理工作流
```
1. 打开 /admin → 登录
2. /admin/advisors → 选择军师
3. /admin/advisors/[id]
   → 输入文件名（如 chuanxilu.md）
   → 粘贴内容 → 点击"上传文档"
   → 上传完成 → 点击"消化"
   → 消化完成 → 点击"发布"
4. 修改后重新上传同名文件 → 状态变为"待重新消化" → 再次点击"消化"
```
