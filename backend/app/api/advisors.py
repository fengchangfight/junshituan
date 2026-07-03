from fastapi import APIRouter, Depends
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.db_models import PersonaDB
from app.core.security import get_current_user

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
        "visibility": p.visibility or "public",
        "creator_id": p.creator_id,
    }


@router.get("")
async def list_advisors(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List advisors: public published + user's own private ones."""
    result = await db.execute(select(PersonaDB))
    all_personas = result.scalars().all()

    visible = []
    for p in all_personas:
        if p.visibility == "public" and p.is_published:
            visible.append(p)
        elif p.visibility == "private" and current_user and p.creator_id == current_user.id:
            visible.append(p)

    # Fallback: if nothing visible, show all published (backward compat for old data)
    if not visible:
        visible = [p for p in all_personas if p.is_published]

    return [_to_dict(p) for p in visible]


@router.get("/{persona_id}")
async def get_advisor(
    persona_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(PersonaDB).where(PersonaDB.id == persona_id))
    p = result.scalar_one_or_none()
    if not p:
        return None
    # Allow access to public published or user's own private
    if p.visibility == "public" and p.is_published:
        return _to_dict(p)
    if p.visibility == "private" and current_user and p.creator_id == current_user.id:
        return _to_dict(p)
    # Fallback for old data
    if p.is_published:
        return _to_dict(p)
    return None
