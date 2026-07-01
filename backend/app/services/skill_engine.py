"""Skill Engine — loads skill definitions from DB and enhances agent prompts.

A Skill extends the static Persona with:
- Workflow steps (classify → retrieve → reason → self-check → respond)
- Self-check checkpoints
- Fallback trees
- Mental models with evidence, application, and limitations
- Decision heuristics
- Anti-patterns
"""

from app.models.db_models import PersonaDB


class Skill:
    def __init__(self, data: dict):
        self.name: str = data.get("name", "")
        self.version: str = data.get("version", "1.0")
        self.trigger_keywords: list[str] = data.get("trigger_keywords", [])

        rp = data.get("roleplay", {})
        self.first_person: bool = rp.get("first_person", True)
        self.disclaimer: str = rp.get("disclaimer_once", "")
        self.exit_triggers: list[str] = rp.get("exit_triggers", [])

        self.workflow: dict = data.get("workflow", {})
        self.mental_models: list[dict] = data.get("mental_models", [])
        self.heuristics: list[dict] = data.get("heuristics", [])
        self.expression: dict = data.get("expression", {})
        self.anti_patterns: list[dict] = data.get("anti_patterns", [])
        self.limitations: list[str] = data.get("limitations", [])

    def build_skill_prompt(self) -> str:
        """Build the skill-enhanced section of the system prompt."""

        sections = []

        # Roleplay rules
        if self.first_person:
            sections.append(f"""## 角色扮演规则
- 你是{self.name}本人，使用"我""吾"等第一人称
- 首次对话可以说："{self.disclaimer}"，之后不必重复
- 退出角色触发词：{', '.join(self.exit_triggers)}
- 不去分析自己扮演得像不像，只是以{self.name}的身份思考和说话""")

        # Workflow
        steps = self.workflow.get("steps", [])
        if steps:
            step_lines = []
            for s in steps:
                step_lines.append(f"  {s['step']}: {s.get('description', '')}")
            sections.append(f"""## 回答工作流
在回答每个问题时，依次完成以下步骤：
{chr(10).join(step_lines)}""")

        # Checkpoints
        checkpoints = self.workflow.get("checkpoints", [])
        if checkpoints:
            cp_lines = []
            for cp in checkpoints:
                cp_lines.append(f"### {cp['id']}")
                for q in cp.get("questions", []):
                    cp_lines.append(f"- {q}")
            sections.append(f"""## 开口前自查
{chr(10).join(cp_lines)}""")

        # Mental models
        if self.mental_models:
            model_lines = []
            for mm in self.mental_models:
                model_lines.append(f"### {mm['name']}")
                model_lines.append(f"**{mm.get('summary', '')}**")
                if mm.get('application'):
                    model_lines.append(f"应用：{mm['application']}")
                if mm.get('limitation'):
                    model_lines.append(f"局限：{mm['limitation']}")
            sections.append(f"""## 核心心智模型
回答时运用以下思维框架分析问题：
{chr(10).join(model_lines)}""")

        # Heuristics
        if self.heuristics:
            heur_lines = []
            for h in self.heuristics:
                heur_lines.append(f"- **{h['name']}**：{h.get('trigger', '')} → {h.get('action', '')}")
            sections.append(f"""## 决策启发式
{chr(10).join(heur_lines)}""")

        # Expression DNA
        expr = self.expression
        if expr:
            expr_parts = []
            if expr.get('sentence_patterns'):
                expr_parts.append(f"句式：{', '.join(expr['sentence_patterns'])}")
            if expr.get('tone'):
                expr_parts.append(f"语气：{expr['tone']}")
            if expr.get('rhythm'):
                expr_parts.append(f"节奏：{expr['rhythm']}")
            if expr.get('certainty'):
                expr_parts.append(f"确定性：{expr['certainty']}")
            sections.append(f"""## 表达风格
{chr(10).join(expr_parts)}""")

        # Anti-patterns
        if self.anti_patterns:
            ap_lines = []
            for ap in self.anti_patterns:
                ap_lines.append(f"- ❌ {ap['pattern']} → ✅ {ap.get('fix', '')}")
            sections.append(f"""## 绝不要做的事
{chr(10).join(ap_lines)}""")

        # Limitations
        if self.limitations:
            lim_lines = "\n".join(f"- {l}" for l in self.limitations)
            sections.append(f"""## 诚实边界
{lim_lines}""")

        return "\n\n".join(sections)


class SkillEngine:
    """Loads and manages Skill definitions from DB."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def load_from_rows(self, rows: list[PersonaDB]):
        """Load skills from database persona rows."""
        self._skills.clear()
        for row in rows:
            if row.skill_config:
                data = dict(row.skill_config)
                self._skills[row.id] = Skill(data)

    def add_skill(self, persona_id: str, skill_data: dict):
        """Add or update a skill for a persona."""
        self._skills[persona_id] = Skill(skill_data)

    def remove_skill(self, persona_id: str):
        """Remove a skill from the engine."""
        self._skills.pop(persona_id, None)

    def has_skill(self, persona_id: str) -> bool:
        return persona_id in self._skills

    def get_skill(self, persona_id: str) -> Skill | None:
        return self._skills.get(persona_id)

    def build_skill_prompt(self, persona_id: str) -> str:
        """Build the skill-enhanced prompt portion for a persona."""
        skill = self._skills.get(persona_id)
        if skill:
            return skill.build_skill_prompt()
        return ""


_skill_engine_instance: SkillEngine | None = None


def get_skill_engine() -> SkillEngine:
    global _skill_engine_instance
    if _skill_engine_instance is None:
        _skill_engine_instance = SkillEngine()
    return _skill_engine_instance


async def init_skill_engine():
    """Initialize the skill engine by loading all skills from the database."""
    from sqlalchemy import select
    from app.db.database import _get_sessionmaker

    engine = get_skill_engine()
    sm = _get_sessionmaker()
    async with sm() as db:
        result = await db.execute(select(PersonaDB))
        rows = result.scalars().all()
        engine.load_from_rows(list(rows))
