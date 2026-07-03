# 军师团 (Junshituan) — 多 Agent 技术总结与对比分析

> 2026-07-03 | 版本 2.1

---

## 1. 项目概览

**军师团** 是一个虚拟历史顾问团系统，允许用户与多位历史智者（如孔子、老子、尼采、孙子等）进行群聊式对话。每位军师拥有独立的人格定义（Persona）、知识库（RAG）、思考框架和语言风格，通过 LLM 驱动进行角色化回答。

**技术栈：**
- **Agent 框架**: LangGraph (状态机/checkpoint) + **llama-index** (知识摄入管道)
- **后端**: Python / FastAPI / SQLAlchemy (async) / sse-starlette
- **前端**: Next.js 14 / TypeScript / Tailwind CSS / Framer Motion
- **LLM**: DeepSeek V4 Pro (可替换)
- **向量库**: Milvus (混合检索: 稠密 + 稀疏 BM25)
- **嵌入模型**: ZhipuAI embedding-2
- **数据库**: PostgreSQL 16 (asyncpg) — 业务数据 + LangGraph checkpoint
- **容器化**: Docker Compose (postgres, etcd, minio, milvus, attu, backend, frontend)

---

## 2. 核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ Council   │  │  Admin   │  │  Login   │  │   SSE Stream  │  │
│  │   Page    │  │  Panel   │  │   Page   │  │    Reader     │  │
│  └─────┬─────┘  └────┬─────┘  └────┬─────┘  └───────┬───────┘  │
└────────┼──────────────┼─────────────┼───────────────┼───────────┘
         │              │             │               │
    ┌────▼──────────────▼─────────────▼───────────────▼──────────┐
    │                    Backend (FastAPI)                        │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
    │  │ Council  │  │  Admin   │  │   Auth   │  │ Advisors │   │
    │  │   API    │  │   API    │  │   API    │  │   API    │   │
    │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
    └───────┼──────────────┼────────────┼──────────────┼─────────┘
            │              │            │              │
    ┌───────▼──────────────▼────────────▼──────────────▼─────────┐
    │                     Service Layer                           │
    │  ┌────────────┐  ┌───────────┐  ┌────────────────────┐    │
    │  │  Council   │  │  Persona  │  │   Agent Registry   │    │
    │  │  Service   │  │  Engine   │  │   (Singleton Pool) │    │
    │  └─────┬──────┘  └─────┬─────┘  └─────────┬──────────┘    │
    │        │               │                   │               │
    │  ┌─────▼───────────────▼───────────────────▼───────────┐   │
    │  │              LangGraph Agent Graph                    │   │
    │  │  understand → retrieve → reason ⇄ tool_call          │   │
    │  │                               ↓                      │   │
    │  │                            respond → END              │   │
    │  └──────────────────────────────────────────────────────┘   │
    └──────────────────────────┬──────────────────────────────────┘
                               │
    ┌──────────────────────────▼──────────────────────────────────┐
    │                    Infrastructure                            │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
    │  │PostgreSQL│  │  Milvus  │  │ DeepSeek │  │  Memory  │   │
    │  │   (DB)   │  │  (RAG)   │  │   (LLM)  │  │  (Cache) │   │
    │  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
    │  ┌──────────┐  ┌──────────────────────────────────────┐   │
    │  │   Tool   │  │          Logging (timestamp+user)      │   │
    │  │ Framework│  │          contextvars isolation         │   │
    │  └──────────┘  └──────────────────────────────────────┘   │
    └─────────────────────────────────────────────────────────────┘
```

---

## 3. Agent 模型：能力矩阵

### 3.1 Agent 架构模式

| 模式 | 实现状态 | 说明 |
|------|---------|------|
| **单 Agent** | ✅ 完整 | 每位军师是一个 LangGraph 状态机 Agent |
| **多 Agent 顺序协作** | ✅ 完整 | 多军师依次回答，后答者获得累积上下文 |
| **@Mention 路由** | ✅ 完整 | 前端 @军师名 或双击头像指定发言人 |
| **接话/续话** | ✅ 完整 | 点击军师触发继续发言，继承讨论上下文 |
| **工具调用 (ReAct)** | ✅ 完整 | Tool 框架 + web_search (DuckDuckGo)，LLM 自主决定是否调用 |
| **子 Agent 委派** | ⚠️ 框架存在 | `sub_agent_pool` 已定义但未接入图节点 |
| **并行多 Agent** | ❌ 未实现 | 当前仅支持顺序执行 |
| **Agent 间直接通信** | ❌ 未实现 | Agent 通过共享上下文间接通信 |

### 3.2 Agent 状态机 (LangGraph)

```
START → understand → retrieve → reason ⇄ tool_call
                                      ↓
                                   respond → END
