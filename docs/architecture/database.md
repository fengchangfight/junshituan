# 数据库设计

## 支持引擎

| 环境 | 引擎 | 连接串 |
|------|------|--------|
| 开发 | SQLite | `sqlite+aiosqlite:///./data/junshituan.db` |
| 生产 | PostgreSQL 16 | `postgresql+asyncpg://user:pass@host/db` |

SQLAlchemy 异步引擎，表结构自动创建（`init_db()` 在服务启动时调用）。

## 表结构

### users (用户)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | VARCHAR | 主键，12位 hex |
| `username` | VARCHAR(64) | 唯一，索引 |
| `hashed_password` | VARCHAR(256) | bcrypt 哈希 |
| `is_admin` | BOOLEAN | 管理员标记 |
| `display_name` | VARCHAR(128) | 显示名称 |
| `avatar_url` | VARCHAR(512) | 头像 URL |
| `created_at` | DATETIME | 创建时间 |

### personas (军师数据库记录)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | VARCHAR | 主键 = persona id |
| `name` | VARCHAR(128) | 军师名称 |
| `title` | VARCHAR(256) | 称号 |
| `category` | VARCHAR(64) | 分类 |
| `yaml_config` | TEXT | YAML 原始配置 |
| `kb_status` | VARCHAR(32) | empty/ingesting/ready/error |
| `kb_doc_count` | INT | 向量索引条数 |
| `kb_last_ingested` | DATETIME | 最后消化时间 |
| `is_published` | BOOLEAN | 是否发布 |
| `published_at` | DATETIME | 发布时间 |

### knowledge_documents (知识文档)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | VARCHAR | 主键 = SHA256(persona:filename)[:24] |
| `persona_id` | VARCHAR FK | 所属军师 |
| `filename` | VARCHAR(256) | 文件名 (如 chuanxilu.md) |
| `title` | VARCHAR(256) | 文档标题 |
| `content_type` | VARCHAR(32) | text/plain 或 text/markdown |
| `content` | TEXT | 全文 |
| `file_path` | VARCHAR(512) | 文件路径 |
| `chunk_count` | INT | 切片数量 |
| `status` | VARCHAR(32) | pending/processing/ingested/error/pending_reingest |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 最后更新时间 |

### sessions (会话/议事厅)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | VARCHAR | 主键 |
| `user_id` | VARCHAR FK | 所属用户 |
| `title` | VARCHAR(256) | 会话名称 |
| `advisor_ids` | JSON | 军师列表 ["zhuge-liang","sun-zi"] |
| `checkpoint_id` | VARCHAR(128) | LangGraph checkpoint 引用 |
| `conversation_summary` | TEXT | 对话摘要 |
| `message_count` | INT | 消息总数 |
| `budget_data` | JSON | 预算状态 |
| `is_active` | BOOLEAN | 活跃标记 |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 更新时间 |

### chat_messages (聊天消息)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | VARCHAR | 主键 |
| `session_id` | VARCHAR FK | 所属会话 |
| `sequence` | INT | 消息序号 |
| `role` | VARCHAR(16) | user/advisor/system |
| `advisor_id` | VARCHAR(64) | 军师 ID (仅 advisor) |
| `advisor_name` | VARCHAR(128) | 军师名称 |
| `content` | TEXT | 消息内容 |
| `metadata` | JSON | 附加元数据 |
| `created_at` | DATETIME | 创建时间 |

### user_memories (用户记忆 — Hermes 风格)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | VARCHAR | 主键 |
| `user_id` | VARCHAR FK | 所属用户 |
| `memory_type` | VARCHAR(32) | fact/preference/insight/event |
| `content` | TEXT | 记忆内容 |
| `importance` | FLOAT | 重要性 (0.0-1.0) |
| `source_session_id` | VARCHAR | 来源会话 |
| `access_count` | INT | 访问次数 |
| `last_accessed` | DATETIME | 最后访问时间 |
| `created_at` | DATETIME | 创建时间 |

### agent_checkpoints (Agent 状态快照)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | VARCHAR | 主键 |
| `session_id` | VARCHAR FK | 所属会话 |
| `advisor_id` | VARCHAR(64) | 军师 ID |
| `checkpoint_ns` | VARCHAR(256) | checkpoint 命名空间 |
| `checkpoint_data` | JSON | 完整状态快照 |
| `created_at` | DATETIME | 创建时间 |

## 关系图

```
User (1) ────< Session (N) ────< ChatMessage (N)
  │
  └──< UserMemory (N)

PersonaDB (1) ────< KnowledgeDocument (N)

Session (1) ────< AgentCheckpoint (N)  [per advisor]
```
