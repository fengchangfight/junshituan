from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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
    has_real_pw = bool(user.hashed_password) and not verify_password(
        user.username, user.hashed_password
    )
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name or "",
        avatar_url=user.avatar_url or "",
        role=user.role,
        has_password=has_real_pw,
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


class ChangePasswordRequest(BaseModel):
    current_password: str = ""
    new_password: str = Field(min_length=6, max_length=128)


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Change password. Phone users (no password or placeholder) skip old-password check."""
    has_real_password = bool(user.hashed_password) and not verify_password(
        user.username, user.hashed_password
    )
    if has_real_password:
        if not req.current_password:
            raise HTTPException(status_code=400, detail="请输入原密码")
        if not verify_password(req.current_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="原密码错误")

    user.hashed_password = hash_password(req.new_password)
    await db.commit()
    return {"status": "ok", "message": "密码已更新"}


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


# ── Phone SMS Login ────────────────────────────────────────────────────────

class SendCodeRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=11)


class LoginPhoneRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=11)
    code: str = Field(min_length=4, max_length=6)


@router.post("/send-code")
async def send_code(req: SendCodeRequest, db: AsyncSession = Depends(get_db)):
    """Send SMS verification code. Rate-limited: 1 per 60s per phone."""
    import random
    from datetime import datetime, timedelta, timezone
    from app.models.db_models import VerificationCode

    phone = req.phone.strip()
    if not phone.isdigit() or len(phone) != 11:
        raise HTTPException(status_code=400, detail="手机号格式不正确")

    # Rate limit: check last code sent within 60s
    recent = await db.execute(
        select(VerificationCode).where(
            VerificationCode.phone == phone,
            VerificationCode.created_at > datetime.now(timezone.utc) - timedelta(seconds=60),
        )
    )
    if recent.scalar_one_or_none():
        raise HTTPException(status_code=429, detail="请60秒后再试")

    code = f"{random.randint(100000, 999999)}"
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)

    db.add(VerificationCode(phone=phone, code=code, expires_at=expires))
    await db.commit()

    # Send SMS via Alibaba Cloud 号码认证 (dypnsapi)
    sms_sent = False
    sms_error = None
    if settings.alibabacloud_access_key_id:
        try:
            import json as _json
            from alibabacloud_dypnsapi20170525.client import Client
            from alibabacloud_dypnsapi20170525 import models
            from alibabacloud_tea_openapi import models as open_api_models

            cfg = open_api_models.Config(
                access_key_id=settings.alibabacloud_access_key_id,
                access_key_secret=settings.alibabacloud_access_key_secret,
            )
            cfg.endpoint = "dypnsapi.aliyuncs.com"
            client = Client(cfg)

            req = models.SendSmsVerifyCodeRequest(
                phone_number=phone,
                sign_name=settings.sms_sign_name,
                template_code=settings.sms_template_code,
                template_param=_json.dumps({"code": code, "min": "5"}),
            )
            resp = client.send_sms_verify_code(req)
            sms_sent = resp.body.code == "OK"
            print(f"[SMS] sent to {phone}: code={resp.body.code} message={resp.body.message}", flush=True)
        except Exception as e:
            sms_error = str(e)
            print(f"[SMS] FAILED to {phone}: {type(e).__name__}: {e}", flush=True)
            secret_preview = settings.alibabacloud_access_key_secret[:4] + "***" if settings.alibabacloud_access_key_secret else "MISSING"
            print(f"[SMS] config: key_id={'SET' if settings.alibabacloud_access_key_id else 'MISSING'} "
                  f"secret={secret_preview} sign={settings.sms_sign_name} tpl={settings.sms_template_code}", flush=True)
    else:
        print(f"[SMS] SKIPPED (no access key configured) code={code} phone={phone}", flush=True)

    if not sms_sent and settings.alibabacloud_access_key_id:
        raise HTTPException(
            status_code=500,
            detail=f"短信发送失败：{sms_error or '未知错误'}",
        )

    return {"status": "ok", "message": "验证码已发送"}


@router.post("/login-phone", response_model=TokenOut)
async def login_phone(req: LoginPhoneRequest, db: AsyncSession = Depends(get_db)):
    """Login or register via phone + SMS code. Auto-creates account if new."""
    from datetime import datetime, timezone
    from app.models.db_models import VerificationCode

    phone = req.phone.strip()
    code = req.code.strip()

    # Verify code
    vc_result = await db.execute(
        select(VerificationCode).where(
            VerificationCode.phone == phone,
            VerificationCode.code == code,
            VerificationCode.used == False,
            VerificationCode.expires_at > datetime.now(timezone.utc),
        )
    )
    vc = vc_result.scalar_one_or_none()
    if not vc:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    # Mark as used
    vc.used = True
    await db.commit()

    # Find or create user
    result = await db.execute(select(User).where(User.username == phone))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            username=phone,
            display_name=f"用户{phone[-4:]}",
            hashed_password="",  # SMS-only user, set password later
            role=ROLE_USER,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = _make_token(user)
    return _token_response(user, token)