```

**节点说明：**

| 节点 | 功能 | LLM 调用 |
|------|------|---------|
| `understand` | 解析用户问题，确定检索查询 | 无 |
| `retrieve` | 从 Milvus 知识库检索相关文档 | 无（向量搜索） |
| `reason` | 分析 + 工具调用决策 + 简单问题直接回答 | 1-2 次 chat_with_tools (ReAct 循环) |
| `tool_call` | 执行 LLM 请求的工具调用，结果回灌 | 0-N 次（取决于工具数量） |
| `respond` | 复杂问题的深度回答（仅在 complex 时） | 1 次 chat_stream |
| `compress` | 上下文压缩（接近 token 上限时） | 1 次 chat_stream |

**关键设计决策：**
- reason 节点支持双路径：工具可用时走 `chat_with_tools()` → ReAct 循环（最多 2 轮）；无工具或达上限时走原始 prompt 路径
- tool_call 节点执行后自动路由回 reason，形成 ReAct 循环
- `StreamTagParser` 实时提取 response 内容流式推送到前端
- 工具调用结果通过 SSE metadata 实时推送到前端工具面板

### 3.3 Tool 框架

基于 Claude Code 的 `buildTool` 模式设计的轻量 Python 框架：

```
BaseTool (抽象基类)
  ├── name, description, parameters (JSON Schema)
  ├── execute() → ToolResult
  ├── prompt_snippet → system prompt 注入
  └── to_openai_schema() → OpenAI function calling 兼容

ToolRegistry (全局注册表)
  ├── register(tool)
  ├── get_schemas() → OpenAI tools schema
  ├── execute(name, args) → ToolResult
  └── 新增工具: 建文件 → subclass → register → 完成
