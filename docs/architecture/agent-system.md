# Agent 系统设计

## 核心概念

每个军师（如诸葛亮、孙子）对应一个 **LangGraph Agent 实例**。Agent 是一个可恢复的状态机，模拟该人物的思维方式、调用其知识库、并以该人物的语言风格回答问题。

## Agent 模板 (AdvisorAgentGraph)

所有军师共享同一个 Agent 模板（`services/agent/base_agent.py`），通过不同的 **System Prompt** 和 **知识库连接** 实现差异化。

### 状态机图

```
         ┌─────────┐
         │  START  │
         └────┬────┘
              │
         ┌────▼────┐
         │understand│  解析用户问题，确定检索方向
         └────┬────┘
              │
         ┌────▼────┐
         │ retrieve │  Milvus 知识库检索（RAG）
         └────┬────┘
              │
         ┌────▼────┐
         │  reason  │  以军师思维方式推理分析
         └────┬────┘
              │
         ┌────▼────┐  yes
         │ needs───┼──────────┐
         │ sub?    │          │
         └────┬────┘     ┌────▼────┐
              │ no       │sub_agent│  派发子任务
              │          └────┬────┘
         ┌────▼────┐         │
         │ respond  │◄────────┘  生成最终回答
         └────┬────┘
              │
         ┌────▼────┐  over_limit
         │context──┼──────────┐
         │check    │          │
         └────┬────┘     ┌────▼────┐
              │ ok       │compress │  压缩旧上下文
              │          └────┬────┘
         ┌────▼────┐         │
         │   END   │◄────────┘
         └─────────┘
```

### AgentState (TypedDict)

```python
class AgentState(TypedDict):
    messages: list[BaseMessage]       # 对话历史 (LangChain messages)
    persona_id: str                   # 军师 ID
    persona_name: str                 # 军师名称
    system_prompt: str                # 动态生成的 System Prompt
    session_id: str                   # 会话 ID (用于 LangGraph thread)
    user_id: str                      # 用户 ID

    retrieved_docs: list[str]         # Milvus 检索到的文档片段
    retrieval_query: str              # 检索查询

    reasoning: str                    # 推理过程
    sub_tasks: list[dict]             # 子任务列表

    context_summary: str              # 压缩后的历史摘要
    tokens_used: int                  # 已用 token 数

    final_response: str               # 最终回答
    needs_sub_agent: bool             # 是否需要子Agent
    sub_agent_task: str               # 子任务描述
```

### 会话恢复 (Claude Code Resume 风格)

LangGraph 内置 **Checkpointer** 机制：

```python
config = {"configurable": {"thread_id": f"{session_id}_{persona_id}"}}

# 新消息
result = await agent.graph.ainvoke(initial_state, config)

# 后续消息 — 自动加载之前的状态
result = await agent.graph.ainvoke(new_state, config)
```

每个 `session_id + persona_id` 组合对应一个独立的 LangGraph thread。重新进入聊天室时，Agent 自动从 checkpoint 恢复状态，包括完整的推理链和对话上下文。

## 子 Agent 系统 (Claude Code Sub-agent 风格)

当主 Agent 在 `reason` 阶段判断需要深入分析某个子问题时，可以派发 **SubAgent**。

### SubAgent 类型

| 类型 | 名称 | 用途 |
|------|------|------|
| `analyze` | 分析助手 | 深度分析单个问题 |
| `verify` | 验证助手 | 检验信息一致性 |
| `search_synthesis` | 检索综合 | 综合检索信息 |
| `counterfactual` | 反事实分析 | 从对立角度挑战假设 |

### 派发流程

```
主 Agent (reason node)
  │
  ├─ 分析问题复杂度
  ├─ 判断是否需要子Agent
  │
  ├─ 不需要 → 直接 respond
  │
  └─ 需要 → 派发 SubAgent
              │
              ├─ SubAgent.run(task, parent_context)
              ├─ 返回结构化结果 (JSON)
              └─ 注入主 Agent reasoning → respond
```

## Agent 注册与生命周期

`AgentRegistry` (`services/agent/agent_registry.py`) 管理 Agent 实例：

- **单例**：每个军师只有一个 Agent 实例
- **知识库重连**：消化完成后调用 `registry.remove(id)` 使旧 Agent 失效
- **Session 隔离**：同一 Agent 通过不同 `thread_id` 服务于不同会话

## 与 Persona Engine 的配合

```
PersonaEngine (YAML → Persona 对象)
  │
  ├─ persona.build_system_prompt(rag_context)
  │    生成该军师的 System Prompt，包含：
  │    - 身份与背景
  │    - 思维框架 (analysis/decision/foresight/methodology)
  │    - 语言风格 (tone/style/length/opening)
  │    - 核心信条
  │    - 知识边界
  │    - RAG 检索到的参考资料
  │
  └─ 注入 Agent 的 system_prompt 字段
```
