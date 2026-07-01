from app.models.db_models import PersonaDB


class Persona:
    def __init__(self, data: dict):
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.title: str = data["title"]
        self.category: str = data["category"]
        self.era: str = data["era"]
        self.short_bio: str = data.get("short_bio", "")
        self.style: str = data.get("style", "")
        self.avatar: str = data.get("avatar", "")

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

    @classmethod
    def from_db_row(cls, row: PersonaDB) -> "Persona":
        return cls({
            "id": row.id,
            "name": row.name,
            "title": row.title,
            "category": row.category,
            "era": row.era,
            "avatar": row.avatar or "",
            "short_bio": row.short_bio or "",
            "style": row.style or "",
            "thinking_framework": row.thinking_framework or {},
            "voice": row.voice or {},
            "core_beliefs": row.core_beliefs or [],
            "canonical_works": row.canonical_works or [],
            "knowledge_domain": row.knowledge_domain or {},
        })

    def build_system_prompt(self, rag_context: str = "", skill_prompt: str = "") -> str:
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

        if skill_prompt:
            prompt += f"\n\n# 认知操作系统（Skill）\n{skill_prompt}"

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

    def load_from_rows(self, rows: list[PersonaDB]):
        """Load all personas from database rows."""
        self._personas.clear()
        for row in rows:
            self._personas[row.id] = Persona.from_db_row(row)

    def reload(self, rows: list[PersonaDB]):
        """Reload all personas from fresh database rows."""
        self.load_from_rows(rows)

    def list_all(self) -> list[Persona]:
        return list(self._personas.values())

    def get(self, persona_id: str) -> Persona | None:
        return self._personas.get(persona_id)

    def get_many(self, ids: list[str]) -> list[Persona]:
        return [p for pid in ids if (p := self._personas.get(pid))]

    def add_persona(self, persona: Persona):
        """Add or update a single persona in the engine."""
        self._personas[persona.id] = persona

    def remove_persona(self, persona_id: str):
        """Remove a persona from the engine."""
        self._personas.pop(persona_id, None)

    def build_prompts(self, ids: list[str], rag_results: dict[str, str] | None = None) -> list[tuple[str, str]]:
        from app.services.skill_engine import get_skill_engine
        skill_engine = get_skill_engine()

        rag_results = rag_results or {}
        result = []
        for pid in ids:
            if persona := self._personas.get(pid):
                ctx = rag_results.get(pid, "")
                skill_prompt = skill_engine.build_skill_prompt(pid)
                result.append((pid, persona.build_system_prompt(ctx, skill_prompt)))
        return result


_engine_instance: PersonaEngine | None = None


def get_persona_engine() -> PersonaEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = PersonaEngine()
    return _engine_instance


async def init_persona_engine():
    """Initialize the persona engine by loading all personas from the database."""
    from sqlalchemy import select
    from app.db.database import _get_sessionmaker

    engine = get_persona_engine()
    sm = _get_sessionmaker()
    async with sm() as db:
        result = await db.execute(select(PersonaDB))
        rows = result.scalars().all()
        engine.load_from_rows(list(rows))
