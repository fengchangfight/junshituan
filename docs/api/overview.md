# API 接口文档

Base URL: `http://localhost:8000/api`

## 认证

使用 JWT Bearer Token：

```
Authorization: Bearer <token>
```

### 公开接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/advisors` | 获取已发布的军师列表 |
| GET | `/advisors/{id}` | 获取单个军师详情 |
| POST | `/auth/login` | 登录 |
| POST | `/auth/register` | 注册 |
| POST | `/auth/admin/create` | 创建初始管理员（仅无管理员时） |

### 需要认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/council` | 创建议事厅 |
| GET | `/council/sessions` | 获取用户的议事厅列表 |
| GET | `/council/sessions/{id}` | 获取议事厅详情（含历史消息） |
| POST | `/council/sessions/{id}/ask` | 向议事厅提问 (SSE 流式) |

### 管理员接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/advisors` | 所有军师（含 KB 状态） |
| GET | `/admin/advisors/{id}` | 军师详情（含文档列表） |
| PUT | `/admin/advisors/{id}` | 更新军师元数据 |
| POST | `/admin/advisors/upload-text` | 上传知识文档 (文本) |
| POST | `/admin/advisors/upload` | 上传知识文档 (文件) |
| POST | `/admin/advisors/ingest` | 消化知识库 |
| POST | `/admin/advisors/publish` | 发布/取消发布 |
| DELETE | `/admin/advisors/{id}/documents/{docId}` | 删除文档 |

---

## 接口详情

### POST /auth/login

```json
// Request
{"username": "admin", "password": "admin123"}

// Response 200
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user_id": "abc123",
  "username": "admin",
  "is_admin": true
}
```

### GET /advisors

```json
// Response 200
[
  {
    "id": "zhuge-liang",
    "name": "诸葛亮",
    "title": "军事家·政治家",
    "category": "军事家",
    "era": "三国",
    "avatar": "/avatars/zhuge-liang.png",
    "short_bio": "字孔明...",
    "style": "谨慎周密...",
    "kb_status": "ready",
    "kb_doc_count": 150,
    "is_published": true
  }
]
```

### POST /council

```json
// Request
{
  "advisor_ids": ["zhuge-liang", "sun-zi", "lao-zi"],
  "title": "战略分析议事厅"
}

// Response 200
{
  "id": "e4c76eb61250",
  "advisors": [...],
  "title": "战略分析议事厅",
  "created_at": "2026-06-28T08:00:00Z"
}
```

### GET /council/sessions/{id}

```json
// Response 200
{
  "id": "e4c76eb61250",
  "title": "战略分析议事厅",
  "advisor_ids": ["zhuge-liang", "sun-zi", "lao-zi"],
  "message_count": 12,
  "budget": {
    "total_cost_cny": 2.35,
    "remaining_budget": 12.65,
    "budget_percent": 15.67,
    "total_tokens": 8400,
    "over_budget": false
  },
  "messages": [
    {
      "id": "msg1",
      "sequence": 0,
      "role": "system",
      "content": "诸葛亮、孙子、老子 已就位..."
    },
    {
      "id": "msg2",
      "sequence": 1,
      "role": "user",
      "content": "如何应对市场竞争？"
    },
    {
      "id": "msg3",
      "sequence": 2,
      "role": "advisor",
      "advisor_id": "sun-zi",
      "advisor_name": "孙子",
      "content": "知己知彼，百战不殆..."
    }
  ]
}
```

### POST /council/sessions/{id}/ask (SSE)

```
// Request
{"question": "如何应对困境？"}

// SSE Events
data: {"advisor_id":"system","content":"","metadata":{"type":"budget","budget":{...}}}

data: {"advisor_id":"zhuge-liang","advisor_name":"诸葛亮","content":"此事亮","done":false}
data: {"advisor_id":"zhuge-liang","advisor_name":"诸葛亮","content":"已思之...","done":false}
data: {"advisor_id":"zhuge-liang","done":true}

data: {"advisor_id":"system","metadata":{"type":"budget_update","cost_this_turn":0.045,"budget":{...}}}
```

### POST /admin/advisors/upload-text

```
// Form Data
persona_id: zhuge-liang
filename: chuanxilu.md
title: 传习录
text: <全文内容>

// Response 200
{
  "id": "a1b2c3d4e5f6",
  "filename": "chuanxilu.md",
  "status": "pending_reingest",
  "overwritten": true,
  "message": "文件已覆盖，请重新点击消化以更新知识库"
}
```

### POST /admin/advisors/ingest

```json
// Request
{"persona_id": "zhuge-liang"}

// Response 200
{"status": "ready", "chunks": 245}
```

### POST /admin/advisors/publish

```json
// Request
{"persona_id": "zhuge-liang", "publish": true}

// Response 200
{"status": "published"}
```
