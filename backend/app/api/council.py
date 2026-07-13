from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.db_models import User, PersonaDB
from app.models.schemas import CreateCouncilRequest, CouncilOut, AskRequest, SessionOut, SessionDetailOut, AddAdvisorsRequest, RenameSessionRequest
from app.core.security import require_user, get_current_user
from app.services.council_service import council_service
from app.services.persona_engine import get_persona_engine
from sqlalchemy import select

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


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Delete a council session and all its messages/checkpoints."""
    deleted = await council_service.delete_session(db, session_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在或无权操作")
    return {"status": "deleted"}


@router.patch("/sessions/{session_id}")
async def rename_session(
    session_id: str,
    req: RenameSessionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Rename a council session."""
    from app.services.memory.session_store import session_store
    session = await council_service.get_session(db, session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无权操作")
    await session_store.rename_session(db, session_id, req.title.strip())
    return {"status": "ok", "title": req.title.strip()}


@router.put("/sessions/{session_id}/advisors")
async def add_advisors(
    session_id: str,
    req: AddAdvisorsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Add advisors to an ongoing council session."""
    ok = await council_service.add_advisors(db, session_id, user.id, req.advisor_ids)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权操作")
    return {"status": "ok", "message": f"已邀请 {len(req.advisor_ids)} 位军师加入议事厅"}


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


@router.get("/sessions/{session_id}/export", response_class=HTMLResponse)
async def export_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    token: str = None,
):
    """Export session as a self-contained HTML page for sharing.

    Designed for mobile-width viewing (~420px) so it renders well in
    WeChat's built-in browser and is screenshot-friendly.

    Accepts optional ?token= query param for direct URL access (WeChat
    can't send auth headers).
    """
    # If token provided via query param, use it to authenticate
    if token and not user:
        from app.core.security import decode_token
        from app.models.db_models import User as U
        from sqlalchemy import select as sa_select
        try:
            payload = decode_token(token)
            uid = payload.get("sub")
            if uid:
                r = await db.execute(sa_select(U).where(U.id == uid))
                user = r.scalar_one_or_none()
        except Exception:
            user = None

    if not user:
        raise HTTPException(status_code=401, detail="请先登录")

    detail = await council_service.get_session_detail(db, session_id, user.id)
    if not detail:
        raise HTTPException(status_code=404, detail="会话不存在")

    # Load advisor avatars
    advisor_ids = detail.get("advisor_ids") or []
    avatars: dict[str, str] = {}
    if advisor_ids:
        result = await db.execute(
            select(PersonaDB.id, PersonaDB.avatar, PersonaDB.name).where(
                PersonaDB.id.in_(advisor_ids)
            )
        )
        for row in result:
            avatars[row[0]] = row[1] or ""

    messages = detail.get("messages") or []
    title = detail.get("title") or "议事厅"

    # ── Build HTML ──────────────────────────────────────────────────────
    message_html_parts = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        advisor_id = m.get("advisor_id") or ""
        advisor_name = m.get("advisor_name") or ""
        avatar_url = avatars.get(advisor_id, "")

        if role == "user":
            message_html_parts.append(f"""\
    <div class="msg msg-user">
      <div class="bubble bubble-user">{content}</div>
    </div>""")
        elif role == "system":
            message_html_parts.append(f"""\
    <div class="msg msg-system">
      <span>{content}</span>
    </div>""")
        else:
            avatar_html = ""
            if avatar_url:
                avatar_html = f'<img src="{avatar_url}" class="avatar" alt="{advisor_name}" onerror="this.style.display=\'none\'">'
            else:
                initial = advisor_name[0] if advisor_name else "?"
                avatar_html = f'<div class="avatar avatar-fallback">{initial}</div>'

            message_html_parts.append(f"""\
    <div class="msg msg-advisor">
      {avatar_html}
      <div class="msg-body">
        <div class="advisor-name">{advisor_name}</div>
        <div class="bubble bubble-advisor">{content}</div>
      </div>
    </div>""")

    # Escape title for HTML attribute safety
    safe_title = title.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta property="og:title" content="{safe_title}">
<meta property="og:description" content="共 {len(messages)} 条对话记录">
<meta property="og:type" content="article">
<meta property="og:site_name" content="议事厅">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: #0f0f1a;
    color: #d0cfd4;
    max-width: 420px;
    margin: 0 auto;
    padding: 16px 12px 32px;
    line-height: 1.6;
  }}
  .header {{
    text-align: center;
    padding: 20px 0 16px;
    border-bottom: 1px solid rgba(180,140,60,0.25);
    margin-bottom: 16px;
  }}
  .header h1 {{
    font-size: 20px;
    color: #d4852c;
    letter-spacing: 2px;
    margin-bottom: 4px;
  }}
  .header .meta {{
    font-size: 11px;
    color: #6b6b7b;
    margin-top: 4px;
  }}
  .msg {{ margin-bottom: 8px; }}
  .msg-user {{ display: flex; justify-content: flex-end; }}
  .msg-system {{ display: flex; justify-content: center; padding: 8px 0; }}
  .msg-system span {{
    font-size: 11px;
    color: #6b6b7b;
    background: rgba(255,255,255,0.04);
    padding: 4px 12px;
    border-radius: 12px;
  }}
  .msg-advisor {{ display: flex; gap: 8px; align-items: flex-start; }}
  .bubble {{
    max-width: 80%;
    padding: 10px 14px;
    border-radius: 16px;
    font-size: 14px;
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
  }}
  .bubble-user {{
    background: linear-gradient(135deg, #b86b2a, #d4852c);
    color: #fff;
    border-bottom-right-radius: 4px;
  }}
  .bubble-advisor {{
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.08);
    border-top-left-radius: 4px;
  }}
  .avatar {{
    width: 36px; height: 36px;
    border-radius: 50%;
    object-fit: cover;
    flex-shrink: 0;
    margin-top: 2px;
  }}
  .avatar-fallback {{
    width: 36px; height: 36px;
    border-radius: 50%;
    background: linear-gradient(135deg, #2a2a3e, #3a3a4e);
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; font-weight: bold;
    color: #d0cfd4;
    flex-shrink: 0;
    margin-top: 2px;
  }}
  .msg-body {{ min-width: 0; }}
  .advisor-name {{
    font-size: 11px;
    font-weight: 600;
    color: #90909e;
    margin-bottom: 3px;
    margin-left: 2px;
  }}
  .footer {{
    text-align: center;
    margin-top: 24px;
    padding-top: 12px;
    border-top: 1px solid rgba(255,255,255,0.06);
    font-size: 10px;
    color: #4a4a5a;
  }}
  .share-bar {{
    margin: 12px 0;
    padding: 12px;
    border-radius: 12px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.06);
  }}
  .share-wechat {{
    display: none;
    text-align: center;
  }}
  .share-wechat .arrow-hint {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border-radius: 20px;
    background: rgba(7,193,96,0.15);
    border: 1px solid rgba(7,193,96,0.3);
    color: #07c160;
    font-size: 13px;
    font-weight: 600;
  }}
  .share-wechat .detail {{
    font-size: 11px;
    color: #6b6b7b;
    margin-top: 6px;
    line-height: 1.6;
  }}
  .share-normal {{
    display: none;
    text-align: center;
  }}
  .share-btn {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 10px 20px;
    border-radius: 24px;
    border: none;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    color: #fff;
    background: linear-gradient(135deg, #07c160, #06ad56);
    box-shadow: 0 2px 8px rgba(7,193,96,0.3);
    transition: transform 0.15s;
  }}
  .share-btn:active {{ transform: scale(0.96); }}
  .share-hint {{
    text-align: center;
    font-size: 11px;
    color: #6b6b7b;
    margin-top: 8px;
  }}
  @media (max-width: 420px) {{
    body {{ padding: 12px 8px 24px; }}
    .bubble {{ font-size: 13px; padding: 8px 12px; }}
  }}
</style>
<script>
(function() {{
  var ua = navigator.userAgent || '';
  var isWeChat = /MicroMessenger/i.test(ua);

  function show(el) {{ if (el) el.style.display = 'block'; }}
  function copyUrl() {{
    var ta = document.createElement('textarea');
    ta.value = window.location.href;
    ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try {{ document.execCommand('copy'); }}
    catch(e) {{}}
    document.body.removeChild(ta);
  }}

  document.addEventListener('DOMContentLoaded', function() {{
    if (isWeChat) {{
      // WeChat browser: only way is the 3-dot menu
      show(document.getElementById('shareWxTop'));
      show(document.getElementById('shareWxBottom'));
    }} else {{
      // Regular browser: try Web Share API, fallback to copy
      show(document.getElementById('shareNormalTop'));
      show(document.getElementById('shareNormalBottom'));
      var fn = function() {{
        if (navigator.share) {{
          navigator.share({{
            title: '{safe_title}',
            text: '议事厅对话：{safe_title}',
            url: window.location.href,
          }}).catch(function(){{}});
        }} else {{
          copyUrl();
          var h = document.getElementById('shareHint');
          if (h) {{ h.style.display = 'block'; h.textContent = '链接已复制，可粘贴到微信发送给朋友'; }}
        }}
      }};
      var b1 = document.getElementById('shareBtn');
      var b2 = document.getElementById('shareBtn2');
      if (b1) b1.onclick = fn;
      if (b2) b2.onclick = fn;
    }}
  }});
}})();
</script>
</head>
<body>
<div class="header">
  <h1>⚔️ {title}</h1>
  <div class="meta">{len(messages)} 条消息</div>
</div>

<div class="share-bar" id="shareWxTop">
  <div class="share-wechat">
    <div class="arrow-hint">📤 点击右上角 <b>···</b> → 分享给朋友</div>
    <div class="detail">微信内分享需通过右上角菜单。<br>发送给朋友或分享到朋友圈后，对方点击链接即可查看。</div>
  </div>
</div>

<div class="share-bar" id="shareNormalTop">
  <div class="share-normal">
    <button class="share-btn" id="shareBtn">📤 分享 / 复制链接</button>
  </div>
</div>

<div class="messages">
{chr(10).join(message_html_parts)}
</div>

<div class="share-bar" id="shareNormalBottom">
  <div class="share-normal">
    <button class="share-btn" id="shareBtn2">📤 分享 / 复制链接</button>
  </div>
</div>
<div class="share-bar" id="shareWxBottom">
  <div class="share-wechat">
    <div class="arrow-hint">📤 点击右上角 <b>···</b> → 分享给朋友</div>
  </div>
</div>

<div class="share-hint" id="shareHint" style="display:none">链接已复制，可粘贴到微信发送给朋友</div>

<div class="footer">
  由 议事厅 导出
</div>
</body>
</html>"""

    return HTMLResponse(content=html, status_code=200)


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
            target_advisor_ids=req.target_advisor_ids,
            use_web_search=req.use_web_search,
        ):
            yield {
                "event": "message",
                "data": event.model_dump_json(),
            }

    return EventSourceResponse(event_generator())