```

**已实现工具：**

| 工具 | 实现 | 说明 |
|------|------|------|
| `web_search` | DuckDuckGo (免费无 API key) | 实时网页搜索，15s 超时，返回标题+URL+摘要 |

扩展新工具只需在 `backend/app/tools/` 下新增一个文件。

---

## 4. 上下文管理

### 4.1 会话上下文

| 机制 | 实现 | 对标系统 |
|------|------|---------|
| **Session Checkpoint** | PostgresCheckpointer (base64-encoded msgpack)，key = `{session_id}_{persona_id}` | LangGraph |
| **会话消息持久化** | PostgreSQL `chat_messages` 表 | - |
| **会话恢复** | `resume()` 从 checkpoint 加载状态，合并全量 conversation history（修复跨军师上下文丢失） | Claude Code (resume session) |
| **跨军师上下文** | checkpoint 加载后合并 `conversation_history`，确保军师看到其他军师在自己上轮后的发言 | - |

### 4.2 上下文窗口管理

| 特性 | 实现 |
|------|------|
| **上下文压缩** | `_compress` 节点：超过阈值时 LLM 生成摘要，保留最近 2 条消息 |
| **背景/焦点分层** | `_format_conversation` 将上下文分为"背景"和"最近讨论"，LLM 优先回应最近话题 |
| **Token 估算** | 基于字符数粗略估算（中文 ~3 chars/token），非精确计数 |
| **上下文注入** | 用户记忆 + 会话历史 + 知识库检索结果 → 拼接进 prompt |

### 4.3 对标分析

| 系统 | 上下文管理策略 |
|------|--------------|
| **Claude Code** | 子 Agent 完全隔离上下文，仅返回摘要给父 Agent |
| **Hermes** | 子 Agent 独立对话历史，父 Agent 只接收结构化结果 |
| **OpenClaw** | 物理工作区隔离 (`agentDir`)，`MEMORY.md` 文件共享 |
| **OpenHuman** | Memory Tree 三层压缩 + Bucket-Seal 引擎 |
| **军师团** | 共享会话上下文 + 背景/焦点分层 + LangGraph checkpoint + history merge |

**差距：** 缺乏精确的 token 计数和自动滑动窗口；上下文压缩阈值硬编码。

---

## 5. 记忆系统

### 5.1 记忆类型

| 记忆类型 | 存储位置 | 生命周期 | 对标 |
|---------|---------|---------|------|
| **会话记忆** | `chat_messages` 表 + LangGraph checkpoint | 会话级 | LangGraph MemorySaver |
| **用户长时记忆** | `user_memories` 表 (PostgreSQL) | 用户级，跨会话 | Hermes MEMORY.md |
| **知识库检索** | Milvus 向量库 | 持久化，per persona | OpenClaw RAG |
| **会话摘要** | `sessions.conversation_summary` | 会话级，按需生成 | OpenHuman Memory Tree |

### 5.2 记忆操作

| 操作 | 触发时机 | 实现 |
|------|---------|------|
| **记忆提取** | 每次 ask 后 LLM 提取 fact/preference/insight/event | `user_memory_service.extract_memories()` |
| **记忆检索** | 每次 ask 前按 user_id + session_id 检索 | `retrieve_relevant()` (关键词匹配) |
| **记忆衰减** | 每 10 次 consolidate 自动衰减低活跃度记忆 | `consolidate()` (importance × 0.95) |
| **记忆裁剪** | 超过 100 条时删除低重要度记忆 | `consolidate()` (DELETE limit) |
| **会话摘要** | 消息 > 30 条时 LLM 生成 | `context_manager.summarize_history()` |

### 5.3 对标分析

| 特性 | 军师团 | Hermes | OpenHuman | Claude Code |
|------|--------|--------|-----------|-------------|
| 用户记忆 | ✅ SQL | ✅ MEMORY.md | ✅ Memory Tree | ✅ /memory |
| 会话记忆 | ✅ SQL + checkpoint | ✅ SQLite FTS5 | ✅ SQLite | ✅ 会话文件 |
| 知识库 RAG | ✅ Milvus | ✅ 工具调用 | ✅ 118+ 连接器 | ✅ WebSearch |
| 自动记忆提取 | ✅ LLM 后台 | ✅ Background Review | ✅ Subconscious | ❌ 手动 |
| 记忆衰减 | ✅ 周期性 | ❌ | ❌ | ❌ |
| 记忆检索 | ⚠️ 关键词 | ✅ FTS5 全文 | ✅ 向量语义 | ✅ 语义 |

**差距：** 记忆检索使用关键词匹配而非语义搜索，准确率受限。

---

## 6. 知识检索 (RAG)

（本节内容与 v2.0 一致，略作精简）

### 6.1 文档摄入管道 (Powered by llama-index)

```
原始文档 → llama_index SentenceSplitter (分段)
         → EmbeddingAdapter (向量化)
         → llama_index IngestionPipeline (编排，UPSERTS_AND_DELETE 去重)
         → MilvusHybridVectorStore (llama-index VectorStore 协议适配器)
         → Milvus (持久化)
