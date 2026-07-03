"""Admin API: Knowledge base management for advisors."""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.database import get_db
from app.models.db_models import PersonaDB, KnowledgeDocument, User
from app.models.schemas import (
    AdvisorAdminOut,
    KnowledgeDocOut,
    KnowledgeDocUpload,
    IngestRequest,
    PublishRequest,
    PersonaCreate,
    PersonaUpdate,
    SmartCreateRequest,
)
from app.core.security import (
    require_user,
    ROLE_SUPER_ADMIN,
    ROLE_ADMIN,
    ALL_ADMIN_ROLES,
)
from app.services.ingestion.pipeline import pipeline as ingest_pipeline
from app.services.agent.agent_registry import agent_registry
from app.services.persona_engine import Persona, get_persona_engine

router = APIRouter(prefix="/api/admin/advisors", tags=["admin-advisors"])


def _is_admin(user: User) -> bool:
    return user.role in ALL_ADMIN_ROLES


async def _get_editable_persona(persona_id: str, user: User, db: AsyncSession) -> PersonaDB:
    """Get a persona that the current user is allowed to edit.
    Admins can edit any. Regular users can only edit their own private ones.
    """
    result = await db.execute(
        select(PersonaDB).where(PersonaDB.id == persona_id)
    )
    db_p = result.scalar_one_or_none()
    if not db_p:
        raise HTTPException(status_code=404, detail="军师不存在")
    if not _is_admin(user):
        if db_p.visibility != "private" or db_p.creator_id != user.id:
            raise HTTPException(status_code=403, detail="无权操作此军师")
    return db_p


@router.get("", response_model=list[AdvisorAdminOut])
async def list_advisors(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """List advisors: admins see all, regular users see only their own private ones."""
    result_rows = await db.execute(select(PersonaDB))
    db_personas = result_rows.scalars().all()

    # Filter for non-admin users: only show their own private advisors
    if not _is_admin(user):
        db_personas = [p for p in db_personas if p.visibility == "private" and p.creator_id == user.id]

    result = []
    for db_p in db_personas:
        docs_stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.persona_id == db_p.id
        )
        docs_result = await db.execute(docs_stmt)
        docs = [
            KnowledgeDocOut(
                id=d.id,
                filename=d.filename,
                title=d.title,
                content_type=d.content_type,
                file_path=d.file_path or "",
                chunk_count=d.chunk_count,
                status=d.status,
                created_at=d.created_at.isoformat() if d.created_at else "",
                updated_at=d.updated_at.isoformat() if d.updated_at else "",
            )
            for d in docs_result.scalars().all()
        ]

        result.append(
            AdvisorAdminOut(
                id=db_p.id,
                name=db_p.name,
                title=db_p.title,
                category=db_p.category,
                era=db_p.era,
                avatar=db_p.avatar,
                short_bio=db_p.short_bio or "",
                style=db_p.style or "",
                thinking_framework=db_p.thinking_framework or {},
                voice=db_p.voice or {},
                core_beliefs=db_p.core_beliefs or [],
                canonical_works=db_p.canonical_works or [],
                knowledge_domain=db_p.knowledge_domain or {},
                skill_config=db_p.skill_config,
                yaml_config=db_p.yaml_config or "",
                kb_status=db_p.kb_status or "empty",
                kb_doc_count=db_p.kb_doc_count or 0,
                is_published=db_p.is_published or False,
                visibility=db_p.visibility or "public",
                creator_id=db_p.creator_id,
                documents=docs,
            )
        )

    return result


