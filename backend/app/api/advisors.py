import time

from fastapi import APIRouter, Depends
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload, defer, load_only
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.db_models import PersonaDB, User
from app.core.security import get_current_user
from app.services.cache import cache
from app.core.logging import get_logger

log = get_logger("advisors")

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
        "creator_name": (p.creator.display_name or p.creator.username or p.creator_id) if p.creator else (p.creator_id or None),
    }


@router.get("")
async def list_advisors(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List advisors: public published + user's own private ones."""
    # ── Cache: skip DB on F5 refresh ──────────────────────────────────────
    t0 = time.time()
    cache_key = "advisors:raw"
    all_personas = cache.get(cache_key)
    if all_personas is None:
        t_query = time.time()
        result = await db.execute(
            select(PersonaDB).options(
                selectinload(PersonaDB.creator).options(
                    load_only(User.id, User.username, User.display_name),
                ),
                defer(PersonaDB.skill_config),
                defer(PersonaDB.thinking_framework),
                defer(PersonaDB.voice),
                defer(PersonaDB.core_beliefs),
                defer(PersonaDB.canonical_works),
                defer(PersonaDB.knowledge_domain),
            )
        )
        all_personas = result.scalars().all()
        cache.set(cache_key, all_personas, ttl=60.0)
        log.info(f"list_advisors DB query took {(time.time() - t_query)*1000:.0f}ms, {len(all_personas)} personas")

    visible = []
    for p in all_personas:
        # Creator always sees their own, regardless of visibility/publish
        if current_user and p.creator_id == current_user.id:
            visible.append(p)
        elif p.visibility == "public" and p.is_published:
            visible.append(p)
        elif p.visibility == "private" and current_user and p.creator_id == current_user.id:
            visible.append(p)

    # Fallback: if nothing visible, show all published (backward compat for old data)
    if not visible:
        visible = [p for p in all_personas if p.is_published]

    result = [_to_dict(p) for p in visible]
    elapsed = (time.time() - t0) * 1000
    log.info(f"list_advisors DONE {len(result)} visible in {elapsed:.0f}ms")
    return result


@router.get("/{persona_id}")
async def get_advisor(
    persona_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(PersonaDB).where(PersonaDB.id == persona_id).options(
            selectinload(PersonaDB.creator).options(
                load_only(User.id, User.username, User.display_name),
            ),
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        return None
    # Creator always sees their own, regardless of visibility/publish
    if current_user and p.creator_id == current_user.id:
        return _to_dict(p)
    # Allow access to public published or user's own private
    if p.visibility == "public" and p.is_published:
        return _to_dict(p)
    if p.visibility == "private" and current_user and p.creator_id == current_user.id:
        return _to_dict(p)
    # Fallback for old data
    if p.is_published:
        return _to_dict(p)
    return None