```

### 6.2 对标分析

| 系统 | RAG 策略 |
|------|---------|
| **军师团** | llama-index 管道 + Milvus 混合检索 + per-persona collection |
| **Hermes** | 文件系统 + WebSearch 工具 |
| **OpenClaw** | 5700+ 插件，含文件/浏览器/数据库 |
| **Claude Code** | Read/Grep/Glob + WebSearch |
| **LangGraph 生态** | LangChain retrievers + VectorStore integrations |
| **llama-index 原生** | 完整 RAG 框架：ingestion + indexing + retrieval + query engine |

---

## 7. 流式传输与实时 UX

### 7.1 流式架构

```
LLM token → token_callback → asyncio.Queue → SSE → frontend
Tool progress → tool_callback → SSE metadata → frontend tool panel
```

| 特性 | 实现 |
|------|------|
| **流式协议** | SSE (Server-Sent Events) via sse-starlette |
| **Token 级流式** | 每 token 立即推送到前端（TTFT ~8s 后首字可见）；工具调用路径按 5 字符分块模拟流式 |
| **XML 标签过滤** | `StreamTagParser` 实时提取 `<response>` 内容 |
| **工具进度可视化** | 右侧工具调用面板，实时显示搜索状态 + hover 查看结果链接 |
| **搜索开关** | 输入栏 `🌐 联网 / ⚡ 快速` toggle，用户可选择跳过 web search |
| **上下文恢复修复** | resume 时合并全量 conversation history，解决跨军师上下文丢失 |

### 7.2 对标分析

| 系统 | 流式策略 |
|------|---------|
| **军师团** | SSE + token 级流式 + 标签过滤 + 工具进度面板 + 搜索开关 |
| **Claude Code** | Server-sent events, 子 Agent 结果摘要返回 |
| **Hermes** | 异步桥接，子 Agent 后台运行，父 Agent 收到摘要 |
| **OpenClaw** | WebSocket 双向通道 |
| **OpenHuman** | Tauri IPC + HTTP RPC |

---

## 8. 会话与状态管理

### 8.1 会话生命周期

| 阶段 | 实现 |
|------|------|
| **创建** | `POST /api/council` → 创建 Session + 初始化 Budget |
| **活跃** | `POST /api/council/sessions/{id}/ask` → SSE 流式回答 |
| **恢复** | `GET /api/council/sessions/{id}` → 加载消息历史 |
| **删除** | `DELETE /api/council/sessions/{id}` → 级联删除消息和 checkpoint |
| **过期** | `cleanup_expired()` 方法存在但未被调度调用 |

### 8.2 Checkpoint 持久化

**当前方案：PostgresCheckpointer**

```
Agent 状态 → PostgresCheckpointer（base64 编码 msgpack → JSON 列）
```

- 继承 `InMemorySaver`（热路径），同步到 PostgreSQL `agent_checkpoints` 表
- msgpack bytes → base64 编码 → JSON 列（解决 bytes 不可序列化问题）
- `parent_config` 精简为仅 `thread_id`（过滤 callbacks 和 Runtime 对象）
- 数据绑定挂载到 `docker/data/postgres/`，迁移时 copy 整个项目目录即可

---

## 9. 多 Agent 协作模式

### 9.1 已实现的模式

| 模式 | 描述 | 对标 |
|------|------|------|
| **顺序发言** | 多军师依次回答，后答者获得累积上下文 | CrewAI Sequential Process |
| **@Mention 路由** | 用户通过 @军师名 指定发言人 | Claude Code Agent tool |
| **接话模式** | 点击军师头像触发继续发言 | Hermes send_message |
| **复杂度分流** | LLM 自判断 simple/complex，走不同路径 | OpenHuman model routing hints |
| **ReAct 工具调用** | reason → tool_call → reason 循环，LLM 自主决策 | Claude Code tool use |

### 9.2 对标矩阵

| 能力 | 军师团 | Claude Code | Hermes | OpenClaw | LangGraph | CrewAI |
|------|--------|-------------|--------|----------|-----------|--------|
| 单 Agent | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 顺序多 Agent | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 并行多 Agent | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 子 Agent 委派 | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Agent 间通信 | ❌ | ✅ Teams | ✅ send_msg | ✅ Gateway | 手动 | ❌ |
| 持续任务板 | ❌ | ❌ | ✅ Kanban | ❌ | ❌ | ❌ |
| 角色定义 | ✅ Persona | ✅ .md | ✅ Profile | ✅ SOUL.md | 手动 | ✅ Role |
| 工具调用 (ReAct) | ✅ | ✅ | ✅ | ✅ 5700+ | ✅ | ✅ |
| 人工审批门 | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ |

---

## 10. 安全与权限

| 维度 | 军师团 | 业界最佳实践 |
|------|--------|-------------|
| **会话隔离** | ✅ session_id + thread_id | ✅ |
| **Token callback 隔离** | ✅ LangGraph config + contextvars（并发安全）| ✅ |
| **用户认证** | ✅ JWT + bcrypt + 4 级角色 | ✅ |
| **军师可见性** | ✅ public（管理员创建，全员可见）/ private（用户自建，仅自己可见）| ✅ |
| **军师删除** | ✅ 级联删除知识库、向量、文档；保留会话记录 | ✅ |
| **工具沙箱** | ❌ 外层 try/except + 超时 | Docker/nsjail/Firecracker |
| **审批门禁** | ❌ | Claude Code / OpenHuman |
| **成本控制** | ✅ Budget per session | ✅ |

---

## 11. 可扩展性

### 11.1 当前扩展点

| 扩展点 | 方式 | 难度 |
|--------|------|------|
| 新增军师 | 首页"创建军师"按钮 / Admin API → 智能创建(AI) 或 手动创建 | 低 |
| 知识库上传 | Admin API → Milvus 入库 | 低 |
| 替换 LLM | 修改 `settings.llm_model` | 低 |
| 新增 Skill | `skill_engine` → 注入 system prompt | 中 |
| 新增 Agent 节点 | LangGraph `add_node` + `add_edge` | 中 |
| 新增 Tool | `app/tools/` 下新建 subclass → register → 立即可用 | 低 |
| 数据迁移 | `docker/data/` bind mount，copy 项目目录即可 | 低 |

### 11.2 对标分析

| 系统 | 扩展方式 | 灵活性 |
|------|---------|--------|
| **军师团** | LangGraph graph + Persona DB + Tool Registry | 中高 |
| **Hermes** | Profile + Tool + Skill 自注册 | 高 |
| **OpenClaw** | 5700+ 插件市场 + ClawHub | 极高 |
| **Claude Code** | Skills + Hooks + Sub-agents | 高 |

---

## 12. 综合评分矩阵

| 维度 | 军师团 | Claude Code | Hermes | OpenClaw | OpenHuman | CrewAI | LangGraph | llama-index |
|------|--------|-------------|--------|----------|-----------|--------|-----------|------------|
| **Agent 架构** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ (RAG only) |
| **上下文管理** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| **记忆系统** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ |
| **RAG 检索** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **文档摄入** | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **流式传输** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐ |
| **会话管理** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ |
| **多 Agent 协作** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | N/A |
| **安全隔离** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | N/A |
| **可扩展性** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **开发体验** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

---

## 13. 关键差距与改进建议

### P0 (立即)

| 差距 | 建议 |
|------|------|
| **会话过期未调度** | 添加 cron/background task 调用 `cleanup_expired()` |
| **记忆检索无语义** | 将关键词匹配替换为 embedding-based 语义检索 (复用 Milvus) |

### P1 (短期)

| 差距 | 建议 |
|------|------|
| **无子 Agent 委派** | 将 `sub_agent_pool` 重新接入图节点，用于复杂分析子任务 |
| **无 Agent 间直接通信** | 实现 Agent-to-Agent 消息传递（参考 Hermes send_message） |
| **无并行 Agent 响应** | 实现 `asyncio.gather` 并行 Agent 执行 |

### P2 (中期)

| 差距 | 建议 |
|------|------|
| **无人工审批门禁** | 在工具调用前插入 `interrupt` checkpoint（LangGraph 原生支持） |
| **无持续任务模式** | 实现 goal loop 或 Kanban 模式（参考 Hermes） |
| **无评估框架** | 集成 LangSmith 或自定义 eval 管道 |
| **精确 Token 计数** | 从 LLM API response 提取实际 token 数，替代字符估算 |

### P3 (长期)

| 差距 | 建议 |
|------|------|
| **前端框架可观测性** | 集成 OpenTelemetry tracing |
| **多平台接入** | CLI / Telegram / Discord 等渠道（参考 Hermes/OpenClaw） |
| **Agent 市场** | 军师模板分享/导入机制 |

---

## 14. 技术独特性

1. **LangGraph + llama-index 双框架融合**：各用所长，通过自定义适配层无缝集成。

2. **Persona 深度**：独立知识库 + 思考框架 + 语言风格 + 核心信念 + 认知操作系统。

3. **Tool 框架 + ReAct 循环**：借鉴 Claude Code 的 `buildTool` 模式设计的轻量可扩展框架，LLM 自主决策工具调用。

4. **XML 流式过滤 + 工具进度面板**：`StreamTagParser` token 级过滤 + 实时工具调用可视化。

5. **上下文背景/焦点二段式注入**：有效抑制 LLM 话题漂移。

6. **Session-scoped 用户记忆**：按 session_id 加权排序，防止跨会话泄漏。

7. **混合检索管道**：稠密 + 稀疏 BM25，per persona collection 知识隔离。

---

*报告生成时间：2026-07-03 | 基于军师团 v2.1.0*
