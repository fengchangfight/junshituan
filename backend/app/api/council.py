import json

from fastapi import APIRouter, HTTPException, Depends
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.db_models import User
from app.models.schemas import CreateCouncilRequest, CouncilOut, AskRequest, SessionOut, SessionDetailOut
from app.core.security import require_user
from app.services.council_service import council_service
from app.services.persona_engine import get_persona_engine

router = APIRouter(prefix="/api/council", tags=["council"])


@router.post("", response_model=CouncilOut)
async def create_council(
    req: CreateCouncilRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Create a new meeting room session."""
    engine = get_persona_engine()
    personas = engine.get_many(req.advisor_ids)
    if not personas:
        raise HTTPException(status_code=400, detail="没有有效的军师")

    session = await council_service.create_session(
        db,
        user_id=user.id,
        advisor_ids=req.advisor_ids,
        title=req.title or "",
    )

    return CouncilOut(
        id=session.id,
        advisors=[p.to_api_dict() for p in personas],
        title=session.title,
        created_at=session.created_at.isoformat() if session.created_at else "",
    )


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """List user's active sessions."""
    return await council_service.list_sessions(db, user.id)


@router.get("/sessions/{session_id}", response_model=SessionDetailOut)
async def get_session_detail(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Get full session detail with message history."""
    detail = await council_service.get_session_detail(db, session_id, user.id)
    if not detail:
        raise HTTPException(status_code=404, detail="会话不存在")
    return detail


@router.post("/sessions/{session_id}/ask")
async def ask_council(
    session_id: str,
    req: AskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Ask the council a question in an existing session."""
    # Check if this is a resume (has previous messages)
    session = await council_service.get_session(db, session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    is_resume = session.message_count > 0

    async def event_generator():
        async for event in council_service.ask_council(
            db=db,
            session_id=session_id,
            user_id=user.id,
            user_name=user.display_name or user.username,
            question=req.question,
            is_resume=is_resume,
        ):
            yield {
                "event": "message",
                "data": event.model_dump_json(),
            }

    return EventSourceResponse(event_generator())
