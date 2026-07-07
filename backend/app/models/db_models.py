import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    DateTime,
    Integer,
    ForeignKey,
    JSON,
    Float,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def gen_id():
    return uuid.uuid4().hex[:12]


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_id)
    username = Column(String(64), unique=True, nullable=False, index=True)
    hashed_password = Column(String(256), nullable=False)
    is_admin = Column(Boolean, default=False)  # deprecated, use role
    role = Column(String(16), default="user", nullable=False)  # super_admin | admin | viewer | user
    display_name = Column(String(128), default="")
    avatar_url = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    sessions = relationship("Session", back_populates="user")
    memories = relationship("UserMemory", back_populates="user")


class PersonaDB(Base):
    __tablename__ = "personas"

    id = Column(String, primary_key=True)
    name = Column(String(128), nullable=False)
    title = Column(String(256), default="")
    category = Column(String(64), default="")
    era = Column(String(64), default="")
    avatar = Column(Text, default="")
    short_bio = Column(Text, default="")
    style = Column(Text, default="")

    # Deep persona configuration (was in YAML, now in DB)
    thinking_framework = Column(JSON, default=dict)
    voice = Column(JSON, default=dict)
    core_beliefs = Column(JSON, default=list)
    canonical_works = Column(JSON, default=list)
    knowledge_domain = Column(JSON, default=dict)

    # Legacy YAML raw data (deprecated, kept for migration)
    yaml_config = Column(Text, default="")

    # Knowledge base status
    kb_status = Column(String(32), default="empty")  # empty, ingesting, ready, error
    kb_doc_count = Column(Integer, default=0)
    kb_last_ingested = Column(DateTime(timezone=True), nullable=True)

    # Skill configuration (cognitive operating system)
    skill_config = Column(JSON, default=None)

    # Publication & visibility
    is_published = Column(Boolean, default=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    visibility = Column(String(16), default="public")  # "public" | "private"
    creator_id = Column(String, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    documents = relationship("KnowledgeDocument", back_populates="persona", cascade="all, delete-orphan")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    # ID = persona_id + ":" + filename (unique per persona)
    id = Column(String, primary_key=True)
    persona_id = Column(String, ForeignKey("personas.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(256), nullable=False)
    title = Column(String(256), default="")
    content_type = Column(String(32), default="text/plain")  # text/markdown, text/plain
    content = Column(Text, default="")
    file_path = Column(String(512), default="")  # absolute path for display
    chunk_count = Column(Integer, default=0)
    status = Column(String(32), default="pending")  # pending, processing, ingested, error, pending_reingest
    content_hash = Column(String(64), default="")   # SHA256(title + content) for dedup
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    persona = relationship("PersonaDB", back_populates="documents")

    @staticmethod
    def make_id(persona_id: str, filename: str) -> str:
        import hashlib
        raw = f"{persona_id}:{filename}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(256), default="")
    advisor_ids = Column(JSON, default=list)  # ["zhuge-liang", "sun-zi"]

    # LangGraph checkpoint reference
    checkpoint_id = Column(String(128), nullable=True)
    checkpoint_data = Column(JSON, nullable=True)

    # Summary cache
    conversation_summary = Column(Text, default="")
    message_count = Column(Integer, default=0)
    token_count_estimate = Column(Integer, default=0)

    # Budget tracking
    budget_data = Column(JSON, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.sequence")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=gen_id)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)

    role = Column(String(16), nullable=False)  # user, advisor, system
    advisor_id = Column(String(64), nullable=True)
    advisor_name = Column(String(128), default="")
    content = Column(Text, default="")
    metadata_ = Column("metadata", JSON, default=dict)

    created_at = Column(DateTime(timezone=True), default=utcnow)

    session = relationship("Session", back_populates="messages")


class UserMemory(Base):
    """Hermes-style persistent user memory."""

    __tablename__ = "user_memories"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    memory_type = Column(String(32), nullable=False)  # fact, preference, insight, event
    content = Column(Text, nullable=False)
    importance = Column(Float, default=0.5)  # 0.0-1.0
    source_session_id = Column(String, nullable=True)
    access_count = Column(Integer, default=0)
    last_accessed = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="memories")


class AgentCheckpoint(Base):
    """LangGraph agent state checkpoints for session resume."""

    __tablename__ = "agent_checkpoints"

    id = Column(String, primary_key=True, default=gen_id)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    advisor_id = Column(String(64), nullable=False)
    checkpoint_ns = Column(String(256), default="")
    checkpoint_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class VerificationCode(Base):
    """SMS verification codes for phone login."""

    __tablename__ = "verification_codes"

    id = Column(String, primary_key=True, default=gen_id)
    phone = Column(String(20), nullable=False, index=True)
    code = Column(String(6), nullable=False)
    used = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
