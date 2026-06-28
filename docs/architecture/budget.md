# 预算管理系统

## 概述

每个会话有 **¥15 元预算上限**。系统在提问前预估费用，提问后记录实际消耗，超支后拒绝服务。

## 计费模型

| 计费项 | 单价 (每百万 token) | 说明 |
|--------|---------------------|------|
| LLM 输入 | ¥2.0 | System Prompt + 对话历史 + 检索文本 |
| LLM 输出 | ¥8.0 | 军师回答内容 |
| Embedding | ¥0.5 | 知识库检索时的向量化 |

配置项：
```
MAX_BUDGET_PER_SESSION_CNY=15.0
LLM_INPUT_PRICE_PER_M=2.0
LLM_OUTPUT_PRICE_PER_M=8.0
EMBEDDING_PRICE_PER_M=0.5
```

## 费用估算

### 提问前预估

```python
est_input_tokens = len(question) // 2           # 中文字符 → token
est_output_tokens = 800 × len(advisors)          # 每位军师预估 800 token
est_cost = input_cost + output_cost               # 预估总费用

if budget.remaining < est_cost:
    → 拒绝提问，提示超支
```

### 提问后实际计算

```python
actual_input = len(enhanced_question) // 2 + system_prompt_overhead
actual_output = total_response_chars // 2
usage = TokenUsage(input_tokens=actual_input, output_tokens=actual_output)
budget.add_usage(usage)
```

## BudgetManager 数据流

```
Session 创建
  │
  ▼
BudgetManager.get(session_id)
  → SessionBudget (内存)
  → persist() to DB (budget_data JSON)

每次提问前
  │
  ├─ BudgetManager.check_budget()
  │     ├─ over_budget? → 拒绝 (SSE 推送提示)
  │     └─ can_spend(est_cost)? → 继续
  │
  ▼
每次提问后
  ├─ budget.add_usage(actual_usage)
  └─ persist() to DB

前端实时显示
  └─ SSE event: {type: "budget_update", budget: {...}}
```

## SessionBudget 数据结构

```python
@dataclass
class SessionBudget:
    session_id: str
    max_budget: float = 15.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_embedding_tokens: int = 0
    total_cost_cny: float = 0.0
    over_budget: bool = False
```

## 前端预算条

在群聊界面顶部：
```
[████████░░░░░░░░] ¥6.23 / ¥15  25,430 tokens
```

颜色变化：
- 绿色 (`< 80%`)：正常
- 琥珀色 (`80% ~ 100%`)：接近上限
- 红色 (`> 100%`)：超支，禁止新提问
