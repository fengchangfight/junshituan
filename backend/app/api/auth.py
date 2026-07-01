from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.db_models import User
from app.models.schemas import LoginRequest, TokenOut, UserCreate, UserOut, ProfileUpdate
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    require_admin,
    require_user,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.username == req.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(user.id, user.username, user.is_admin)
    return TokenOut(
        access_token=token,
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        avatar_url=user.avatar_url or "",
        display_name=user.display_name or "",
    )


@router.post("/register", response_model=TokenOut)
async def register(req: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=req.username,
        hashed_password=hash_password(req.password),
        display_name=req.display_name or req.username,
        is_admin=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id, user.username, user.is_admin)
    return TokenOut(
        access_token=token,
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        avatar_url=user.avatar_url or "",
        display_name=user.display_name or "",
    )


@router.post("/admin/create", response_model=TokenOut)
async def create_admin(req: UserCreate, db: AsyncSession = Depends(get_db)):
    admin_check = await db.execute(select(User).where(User.is_admin == True))
    if admin_check.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="管理员已存在，请登录后操作")

    existing = await db.execute(select(User).where(User.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=req.username,
        hashed_password=hash_password(req.password),
        display_name=req.display_name or req.username,
        is_admin=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id, user.username, user.is_admin)
    return TokenOut(
        access_token=token,
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        avatar_url=user.avatar_url or "",
        display_name=user.display_name or "",
    )


@router.get("/me", response_model=UserOut)
async def get_profile(user: User = Depends(require_user)):
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name or "",
        avatar_url=user.avatar_url or "",
        is_admin=user.is_admin,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


@router.put("/profile")
async def update_profile(
    req: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Update display name and/or avatar (base64 data URI)."""
    if req.display_name is not None:
        user.display_name = req.display_name
    if req.avatar_url is not None:
        user.avatar_url = req.avatar_url
    await db.commit()
    await db.refresh(user)
    return {"status": "ok", "avatar_url": user.avatar_url, "display_name": user.display_name}
