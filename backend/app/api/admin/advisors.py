"""Admin API: Knowledge base management for advisors."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.database import get_db
from app.models.db_models import PersonaDB, KnowledgeDocument
from app.models.schemas import (
    AdvisorAdminOut,
    KnowledgeDocOut,
    KnowledgeDocUpload,
    IngestRequest,
    PublishRequest,
    PersonaUpdate,
)
from app.core.security import require_admin
from app.services.ingestion.pipeline import pipeline as ingest_pipeline
from app.services.agent.agent_registry import agent_registry
from app.services.persona_engine import get_persona_engine

router = APIRouter(prefix="/api/admin/advisors", tags=["admin-advisors"])


@router.get("", response_model=list[AdvisorAdminOut])
async def list_advisors(
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    """List all advisors with full admin details."""
    engine = get_persona_engine()
    personas = engine.list_all()

    result = []
    for p in personas:
        db_persona = await db.execute(
            select(PersonaDB).where(PersonaDB.id == p.id)
        )
        db_p = db_persona.scalar_one_or_none()

        docs = []
        if db_p:
            docs_stmt = select(KnowledgeDocument).where(
                KnowledgeDocument.persona_id == p.id
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
                id=p.id,
                name=p.name,
                title=p.title,
                category=p.category,
                era=p.era,
                avatar=p.avatar,
                short_bio=p.short_bio,
                style=p.style,
                yaml_config=db_p.yaml_config if db_p else "",
                kb_status=db_p.kb_status if db_p else "empty",
                kb_doc_count=db_p.kb_doc_count if db_p else 0,
                is_published=db_p.is_published if db_p else False,
                documents=docs,
            )
        )

    return result


@router.get("/{persona_id}", response_model=AdvisorAdminOut)
async def get_advisor(
    persona_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    engine = get_persona_engine()
    p = engine.get(persona_id)
    if not p:
        raise HTTPException(status_code=404, detail="军师不存在")

    db_persona = await db.execute(
        select(PersonaDB).where(PersonaDB.id == persona_id)
    )
    db_p = db_persona.scalar_one_or_none()

    docs = []
    if db_p:
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
        id=p.id,
        name=p.name,
        title=p.title,
        category=p.category,
        era=p.era,
        avatar=p.avatar,
        short_bio=p.short_bio,
        style=p.style,
        yaml_config=db_p.yaml_config if db_p else "",
        kb_status=db_p.kb_status if db_p else "empty",
        kb_doc_count=db_p.kb_doc_count if db_p else 0,
        is_published=db_p.is_published if db_p else False,
        documents=docs,
    )


@router.put("/{persona_id}")
async def update_advisor(
    persona_id: str,
    data: PersonaUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    """Update advisor metadata or YAML config."""
    engine = get_persona_engine()
    p = engine.get(persona_id)
    if not p:
        raise HTTPException(status_code=404, detail="军师不存在")

    # Upsert PersonaDB
    db_persona = await db.execute(
        select(PersonaDB).where(PersonaDB.id == persona_id)
    )
    db_p = db_persona.scalar_one_or_none()

    if not db_p:
        db_p = PersonaDB(
            id=persona_id,
            name=p.name,
            title=p.title,
            category=p.category,
            yaml_config="",
        )
        db.add(db_p)

    if data.name is not None:
        db_p.name = data.name
    if data.title is not None:
        db_p.title = data.title
    if data.category is not None:
        db_p.category = data.category
    if data.yaml_config is not None:
        db_p.yaml_config = data.yaml_config

    await db.commit()
    return {"status": "ok"}


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
    from datetime import datetime, timezone

    doc_id = KnowledgeDocument.make_id(persona_id, filename)
    content_type = _content_type_from_filename(filename)

    # Check if document exists
    existing_stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.persona_id == persona_id,
        KnowledgeDocument.filename == filename,
    )
    result = await db.execute(existing_stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.content = content
        existing.title = title or existing.title
        existing.file_path = file_path or existing.file_path
        existing.content_type = content_type
        existing.status = "pending_reingest"
        existing.chunk_count = 0
        existing.updated_at = datetime.now(timezone.utc)
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
            status="pending",
        )
        db.add(doc)

    # Ensure PersonaDB record exists
    db_persona = await db.execute(
        select(PersonaDB).where(PersonaDB.id == persona_id)
    )
    db_p = db_persona.scalar_one_or_none()
    if not db_p:
        engine = get_persona_engine()
        p = engine.get(persona_id)
        if p:
            db_p = PersonaDB(
                id=persona_id, name=p.name, title=p.title, category=p.category
            )
            db.add(db_p)

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
    admin=Depends(require_admin),
):
    """Upload a knowledge document (.md / .txt only).

    Same filename overwrites previous version. Content change triggers re-ingest.
    """
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
    admin=Depends(require_admin),
):
    """Upload knowledge as raw text input (for the admin UI textarea).

    Same filename overwrites previous version.
    """
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
    admin=Depends(require_admin),
):
    """Ingest all pending documents for a persona into Milvus."""
    db_persona = await db.execute(
        select(PersonaDB).where(PersonaDB.id == req.persona_id)
    )
    db_p = db_persona.scalar_one_or_none()
    if not db_p:
        raise HTTPException(status_code=404, detail="军师不存在")

    # Get all documents that need processing
    docs_stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.persona_id == req.persona_id,
        KnowledgeDocument.status.in_(["pending", "pending_reingest", "error"]),
    )
    docs_result = await db.execute(docs_stmt)
    docs = list(docs_result.scalars().all())

    # Also include already-ingested docs (need to rebuild whole index)
    all_docs_stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.persona_id == req.persona_id,
        KnowledgeDocument.status.in_(["ingested"]),
    )
    all_docs_result = await db.execute(all_docs_stmt)
    ingested_docs = list(all_docs_result.scalars().all())

    all_docs = docs + ingested_docs
    if not all_docs:
        raise HTTPException(status_code=400, detail="该军师没有已上传的知识文档")

    # Update status to ingesting
    db_p.kb_status = "ingesting"
    for d in all_docs:
        d.status = "processing"
    await db.commit()

    try:
        texts = [d.content for d in all_docs]
        sources = [d.filename for d in all_docs]
        total_chunks = await ingest_pipeline.ingest_text(
            req.persona_id, texts, sources
        )

        db_p.kb_status = "ready"
        db_p.kb_doc_count = total_chunks
        db_p.kb_last_ingested = datetime.now(timezone.utc)
        for d in all_docs:
            d.status = "ingested"
            d.chunk_count = total_chunks // len(all_docs) if all_docs else 0

        # Invalidate agent so it picks up new KB
        agent_registry.remove(req.persona_id)

    except Exception as e:
        db_p.kb_status = "error"
        for d in docs:
            d.status = "error"
        raise HTTPException(status_code=500, detail=f"摄入失败: {e}")

    await db.commit()
    return {"status": "ready", "chunks": total_chunks}


@router.post("/publish")
async def publish_advisor(
    req: PublishRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    """Publish/unpublish an advisor for all users."""
    from datetime import datetime, timezone

    db_persona = await db.execute(
        select(PersonaDB).where(PersonaDB.id == req.persona_id)
    )
    db_p = db_persona.scalar_one_or_none()

    if not db_p:
        db_p = PersonaDB(id=req.persona_id, name=req.persona_id)
        db.add(db_p)

    if req.publish and db_p.kb_status != "ready":
        raise HTTPException(status_code=400, detail="请先完成知识库消化再发布")

    db_p.is_published = req.publish
    db_p.published_at = datetime.now(timezone.utc) if req.publish else None
    await db.commit()

    return {"status": "published" if req.publish else "unpublished"}


@router.delete("/{persona_id}/documents/{doc_id}")
async def delete_document(
    persona_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
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
