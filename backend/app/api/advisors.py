from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.db_models import PersonaDB
from app.services.persona_engine import get_persona_engine

router = APIRouter(prefix="/api/advisors", tags=["advisors"])


@router.get("")
async def list_advisors(db: AsyncSession = Depends(get_db)):
    engine = get_persona_engine()
    personas = engine.list_all()

    # Get publish + KB status from DB
    published_ids = set()
    db_stmt = select(PersonaDB).where(PersonaDB.is_published == True)
    result = await db.execute(db_stmt)
    for row in result.scalars().all():
        published_ids.add(row.id)

    # Only return published advisors for public listing
    # If no one is published yet, return all (development convenience)
    if published_ids:
        return [p.to_api_dict() for p in personas if p.id in published_ids]
    return [p.to_api_dict() for p in personas]


@router.get("/{persona_id}")
async def get_advisor(persona_id: str, db: AsyncSession = Depends(get_db)):
    engine = get_persona_engine()
    persona = engine.get(persona_id)
    if not persona:
        return None
    return persona.to_api_dict()
