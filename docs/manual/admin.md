# 管理员手册

## 登录

访问 `http://localhost:3000/admin/login`，使用管理员账户登录。

首次部署时通过 API 创建管理员：
```bash
curl -s -X POST http://localhost:8000/api/auth/admin/create \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Windows PowerShell:
Invoke-WebRequest -Uri http://localhost:8000/api/auth/admin/create -Method Post -ContentType "application/json" -Body '{"username":"admin","password":"admin123"}'
```

## 知识库管理流程

```
1. 打开管理面板 → 点击"知识库管理"
2. 选择军师 → 进入该军师的知识库页面
3. 输入文件名 (如 chuanxilu.md)
4. 粘贴文本内容
5. 点击"上传文档"
6. 上传完成后 → 点击"消化"按钮
7. 消化完成 (status=ready) → 点击"发布"
```

### 文件格式限制

- 仅接受 `.md`、`.txt`、`.markdown` 文件
- 文件名作为唯一标识，同名文件覆盖会触发重新消化

### 消化 (Ingest)

消化过程：
1. 文本切分（800字符/块）
2. 调用嵌入 API 生成向量（1536维）
3. 存入 Milvus 向量库

消化完成后军师状态变为 `ready`。

### 发布 (Publish)

发布后军师对全体用户可见，可在军师大厅中被选择。

### 修改知识库

```
1. 重新上传同名文件 → 覆盖 (status = pending_reingest)
2. 点击"消化" → 重建整个知识库索引
3. 无需重新发布 (已发布的保持发布状态)
```

## 军师状态一览

| 状态 | 图标 | 说明 |
|------|------|------|
| `empty` | ○ | 未上传任何文档 |
| `pending` | ○ | 已上传，等待消化 |
| `pending_reingest` | ○ | 已覆盖，需要重新消化 |
| `ingesting` | ◌ | 正在消化中 |
| `ready` | ● | 已消化，可以发布或使用 |
| `error` | ✕ | 消化失败，检查日志 |

## 添加新军师

1. 创建 `backend/data/personas/{new-id}.yaml`
2. 按照 [Persona YAML 规范](../architecture/persona-yaml.md) 填写内容
3. 重启后端服务（或等待自动重新加载）
4. 在管理后台为它上传文档、消化、发布

## 管理面板功能

| 功能 | 路径 | 说明 |
|------|------|------|
| 总览 | `/admin` | 功能入口 |
| KB 列表 | `/admin/advisors` | 所有军师及 KB 状态 |
| KB 编辑 | `/admin/advisors/[id]` | 上传/消化/发布 |
| 用户管理 | `/admin/users` | 即将推出 |
| 系统监控 | `/admin/stats` | 即将推出 |
