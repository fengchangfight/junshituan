from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.db_models import User
from app.models.schemas import (
    LoginRequest,
    TokenOut,
    UserCreate,
    UserOut,
    ProfileUpdate,
    RoleUpdateRequest,
)
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    require_user,
    require_super_admin,
    ROLE_SUPER_ADMIN,
    ROLE_USER,
    ALL_ADMIN_ROLES,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _make_token(user: User) -> str:
    return create_access_token(user.id, user.username, user.role)


def _token_response(user: User, token: str) -> TokenOut:
    return TokenOut(
        access_token=token,
        user_id=user.id,
        username=user.username,
        role=user.role,
        avatar_url=user.avatar_url or "",
        display_name=user.display_name or "",
    )


@router.post("/login", response_model=TokenOut)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.username == req.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = _make_token(user)
    return _token_response(user, token)


@router.post("/register", response_model=TokenOut)
async def register(req: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=req.username,
        hashed_password=hash_password(req.password),
        display_name=req.display_name or req.username,
        role=ROLE_USER,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = _make_token(user)
    return _token_response(user, token)


@router.post("/admin/create", response_model=TokenOut)
async def create_admin(req: UserCreate, db: AsyncSession = Depends(get_db)):
    """Bootstrap first super admin (only works if no admin exists)."""
    admin_check = await db.execute(select(User).where(User.role.in_(ALL_ADMIN_ROLES)))
    if admin_check.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="管理员已存在，请登录后操作")

    existing = await db.execute(select(User).where(User.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=req.username,
        hashed_password=hash_password(req.password),
        display_name=req.display_name or req.username,
        role=ROLE_SUPER_ADMIN,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = _make_token(user)
    return _token_response(user, token)


@router.get("/me", response_model=UserOut)
async def get_profile(user: User = Depends(require_user)):
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name or "",
        avatar_url=user.avatar_url or "",
        role=user.role,
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


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    req: RoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _super: User = Depends(require_super_admin),
):
    """Super admin only: change another user's role."""
    if req.role not in (ROLE_SUPER_ADMIN, "admin", "viewer", ROLE_USER):
        raise HTTPException(status_code=400, detail="无效的角色")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.id == _super.id:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")

    target.role = req.role
    await db.commit()
    return {"status": "ok", "user_id": user_id, "role": req.role}