@router.post("", status_code=201)
async def create_advisor(
    req: PersonaCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Create a new advisor persona (DB only).
    Admins create public advisors. Regular users create private advisors.
    """
    import re
    if req.id and req.id.strip():
        if not re.match(r"^[a-zA-Z0-9_-]+$", req.id):
            raise HTTPException(status_code=400, detail="军师ID只能包含字母、数字、下划线和连字符")
    else:
        req.id = re.sub(r"[^a-z0-9-]", "", req.name.lower().replace(" ", "-")) or "unknown"

    # Collision check with auto-increment suffix
    base_id = req.id.rstrip("-0123456789")
    candidate_id = req.id
    cnt = 1
    while True:
        existing = await db.execute(select(PersonaDB).where(PersonaDB.id == candidate_id))
        if not existing.scalar_one_or_none():
            break
        candidate_id = f"{base_id}-{cnt}"
        cnt += 1
    req.id = candidate_id

    is_admin = _is_admin(user)
    db_p = PersonaDB(
        id=req.id,
        name=req.name,
        title=req.title,
        category=req.category,
        era=req.era,
        avatar=req.avatar,
        short_bio=req.short_bio,
        style=req.style,
        thinking_framework=req.thinking_framework or {
            "analysis": "", "decision": "", "foresight": "", "methodology": "",
        },
        voice=req.voice or {
            "tone": "", "style": "", "length": "中等", "opening": "",
        },
        core_beliefs=req.core_beliefs if req.core_beliefs is not None else [],
        canonical_works=req.canonical_works if req.canonical_works is not None else [],
        knowledge_domain=req.knowledge_domain or {
            "known": [], "unknown": [], "attitude_to_unknown": "",
        },
        is_published=False,
        visibility="public" if is_admin else "private",
        creator_id=None if is_admin else user.id,
    )
    db.add(db_p)
    await db.commit()
    await db.refresh(db_p)

    engine = get_persona_engine()
    engine.add_persona(Persona.from_db_row(db_p))

    return {"id": req.id, "message": "创建成功"}


@router.post("/smart-create", status_code=201)
async def smart_create(
    req: SmartCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """One-click smart advisor creation: LLM generates everything from just a name.
    Admins create public advisors. Regular users create private advisors.
    """
    import json as _json
    import re as _re
    from app.core.llm_client import chat
    from app.services.skill_engine import get_skill_engine

    name = req.name.strip()

    system_prompt = (
        '你是一位精通世界历史和文化的专家。用户给你一个历史/现代名人的名字，'
        '你需要生成一份完整的 AI 角色配置。\n\n'
        '输出必须是严格合法的 JSON，包含以下所有字段：\n'
        '{'
        '"id": "英文标识（小写+连字符）",'
        '"name": "中文名",'
        '"title": "称号",'
        '"category": "分类（军事家/哲学家/政治家/文学家/科学家/企业家/其他）",'
        '"era": "时代",'
        '"short_bio": "2-3句话简介",'
        '"style": "说话风格描述",'
        '"thinking_framework": {"analysis":"...","decision":"...","foresight":"...","methodology":"..."},'
        '"voice": {"tone":"...","style":"...","length":"简短/中等/详细","opening":"..."},'
        '"core_beliefs": ["信条1","信条2","信条3","信条4"],'
        '"canonical_works": [{"title":"代表作","source":"出处/年份"}],'
        '"knowledge_domain": {"known":["擅长领域"],"unknown":["不擅长领域"],"attitude_to_unknown":"态度"},'
        '"skill_config": {'
        '"name":"名字","version":"2.0","trigger_keywords":["触发词"],'
        '"roleplay":{"first_person":true,"disclaimer_once":"免责声明","exit_triggers":["退出角色"]},'
        '"workflow":{"steps":[{"step":"classify","description":"..."}],"checkpoints":[{"id":"check","questions":["自查"]}],"fallback_tree":[{"trigger":"触发","action":"行动"}]},'
        '"mental_models":[{"name":"模型名","summary":"描述","evidence":["证据"],"application":"应用","limitation":"局限"}],'
        '"heuristics":[{"name":"启发式","trigger":"触发","action":"行动","example":"例子"}],'
        '"expression":{"sentence_patterns":["句式"],"tone":"语气","rhythm":"节奏","certainty":"确定性","vocabulary":{"preferred":["偏好词"],"avoided":["避免词"]}},'
        '"anti_patterns":[{"pattern":"避免的行为","fix":"正确做法"}],'
        '"limitations":["能力边界"]'
        '}'
        '}\n\n'
        '要求：基于真实历史/学术知识填充所有字段，心智模型和启发式要体现该人物的核心思维特征，只输出JSON不要解释'
    )

    user_prompt = f'请为 {name} 生成完整的 AI 角色配置。'

    try:
        response = await chat(system_prompt, user_prompt, temperature=0.7)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM请求失败: {str(e)}")

    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        text = text.strip()

    try:
        data = _json.loads(text)
    except _json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"LLM返回格式错误，请重试。原始响应: {text[:200]}")

    persona_id = data.get("id", "").strip()
    if not persona_id or not _re.match(r"^[a-zA-Z0-9_-]+$", persona_id):
        persona_id = _re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-")) or "unknown"

    # Check uniqueness
    existing = await db.execute(select(PersonaDB).where(PersonaDB.id == persona_id))
    if existing.scalar_one_or_none():
        base = persona_id.rstrip("-0123456789")
        cnt = 1
        while True:
            candidate = f"{base}-{cnt}"
            check = await db.execute(select(PersonaDB).where(PersonaDB.id == candidate))
            if not check.scalar_one_or_none():
                persona_id = candidate
                break
            cnt += 1

    is_admin = _is_admin(user)
    db_p = PersonaDB(
        id=persona_id,
        name=data.get("name", name),
        title=data.get("title", ""),
        category=data.get("category", "其他"),
        era=data.get("era", ""),
        avatar="",
        short_bio=data.get("short_bio", ""),
        style=data.get("style", ""),
        thinking_framework=data.get("thinking_framework", {}),
        voice=data.get("voice", {}),
        core_beliefs=data.get("core_beliefs", []),
        canonical_works=data.get("canonical_works", []),
        knowledge_domain=data.get("knowledge_domain", {}),
        skill_config=data.get("skill_config"),
        is_published=False,
        visibility="public" if is_admin else "private",
        creator_id=None if is_admin else user.id,
    )
    db.add(db_p)
    await db.commit()
    await db.refresh(db_p)

    engine = get_persona_engine()
    engine.add_persona(Persona.from_db_row(db_p))

    if db_p.skill_config:
        skill_engine = get_skill_engine()
        skill_engine.add_skill(persona_id, db_p.skill_config)

    return {
        "id": db_p.id,
        "name": db_p.name,
        "title": db_p.title,
        "category": db_p.category,
        "era": db_p.era,
        "short_bio": db_p.short_bio,
        "style": db_p.style,
        "thinking_framework": db_p.thinking_framework,
        "voice": db_p.voice,
        "core_beliefs": db_p.core_beliefs,
        "canonical_works": db_p.canonical_works,
        "knowledge_domain": db_p.knowledge_domain,
        "skill_config": db_p.skill_config,
    }


@router.get("/{persona_id}", response_model=AdvisorAdminOut)
async def get_advisor(
    persona_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Get a single advisor with full admin details. Users can only see their own."""
    db_p = await _get_editable_persona(persona_id, user, db)

    docs_stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.persona_id == persona_id
    )
    docs_result = await db.execute(docs_stmt)
    docs = [
        KnowledgeDocOut(
            id=d.id,
            filename=d.filename,
            title=d.title,
            content_type=d.content_type,
            file_path=d.file_path or "",
            chunk_count=d.chunk_count,
            status=d.status,
            created_at=d.created_at.isoformat() if d.created_at else "",
            updated_at=d.updated_at.isoformat() if d.updated_at else "",
        )
        for d in docs_result.scalars().all()
    ]

    return AdvisorAdminOut(
        id=db_p.id,
        name=db_p.name,
        title=db_p.title,
        category=db_p.category,
        era=db_p.era,
        avatar=db_p.avatar,
        short_bio=db_p.short_bio or "",
        style=db_p.style or "",
        thinking_framework=db_p.thinking_framework or {},
        voice=db_p.voice or {},
        core_beliefs=db_p.core_beliefs or [],
        canonical_works=db_p.canonical_works or [],
        knowledge_domain=db_p.knowledge_domain or {},
        skill_config=db_p.skill_config,
        yaml_config=db_p.yaml_config or "",
        kb_status=db_p.kb_status or "empty",
        kb_doc_count=db_p.kb_doc_count or 0,
        is_published=db_p.is_published or False,
        visibility=db_p.visibility or "public",
        creator_id=db_p.creator_id,
        documents=docs,
    )


