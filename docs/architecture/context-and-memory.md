# 上下文管理与持久化记忆

## 三层记忆架构

```
┌──────────────────────────────────────┐
│         短期记忆 (Short-term)         │
│  ────────────────────────────────── │
│  当前对话历史 (LangGraph messages)    │
│  存活周期：单次会话                    │
│  管理策略：滑动窗口 + 压缩            │
└──────────────┬───────────────────────┘
               │ 提取
┌──────────────▼───────────────────────┐
│        长期记忆 (Long-term)           │
│  ────────────────────────────────── │
│  Hermes 风格持久化记忆               │
│  类型：fact / preference / insight   │
│  存活周期：跨会话                     │
│  管理策略：重要性评分 + 衰减 + 合并   │
└──────────────┬───────────────────────┘
               │ 快照
┌──────────────▼───────────────────────┐
│        Agent 状态 (Checkpoint)        │
│  ────────────────────────────────── │
│  LangGraph checkpointer 状态快照     │
│  存活周期：会话期间                    │
│  恢复：resume session 时自动加载     │
└──────────────────────────────────────┘
```

## 上下文管理器 (ContextManager)

`services/memory/context_manager.py`

### 核心策略

| 策略 | 触发条件 | 行为 |
|------|----------|------|
| **压缩 (Compress)** | token 使用量 > 上限的 75% | LLM 摘要旧消息，仅保留最近 4 条 + 摘要 |
| **剪枝 (Prune)** | 需要限制 token 预算 | 保留 system 消息 + 最近消息，丢弃旧消息 |
| **Prefix Cache** | 重复调用相同 Persona | 缓存 System Prompt → 响应前缀 |

### Token 计算

采用简单估算：**中文字符数 / 3 ≈ token 数**（近似）

配置项：
```
MAX_CONTEXT_TOKENS=8000      # 最大上下文 token
SUMMARY_TRIGGER_TOKENS=6000  # 触发压缩的阈值
```

## 持久化记忆 (UserMemoryService — Hermes 风格)

`services/memory/user_memory.py`

### 记忆类型

| 类型 | 标记 | 示例 |
|------|------|------|
| `fact` | 📋 | "用户在互联网行业工作" |
| `preference` | 💡 | "用户偏好简洁的回答" |
| `insight` | 🔮 | "用户认为知行合一最重要" |
| `event` | 📅 | "用户上周经历了团队重组" |

### 生命周期

```
1. 每轮对话后 → extract_memories()
   LLM 从最近 6 条消息中提取值得记住的信息
   → 存入 user_memories 表 (importance ≥ 0.5)

2. 新提问前 → retrieve_relevant()
   关键词匹配 + importance 排序
   → 注入 System Prompt: "关于用户的长久记忆..."

3. 定期维护 → consolidate()
   每 10 次记忆提取触发：
   - 衰减：久未访问的记忆 importance × 0.95
   - 清理：超过 100 条时移除低 importance 记忆
```

### 记忆注入格式

```
## 关于用户的长久记忆
- 📋 用户在互联网行业工作
- 💡 用户偏好简洁的回答
- 🔮 用户认为知行合一最重要
```

## 会话存储 (SessionStore)

`services/memory/session_store.py`

### Session 表字段

| 字段 | 说明 |
|------|------|
| `id` | Session ID |
| `user_id` | 所属用户 |
| `advisor_ids` | JSON 数组，如 `["zhuge-liang","sun-zi"]` |
| `conversation_summary` | 压缩后的对话摘要 |
| `message_count` | 消息总数 |
| `budget_data` | 预算状态 JSON |
| `is_active` | 是否活跃 |

### 消息持久化

每条消息存入 `chat_messages` 表：
- `session_id` + `sequence` 保证顺序
- `role` = user / advisor / system
- `metadata` JSON 存储附加信息

### 会话过期

TTL 72小时（可配置 `SESSION_TTL_HOURS`），过期后 `is_active = False`。
