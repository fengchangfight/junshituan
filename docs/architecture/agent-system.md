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

## 与 Persona Engine + Skill Engine 的配合

```
System Prompt 由三层组成：

PersonaEngine (Persona YAML → 身份与风格)
  │
  ├─ persona.build_system_prompt(rag_context, skill_prompt)
  │    生成基础 System Prompt：
  │    - 身份与背景
  │    - 思维框架 (analysis/decision/foresight/methodology)
  │    - 语言风格 (tone/style/length/opening)
  │    - 核心信条
  │    - 知识边界
  │    - RAG 检索到的参考资料（Milvus 混合搜索）
  │
  ▼
SkillEngine (Skill YAML → 认知操作系统)
  │
  ├─ skill.build_skill_prompt()
  │    增强 System Prompt：
  │    - 回答工作流 (classify → retrieve → reason → check → respond)
  │    - 开口前自查询问点 (CHECKPOINT)
  │    - Fallback 树 (检索空/超时代/追问)
  │    - 心智模型 (含证据/应用/局限)
  │    - 决策启发式 (触发条件 + 行动)
  │    - 表达DNA (句式/词汇/节奏/确定性)
  │    - 反例黑名单 (绝不要做的事)
  │    - 诚实边界 (已知局限)
  │
  └─ 注入 Agent 的 system_prompt 字段
```

## Skill 系统 (v2 新增)

Skill 是比 Persona 更深的"认知操作系统"。参考 [zhangxuefeng-skill](https://github.com/alchaincyf/zhangxuefeng-skill) 的设计范式。

### Skill vs Persona

| 维度 | Persona v1 | Skill v2 |
|------|-----------|----------|
| 思维框架 | 4 句描述性引导 | 3-5 个心智模型（含证据/应用场景/局限性） |
| 决策方式 | 无 | 决策启发式（触发条件 + 行动 + 案例） |
| 工作流 | 无 | 5 步 Agentic Protocol |
| 自查机制 | 无 | CHECKPOINT 开口前自检 |
| 容错 | 无 | Fallback 树（检索空/超时代/问细节） |
| 表达风格 | 3 行描述 | 句式/词汇/节奏/幽默/确定性/禁忌词 |
| 反例约束 | 无 | 反例黑名单（禁止行为 + 纠正方案） |
| 诚实边界 | 知识边界 | 知识边界 + 内在矛盾 + 来源局限 |

### Skill YAML 目录结构

```
backend/data/skills/
└── {persona_id}/
    └── skill.yaml          # 认知操作系统定义
```

### Skill 蒸馏

使用 LLM 从原始语料自动生成 Skill：

```bash
python scripts/distill_skill.py --persona zhuge-liang
```

蒸馏流程：
1. 读取 Persona YAML（身份/信条/风格）
2. 读取 corpus 原文（著作/言论）
3. LLM 分析 → 提取心智模型、启发式、表达DNA
4. 输出 YAML → `data/skills/{persona_id}/skill.yaml`