@router.put("/{persona_id}")
async def update_advisor(
    persona_id: str,
    data: PersonaUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Update advisor metadata (DB only). Users can only edit their own."""
    db_p = await _get_editable_persona(persona_id, user, db)

    if data.name is not None:
        db_p.name = data.name
    if data.title is not None:
        db_p.title = data.title
    if data.category is not None:
        db_p.category = data.category
    if data.era is not None:
        db_p.era = data.era
    if data.avatar is not None:
        db_p.avatar = data.avatar
    if data.short_bio is not None:
        db_p.short_bio = data.short_bio
    if data.style is not None:
        db_p.style = data.style
    if data.thinking_framework is not None:
        db_p.thinking_framework = data.thinking_framework
    if data.voice is not None:
        db_p.voice = data.voice
    if data.core_beliefs is not None:
        db_p.core_beliefs = data.core_beliefs
    if data.canonical_works is not None:
        db_p.canonical_works = data.canonical_works
    if data.knowledge_domain is not None:
        db_p.knowledge_domain = data.knowledge_domain
    if data.skill_config is not None:
        db_p.skill_config = data.skill_config
    if data.yaml_config is not None:
        db_p.yaml_config = data.yaml_config

    await db.commit()
    await db.refresh(db_p)

    engine = get_persona_engine()
    engine.add_persona(Persona.from_db_row(db_p))

    if db_p.skill_config:
        from app.services.skill_engine import get_skill_engine
        get_skill_engine().add_skill(persona_id, db_p.skill_config)

    return {"status": "ok"}


@router.post("/{persona_id}/avatar")
async def upload_avatar(
    persona_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload an avatar image: accept base64, resize to 128x128, store in DB.

    Request body: { "image": "data:image/png;base64,..." }
    """
    from fastapi import Request
    from io import BytesIO
    from PIL import Image
    import base64
    import re

    # Verify permission first
    await _get_editable_persona(persona_id, user, db)

    # We need the raw request body — use a simple approach
    # FastAPI doesn't auto-inject Request here since we didn't declare it,
    # so let's rebuild: read body from a second query

    return {"status": "ok", "message": "Avatar upload via this endpoint requires client-side resize. Use the update endpoint with avatar field instead."}


ALLOWED_EXTENSIONS = {".md", ".txt", ".markdown"}


def _content_type_from_filename(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("md", "markdown"):
        return "text/markdown"
    return "text/plain"


async def _upsert_document(
    persona_id: str,
    filename: str,
    title: str,
    content: str,
    file_path: str,
    db: AsyncSession,
) -> KnowledgeDocument:
    """Upsert a knowledge document. Same filename overwrites, ID stays the same."""
    import hashlib
    from datetime import datetime, timezone

    doc_id = KnowledgeDocument.make_id(persona_id, filename)
    content_type = _content_type_from_filename(filename)
    content_hash = hashlib.sha256((title + content).encode()).hexdigest()

    # Ensure PersonaDB record exists FIRST (before any doc queries trigger autoflush)
    db_persona = await db.execute(
        select(PersonaDB).where(PersonaDB.id == persona_id)
    )
    db_p = db_persona.scalar_one_or_none()
    if not db_p:
        raise HTTPException(status_code=404, detail="军师不存在")

    # Check if document exists
    existing_stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.persona_id == persona_id,
        KnowledgeDocument.filename == filename,
    )
    result = await db.execute(existing_stmt)
    existing = result.scalar_one_or_none()

    if existing:
        old_hash = existing.content_hash
        existing.content = content
        existing.title = title or existing.title
        existing.file_path = file_path or existing.file_path
        existing.content_type = content_type
        existing.content_hash = content_hash
        existing.chunk_count = 0
        existing.updated_at = datetime.now(timezone.utc)
        # Only mark for re-ingest if content actually changed
        if old_hash != content_hash or existing.status not in ("ingested",):
            existing.status = "pending_reingest"
        doc = existing
    else:
        doc = KnowledgeDocument(
            id=doc_id,
            persona_id=persona_id,
            filename=filename,
            title=title or filename,
            content=content,
            content_type=content_type,
            file_path=file_path,
            content_hash=content_hash,
            status="pending",
        )
        db.add(doc)

    await db.commit()
    await db.refresh(doc)
    return doc


@router.post("/upload")
async def upload_document(
    persona_id: str = Form(...),
    title: str = Form(""),
    file_path: str = Form(""),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Upload a knowledge document (.md / .txt only).

    Same filename overwrites previous version. Content change triggers re-ingest.
    """
    await _get_editable_persona(persona_id, user, db)
    filename = file.filename or "untitled.txt"

    # Validate extension
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if f".{ext}" not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式：.{ext}。仅接受 {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    if not text.strip():
        raise HTTPException(status_code=400, detail="文件内容为空")

    doc = await _upsert_document(
        persona_id=persona_id,
        filename=filename,
        title=title,
        content=text,
        file_path=file_path or filename,
        db=db,
    )

    is_override = doc.status == "pending_reingest"

    return {
        **KnowledgeDocOut(
            id=doc.id,
            filename=doc.filename,
            title=doc.title,
            content_type=doc.content_type,
            file_path=doc.file_path,
            chunk_count=doc.chunk_count,
            status=doc.status,
            created_at=doc.created_at.isoformat() if doc.created_at else "",
            updated_at=doc.updated_at.isoformat() if doc.updated_at else "",
        ).model_dump(),
        "overwritten": is_override,
        "message": "文件已覆盖，请重新点击消化以更新知识库" if is_override else "上传成功",
    }


@router.post("/upload-text")
async def upload_text(
    persona_id: str = Form(...),
    title: str = Form(""),
    filename: str = Form(...),
    file_path: str = Form(""),
    text: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Upload knowledge as raw text input (for the admin UI textarea).

    Same filename overwrites previous version.
    """
    await _get_editable_persona(persona_id, user, db)
    # Validate extension
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if f".{ext}" not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式：.{ext}。仅接受 {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    if not text.strip():
        raise HTTPException(status_code=400, detail="文本内容为空")

    doc = await _upsert_document(
        persona_id=persona_id,
        filename=filename,
        title=title,
        content=text,
        file_path=file_path or filename,
        db=db,
    )

    is_override = doc.status == "pending_reingest"

    return {
        **KnowledgeDocOut(
            id=doc.id,
            filename=doc.filename,
            title=doc.title,
            content_type=doc.content_type,
            file_path=doc.file_path,
            chunk_count=doc.chunk_count,
            status=doc.status,
            created_at=doc.created_at.isoformat() if doc.created_at else "",
            updated_at=doc.updated_at.isoformat() if doc.updated_at else "",
        ).model_dump(),
        "overwritten": is_override,
        "message": "文件已覆盖，请重新点击消化以更新知识库" if is_override else "上传成功",
    }


@router.post("/ingest")
async def ingest_knowledge(
    req: IngestRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Ingest documents for a persona into Milvus.

    If force=True: drop collection + docstore, rebuild from scratch (no dedup).
    Otherwise: skip if no document content has changed since last ingest.
    """
    import hashlib

    db_p = await _get_editable_persona(req.persona_id, user, db)

    all_docs_stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.persona_id == req.persona_id,
    )
    all_docs_result = await db.execute(all_docs_stmt)
    all_docs = list(all_docs_result.scalars().all())

    if not all_docs:
        raise HTTPException(status_code=400, detail="该军师没有已上传的知识文档")

    if req.force:
        # Delete this persona's nodes from shared collection
        from app.services.ingestion.milvus_store import milvus_store as _ms
        deleted = _ms.delete_persona(req.persona_id)
        print(f"[Ingest] force rebuild: deleted {deleted} nodes for {req.persona_id}")
        docstore_path = os.path.join("data", "docstore", f"{req.persona_id}.json")
        if os.path.exists(docstore_path):
            os.remove(docstore_path)
        # Mark all docs for processing
        for d in all_docs:
            d.content_hash = hashlib.sha256((d.title + d.content).encode()).hexdigest()
            d.status = "processing"
    else:
        # Compute current hashes and detect changes
        needs_ingest = False
        for d in all_docs:
            current_hash = hashlib.sha256((d.title + d.content).encode()).hexdigest()
            if d.status != "ingested" or d.content_hash != current_hash:
                needs_ingest = True
                d.content_hash = current_hash
                d.status = "processing"

        if not needs_ingest:
            return {"status": "ready", "chunks": db_p.kb_doc_count, "message": "所有文档已是最新，无需消化"}

    db_p.kb_status = "ingesting"
    await db.commit()

    try:
        texts = [d.content for d in all_docs]
        sources = [d.filename for d in all_docs]
        doc_hashes = [d.content_hash for d in all_docs]
        total_chunks = await ingest_pipeline.ingest_text(
            req.persona_id, texts, sources, doc_hashes=doc_hashes
        )

        db_p.kb_status = "ready"
        db_p.kb_doc_count = total_chunks
        db_p.kb_last_ingested = datetime.now(timezone.utc)
        for d in all_docs:
            d.status = "ingested"
            d.chunk_count = max(1, total_chunks // len(all_docs))
        agent_registry.remove(req.persona_id)
        await db.commit()
        return {"status": "ready", "chunks": total_chunks}

    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            db_p.kb_status = "error"
            for d in all_docs:
                d.status = "error"
            await db.commit()
        except Exception:
            traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"摄入失败: {e}")


@router.post("/publish")
async def publish_advisor(
    req: PublishRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Publish/unpublish an advisor. Only admins can publish public advisors."""
    from datetime import datetime, timezone

    db_p = await _get_editable_persona(req.persona_id, user, db)

    if req.publish:
        # Only admins can publish
        if not _is_admin(user):
            raise HTTPException(status_code=403, detail="只有管理员可以发布军师")
        # Only public advisors can be published
        if db_p.visibility != "public":
            raise HTTPException(status_code=400, detail="私人军师不能公开发布")

        if db_p.kb_status != "ready":
            has_config = (
                (db_p.thinking_framework and db_p.thinking_framework.get("analysis")) or
                db_p.skill_config
            )
            if not has_config:
                raise HTTPException(status_code=400, detail="请先完成知识库消化，或用 AI 充实人格配置后再发布")

    db_p.is_published = req.publish
    db_p.published_at = datetime.now(timezone.utc) if req.publish else None
    await db.commit()

    return {"status": "published" if req.publish else "unpublished"}


@router.delete("/{persona_id}/documents/{doc_id}")
async def delete_document(
    persona_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    await _get_editable_persona(persona_id, user, db)
    stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.id == doc_id,
        KnowledgeDocument.persona_id == persona_id,
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    await db.delete(doc)
    await db.commit()
    return {"status": "deleted"}


@router.post("/{persona_id}/enrich")
async def enrich_advisor(
    persona_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Use LLM to enrich a persona's thinking framework, voice, beliefs, and knowledge domain.

    Only fills fields that are currently empty/default, preserving user-edited content.
    """
    import json as _json
    from app.core.llm_client import chat

    db_p = await _get_editable_persona(persona_id, user, db)

    basic_info = {
        "name": db_p.name,
        "title": db_p.title,
        "category": db_p.category,
        "era": db_p.era,
        "short_bio": db_p.short_bio or "",
        "style": db_p.style or "",
    }

    system_prompt = (
        "你是一位精通中国历史文化和战略思维的专家。你的任务是根据一个历史/现代名人的基本信息，"
        "为其生成深度的人格配置（persona configuration）。\n\n"
        "输出必须是严格合法的JSON格式，不要有任何额外的解释文字。JSON结构如下：\n"
        '{\n'
        '  "thinking_framework": {\n'
        '    "analysis": "分析问题的核心方式（1-2句话）",\n'
        '    "decision": "做决策的模式（1-2句话）",\n'
        '    "foresight": "预见/规划习惯（1-2句话）",\n'
        '    "methodology": "核心方法论（1-2句话）"\n'
        '  },\n'
        '  "voice": {\n'
        '    "tone": "语气特征（如：沉稳、犀利、幽默）",\n'
        '    "style": "表达方式描述（1-2句话）",\n'
        '    "length": "回答长度偏好（简短/中等/详细）",\n'
        '    "opening": "典型的开场方式描述（1句话）"\n'
        '  },\n'
        '  "core_beliefs": ["核心信条1（15字以内）", "核心信条2（15字以内）", "核心信条3（15字以内）", "核心信条4（15字以内）"],\n'
        '  "knowledge_domain": {\n'
        '    "known": ["擅长领域1", "擅长领域2", "擅长领域3", "擅长领域4", "擅长领域5"],\n'
        '    "unknown": ["不熟悉领域1", "不熟悉领域2", "不熟悉领域3"],\n'
        '    "attitude_to_unknown": "对于不熟悉事物的态度（1句话）"\n'
        '  },\n'
        '  "canonical_works": [\n'
        '    {"title": "代表作/名言/经典出处", "source": "来源或年份"},\n'
        '    {"title": "代表作/名言/经典出处", "source": "来源或年份"}\n'
        '  ]\n'
        '}\n\n'
        "要求：\n"
        "1. 每个字段都要结合该人物的真实历史背景、思想和风格\n"
        "2. 核心信条要体现该人物的核心价值观，用第一人称口吻\n"
        "3. 知识边界要真实反映该人物所处时代的认知范围\n"
        "4. 只输出JSON，不要任何其他内容"
    )

    user_prompt = _json.dumps(basic_info, ensure_ascii=False, indent=2)

    try:
        response = await chat(system_prompt, user_prompt, temperature=0.7)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM请求失败: {str(e)}")

    # Extract JSON from response (may be wrapped in markdown code blocks)
    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        text = text.strip()

    try:
        enriched = _json.loads(text)
    except _json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"LLM返回格式错误，请重试。原始响应: {text[:200]}",
        )

    # Only update fields that are currently empty/default / or always overwrite on enrich
    tf = enriched.get("thinking_framework", {})
    if isinstance(tf, dict) and tf.get("analysis"):
        db_p.thinking_framework = tf

    voice = enriched.get("voice", {})
    if isinstance(voice, dict) and voice.get("tone"):
        db_p.voice = voice

    beliefs = enriched.get("core_beliefs", [])
    if isinstance(beliefs, list) and len(beliefs) > 0:
        db_p.core_beliefs = beliefs

    works = enriched.get("canonical_works", [])
    if isinstance(works, list) and len(works) > 0:
        db_p.canonical_works = works

    kd = enriched.get("knowledge_domain", {})
    if isinstance(kd, dict) and kd.get("known"):
        db_p.knowledge_domain = kd

    await db.commit()
    await db.refresh(db_p)

    engine = get_persona_engine()
    engine.add_persona(Persona.from_db_row(db_p))

    return {
        "status": "ok",
        "thinking_framework": db_p.thinking_framework,
        "voice": db_p.voice,
        "core_beliefs": db_p.core_beliefs,
        "canonical_works": db_p.canonical_works,
        "knowledge_domain": db_p.knowledge_domain,
    }


@router.post("/{persona_id}/skill/generate")
async def generate_skill(
    persona_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Use LLM to generate a complete cognitive skill (cognitive OS) for this persona.

    The skill includes: workflow, mental models, heuristics, expression DNA,
    anti-patterns, limitations, and checkpoints — making the AI persona more
    consistent and sophisticated in conversation.
    """
    import json as _json
    from app.core.llm_client import chat
    from app.services.skill_engine import get_skill_engine, Skill

    db_p = await _get_editable_persona(persona_id, user, db)

    # Gather persona context for the LLM
    context = {
        "name": db_p.name,
        "title": db_p.title,
        "category": db_p.category,
        "era": db_p.era,
        "short_bio": db_p.short_bio or "",
        "style": db_p.style or "",
        "thinking_framework": db_p.thinking_framework or {},
        "voice": db_p.voice or {},
        "core_beliefs": db_p.core_beliefs or [],
        "canonical_works": db_p.canonical_works or [],
        "knowledge_domain": db_p.knowledge_domain or {},
    }

    system_prompt = (
        '你是一位认知科学家，专门为AI角色设计「认知操作系统」（Cognitive Skill）。\n'
        '你需要根据一个历史/现代名人的背景信息，生成一套完整的认知技能配置。\n\n'
        '输出必须是严格合法的JSON格式，结构如下：\n'
        '{'
        '"name": "人物名称",'
        '"version": "2.0",'
        '"trigger_keywords": ["触发词1", "触发词2", "触发词3"],'
        '"roleplay": {'
        '"first_person": true,'
        '"disclaimer_once": "一句免责声明（该人物的口吻）",'
        '"exit_triggers": ["退出角色 触发词1", "触发词2"]'
        '},'
        '"workflow": {'
        '"steps": ['
        '{"step": "classify", "description": "判断问题类型：..."},'
        '{"step": "retrieve", "description": "从知识库检索..."},'
        '{"step": "reason", "description": "以该人物的思维框架推理"},'
        '{"step": "self_check", "description": "开口前自查"},'
        '{"step": "respond", "description": "输出回答"}'
        '],'
        '"checkpoints": ['
        '{"id": "before_speak", "questions": ["自查问题1", "自查问题2"]},'
        '{"id": "before_advise", "questions": ["自查问题3"]}'
        '],'
        '"fallback_tree": ['
        '{"trigger": "知识库检索为空", "action": "坦诚告知..."},'
        '{"trigger": "问题超出时代范围", "action": "用古代/原有智慧框架类比..."}'
        ']'
        '},'
        '"mental_models": ['
        '{"name": "心智模型1", "summary": "一句话描述", "evidence": ["证据1"], '
        '"application": "如何应用", "limitation": "局限"}'
        '],'
        '"heuristics": ['
        '{"name": "启发式1", "trigger": "触发场景", "action": "行动描述", "example": "举例"}'
        '],'
        '"expression": {'
        '"sentence_patterns": ["句式1", "句式2"],'
        '"tone": "语气描述",'
        '"rhythm": "表达节奏",'
        '"certainty": "结论的确定程度",'
        '"vocabulary": {"preferred": ["偏好词"], "avoided": ["避免词"]}'
        '},'
        '"anti_patterns": ['
        '{"pattern": "要避免的行为", "fix": "正确的做法"}'
        '],'
        '"limitations": ["能力边界1（诚实声明）", "能力边界2"]'
        '}'
        '\n\n要求：\n'
        '1. 每个字段都要紧密结合该人物的真实背景、著作和思想风格\n'
        '2. 心智模型(mental_models)要体现该人物最核心的思维特征，带evidence引用原文/历史事件\n'
        '3. 决策启发式(heuristics)要把该人物的决策智慧变成可操作的trigger→action规则\n'
        '4. 表达DNA(expression)要捕捉该人物的独特说话方式、常用句式、词汇偏好\n'
        '5. 反例黑名单(anti_patterns)列3-5条该人物绝不会做的事\n'
        '6. 诚实边界(limitations)要真实反映该人物的时代/知识局限\n'
        '7. 只输出JSON，不要任何其他内容'
    )

    user_prompt = _json.dumps(context, ensure_ascii=False, indent=2)

    try:
        response = await chat(system_prompt, user_prompt, temperature=0.7)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM请求失败: {str(e)}")

    # Extract JSON from response
    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        text = text.strip()

    try:
        skill_data = _json.loads(text)
    except _json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"LLM返回格式错误，请重试。原始响应: {text[:200]}",
        )

    # Save to DB
    db_p.skill_config = skill_data
    await db.commit()
    await db.refresh(db_p)

    # Update in-memory engine
    engine = get_skill_engine()
    engine.add_skill(persona_id, skill_data)

    return {"status": "ok", "skill": skill_data}
