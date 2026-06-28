import os
from pathlib import Path
from functools import lru_cache

import yaml

from app.core.config import settings


class Persona:
    def __init__(self, data: dict):
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.title: str = data["title"]
        self.category: str = data["category"]
        self.era: str = data["era"]
        self.avatar: str = data.get("avatar", "")
        self.short_bio: str = data.get("short_bio", "")
        self.style: str = data.get("style", "")

        tf = data.get("thinking_framework", {})
        self.analysis: str = tf.get("analysis", "")
        self.decision: str = tf.get("decision", "")
        self.foresight: str = tf.get("foresight", "")
        self.methodology: str = tf.get("methodology", "")

        voice = data.get("voice", {})
        self.tone: str = voice.get("tone", "")
        self.speak_style: str = voice.get("style", "")
        self.length_pref: str = voice.get("length", "中等")
        self.opening_style: str = voice.get("opening", "")

        self.core_beliefs: list[str] = data.get("core_beliefs", [])
        self.canonical_works: list[dict] = data.get("canonical_works", [])

        kd = data.get("knowledge_domain", {})
        self.known: list[str] = kd.get("known", [])
        self.unknown: list[str] = kd.get("unknown", [])
        self.attitude_to_unknown: str = kd.get("attitude_to_unknown", "")

    def build_system_prompt(self, rag_context: str = "") -> str:
        beliefs_text = "\n".join(f"- {b}" for b in self.core_beliefs)
        known_text = "、".join(self.known)
        unknown_text = "、".join(self.unknown)

        prompt = f"""你正在扮演{self.name}（{self.era}·{self.title}）。你必须完全以{self.name}的身份、思维方式和语言风格来回答问题。

## 你的身份
你是{self.name}，{self.era}时期的{self.title}。
简介：{self.short_bio}

## 你的思维框架
- 分析问题的方式：{self.analysis}
- 决策模式：{self.decision}
- 预见习惯：{self.foresight}
- 方法论：{self.methodology}

## 你的语言风格
- 语气：{self.tone}
- 表达方式：{self.speak_style}
- 回答长度偏好：{self.length_pref}
- 开场方式：{self.opening_style}

## 你的核心信条
{beliefs_text}

## 你的知识边界
- 你熟悉的领域：{known_text}
- 你不了解的事物：{unknown_text}
- 对于不了解事物的态度：{self.attitude_to_unknown}

## 回答要求
1. 你是{self.name}本人，不要用"作为XX我会说"这类元描述
2. 用{self.style}的方式思考并回答
3. 可以引用你的著作或名言，但要自然融入
4. 对于现代事物，用你的古代/原有智慧框架去类比理解
5. 保持谦逊真诚，但对自己的信念坚定不移
6. 回答简洁有力，符合{self.length_pref}的篇幅偏好"""

        if rag_context:
            prompt += f"\n\n## 参考资料（你的著作中与问题相关的原文）\n{rag_context}\n\n请参考以上资料的精神来回答，但用自己的话重新表达，不要直接复制。"

        return prompt

    def to_api_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "title": self.title,
            "category": self.category,
            "era": self.era,
            "avatar": self.avatar,
            "short_bio": self.short_bio,
            "style": self.style,
        }


class PersonaEngine:
    def __init__(self):
        self._personas: dict[str, Persona] = {}
        self._load_all()

    def _load_all(self):
        personas_dir = Path(settings.personas_dir)
        for f in personas_dir.glob("*.yaml"):
            with open(f, "r", encoding="utf-8") as fp:
                data = yaml.safe_load(fp)
                persona = Persona(data)
                self._personas[persona.id] = persona

    def list_all(self) -> list[Persona]:
        return list(self._personas.values())

    def get(self, persona_id: str) -> Persona | None:
        return self._personas.get(persona_id)

    def get_many(self, ids: list[str]) -> list[Persona]:
        return [p for pid in ids if (p := self._personas.get(pid))]

    def build_prompts(self, ids: list[str], rag_results: dict[str, str] | None = None) -> list[tuple[str, str]]:
        rag_results = rag_results or {}
        result = []
        for pid in ids:
            if persona := self._personas.get(pid):
                ctx = rag_results.get(pid, "")
                result.append((pid, persona.build_system_prompt(ctx)))
        return result


@lru_cache(maxsize=1)
def get_persona_engine() -> PersonaEngine:
    return PersonaEngine()
