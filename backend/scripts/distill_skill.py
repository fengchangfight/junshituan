"""Skill distillation — generates skill.yaml from corpus and persona data.

Inspired by nuwa.skill: inputs a persona, outputs a structured SKILL.yaml
with mental models, heuristics, workflows, and expression patterns.

Usage:
  python scripts/distill_skill.py --persona zhuge-liang
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.llm_client import chat_stream
from app.services.persona_engine import get_persona_engine


DISTILL_PROMPT = """你是一位认知科学家，专门从原始材料中提炼人物的"认知操作系统"。

你需要分析以下关于{name}的材料，输出一个结构化的 Skill 定义。

## 原始材料

### 人物信息
- 名称：{name}
- 时代：{era}
- 称号：{title}
- 简介：{bio}
- 风格：{style}

### 核心信条
{beliefs}

### 著作原文（节选）
{corpus_sample}

## 输出格式

请生成 YAML 格式的 Skill 定义，包含以下部分（参考 zhangxuefeng-skill 的格式）：

```yaml
name: "{name}"
version: "2.0"

# 角色扮演规则
roleplay:
  first_person: true
  disclaimer_once: "一句话免责声明"
  exit_triggers: ["退出角色", "切换"]

# 回答工作流
workflow:
  steps:
    - step: classify
      description: "如何判断问题类型"
    - step: retrieve
      description: "从什么知识库检索"
    - step: reason
      description: "用这个人的什么思维框架推理"
    - step: self_check
      description: "开口前检查什么"
    - step: respond
      description: "如何输出回答"

  checkpoints:
    - id: before_speak
      questions:
        - "这条人的标志性自问1？"
        - "这条人的标志性自问2？"

  fallback_tree:
    - trigger: "遇到未知问题时的反应"
      action: "如何处理"

# 心智模型（3-5个，每个包含：摘要、证据、应用场景、局限性）
mental_models:
  - name: "模型名称"
    summary: "一句话概括"
    evidence:
      - "支撑的证据"
    application: "什么时候用"
    limitation: "什么情况下不适用"

# 决策启发式（3-5个）
heuristics:
  - name: "启发式名称"
    trigger: "什么情况下触发"
    action: "怎么做"
    example: "经典案例"

# 表达DNA
expression:
  sentence_patterns:
    - "标志性句式1"
    - "标志性句式2"
  tone: "语气描述"
  rhythm: "回答节奏"
  vocabulary:
    preferred: ["高频词1", "高频词2"]
    avoided: ["禁忌词1", "禁忌词2"]
  certainty: "确定性程度"
  humor: "幽默方式"

# 反例黑名单
anti_patterns:
  - pattern: "这个人物绝不会做的事情"
    reason: "为什么"
    fix: "应该怎么做"

# 诚实边界
limitations:
  - "这个人物知识的天然局限"
  - "已知的盲区"
```

要求：
1. 每个心智模型必须有明确的 evidence（从原文中找引用）
2. 表达DNA要捕捉这个人的独特说话方式
3. 决策启发式要包含具体的触发场景
4. Workflow 要体现这个人的思维过程"""


async def distill(persona_id: str, corpus_dir: str = "data/corpus") -> str:
    engine = get_persona_engine()
    persona = engine.get(persona_id)
    if not persona:
        print(f"Persona not found: {persona_id}")
        return ""

    # Collect corpus samples
    corpus_samples = []
    corp_path = Path(corpus_dir) / persona_id
    if corp_path.is_dir():
        for f in corp_path.glob("*.txt"):
            text = f.read_text(encoding="utf-8")[:2000]
            corpus_samples.append(text)

    beliefs_text = "\n".join(f"- {b}" for b in persona.core_beliefs)
    corpus_text = "\n\n---\n\n".join(corpus_samples[:3]) if corpus_samples else "无原文材料"

    prompt = DISTILL_PROMPT.format(
        name=persona.name,
        era=persona.era,
        title=persona.title,
        bio=persona.short_bio,
        style=persona.style,
        beliefs=beliefs_text,
        corpus_sample=corpus_text[:4000],
    )

    print(f"Distilling skill for {persona.name}...")
    print(f"  Corpus: {len(corpus_samples)} files, {sum(len(c) for c in corpus_samples)} chars")

    result = ""
    async for token in chat_stream(
        system_prompt="你是一位认知科学家。输出高质量的 YAML。",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6,
    ):
        result += token
        print(token, end="", flush=True)

    print("\n\nDone!")
    return result


def main():
    parser = argparse.ArgumentParser(description="Distill a Skill from persona + corpus")
    parser.add_argument("--persona", type=str, required=True, help="Persona ID to distill")
    parser.add_argument("--output", type=str, help="Output file path")
    args = parser.parse_args()

    result = asyncio.run(distill(args.persona))

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Extract just the YAML part
        start = result.find("---")
        end = result.rfind("```") if result.rfind("```") > 0 else len(result)
        if start >= 0:
            yaml_content = result[start:end].strip()
        else:
            yaml_content = result
        output_path.write_text(yaml_content, encoding="utf-8")
        print(f"Written to {output_path}")


if __name__ == "__main__":
    main()
