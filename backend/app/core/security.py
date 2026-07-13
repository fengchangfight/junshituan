from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_db

security_scheme = HTTPBearer(auto_error=False)

ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"
ROLE_USER = "user"

EDITOR_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN}
ALL_ADMIN_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_VIEWER}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str, username: str, role: str, display_name: str = "", avatar_url: str = "") -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "display_name": display_name or username,
        "avatar_url": avatar_url or "",
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Get current user from JWT token. Returns None if no valid token."""
    if credentials is None:
        return None

    try:
        payload = decode_token(credentials.credentials)
        user_id = payload.get("sub")
        if not user_id:
            return None
    except JWTError:
        return None

    from app.models.db_models import User
    from app.core.logging import set_log_user
    from app.services.cache import cache

    cache_key = f"user:{user_id}"
    user = cache.get(cache_key)
    if user is None:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is not None:
            cache.set(cache_key, user, ttl=10.0)

    if user:
        set_log_user(user.username)
    return user


async def require_user(
    current_user=Depends(get_current_user),
):
    """Require authenticated user. Raises 401 if not authenticated."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return current_user


async def require_admin(
    current_user=Depends(require_user),
):
    """Require any admin role (super_admin, admin, or viewer)."""
    if current_user.role not in ALL_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


async def require_editor(
    current_user=Depends(require_user),
):
    """Require editor role (super_admin or admin). Viewer is NOT an editor."""
    if current_user.role not in EDITOR_ROLES:
        raise HTTPException(status_code=403, detail="需要编辑权限")
    return current_user


async def require_super_admin(
    current_user=Depends(require_user),
):
    """Require super_admin role."""
    if current_user.role != ROLE_SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="需要超级管理员权限")
    return current_user
