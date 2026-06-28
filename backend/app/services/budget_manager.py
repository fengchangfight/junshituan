"""Session budget management.

Tracks token usage and cost per session, enforcing spending caps.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.db_models import Session


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    embedding_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.embedding_tokens

    @property
    def cost_cny(self) -> float:
        return (
            self.input_tokens / 1_000_000 * settings.llm_input_price_per_m
            + self.output_tokens / 1_000_000 * settings.llm_output_price_per_m
            + self.embedding_tokens / 1_000_000 * settings.embedding_price_per_m
        )


@dataclass
class SessionBudget:
    session_id: str
    max_budget: float = field(default_factory=lambda: settings.max_budget_per_session_cny)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_embedding_tokens: int = 0
    total_cost_cny: float = 0.0
    over_budget: bool = False

    @property
    def remaining_budget(self) -> float:
        return max(0.0, self.max_budget - self.total_cost_cny)

    @property
    def budget_percent(self) -> float:
        if self.max_budget <= 0:
            return 0.0
        return min(100.0, self.total_cost_cny / self.max_budget * 100)

    def can_spend(self, estimated_cost: float = 0.005) -> bool:
        """Check if we can afford another operation."""
        return self.total_cost_cny + estimated_cost <= self.max_budget

    def add_usage(self, usage: TokenUsage) -> float:
        """Record token usage, return the cost of this usage."""
        cost = usage.cost_cny
        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens
        self.total_embedding_tokens += usage.embedding_tokens
        self.total_cost_cny += cost
        if self.total_cost_cny >= self.max_budget:
            self.over_budget = True
        return cost

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "max_budget": self.max_budget,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_embedding_tokens": self.total_embedding_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens + self.total_embedding_tokens,
            "total_cost_cny": round(self.total_cost_cny, 4),
            "remaining_budget": round(self.remaining_budget, 4),
            "budget_percent": round(self.budget_percent, 2),
            "over_budget": self.over_budget,
        }


class BudgetManager:
    """Manages per-session budgets in memory with DB persistence."""

    def __init__(self):
        self._sessions: dict[str, SessionBudget] = {}

    def get(self, session_id: str) -> SessionBudget:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionBudget(session_id=session_id)
        return self._sessions[session_id]

    async def load_from_db(self, session_id: str, db: AsyncSession):
        """Load budget state from DB into memory."""
        from sqlalchemy import select
        stmt = select(Session).where(Session.id == session_id)
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        if session and session.budget_data:
            budget = SessionBudget(
                session_id=session_id,
                max_budget=session.budget_data.get("max_budget", settings.max_budget_per_session_cny),
                total_input_tokens=session.budget_data.get("total_input_tokens", 0),
                total_output_tokens=session.budget_data.get("total_output_tokens", 0),
                total_embedding_tokens=session.budget_data.get("total_embedding_tokens", 0),
                total_cost_cny=session.budget_data.get("total_cost_cny", 0.0),
                over_budget=session.budget_data.get("over_budget", False),
            )
            self._sessions[session_id] = budget

    async def persist(self, session_id: str, db: AsyncSession):
        """Persist budget state to DB."""
        budget = self._sessions.get(session_id)
        if not budget:
            return
        await db.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(
                budget_data=budget.to_dict(),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    def check_budget(self, session_id: str) -> SessionBudget:
        """Get budget, raise loud warning if over."""
        budget = self.get(session_id)
        return budget

    def estimate_chat_cost(self, input_chars: int) -> float:
        """Estimate cost for a chat message. ~2 chars per token for Chinese."""
        est_tokens = input_chars // 2
        est_output = est_tokens * 3
        usage = TokenUsage(input_tokens=est_tokens, output_tokens=est_output)
        return usage.cost_cny

    def _input_price(self) -> float:
        return settings.llm_input_price_per_m

    def _output_price(self) -> float:
        return settings.llm_output_price_per_m


budget_manager = BudgetManager()
