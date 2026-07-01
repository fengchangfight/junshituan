from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.db_models import PersonaDB

router = APIRouter(prefix="/api/advisors", tags=["advisors"])


def _to_dict(p: PersonaDB) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "title": p.title,
        "category": p.category,
        "era": p.era,
        "avatar": p.avatar,
        "short_bio": p.short_bio,
        "style": p.style,
    }


@router.get("")
async def list_advisors(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PersonaDB))
    all_personas = result.scalars().all()

    published = [p for p in all_personas if p.is_published]
    result_list = published if published else all_personas

    return [_to_dict(p) for p in result_list]


@router.get("/{persona_id}")
async def get_advisor(persona_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PersonaDB).where(PersonaDB.id == persona_id))
    p = result.scalar_one_or_none()
    if not p:
        return None
    return _to_dict(p)
