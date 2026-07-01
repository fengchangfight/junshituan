from pydantic import BaseModel, Field
from typing import Optional


# ── Advisor ─────────────────────────────────────────────────────────────────

class AdvisorOut(BaseModel):
    id: str
    name: str
    title: str
    category: str
    era: str
    avatar: str
    short_bio: str = ""
    style: str = ""
    kb_status: str = "empty"
    kb_doc_count: int = 0
    is_published: bool = False


class AdvisorAdminOut(AdvisorOut):
    yaml_config: str = ""
    documents: list["KnowledgeDocOut"] = []


class KnowledgeDocUpload(BaseModel):
    persona_id: str
    filename: str
    content: str
    content_type: str = "text/plain"


class KnowledgeDocOut(BaseModel):
    id: str
    filename: str
    title: str
    content_type: str
    file_path: str = ""
    chunk_count: int
    status: str
    created_at: str
    updated_at: str = ""


class IngestRequest(BaseModel):
    persona_id: str


class PublishRequest(BaseModel):
    persona_id: str
    publish: bool = True


class PersonaCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=256)
    category: str = "其他"
    era: str = ""
    avatar: str = ""
    short_bio: str = ""
    style: str = ""


class PersonaUpdate(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    category: Optional[str] = None
    era: Optional[str] = None
    avatar: Optional[str] = None
    short_bio: Optional[str] = None
    style: Optional[str] = None
    yaml_config: Optional[str] = None


# ── Council / Session ──────────────────────────────────────────────────────

class CreateCouncilRequest(BaseModel):
    advisor_ids: list[str] = Field(min_length=1, max_length=5)
    title: str = ""


class CouncilOut(BaseModel):
    id: str
    advisors: list[AdvisorOut]
    title: str
    created_at: str


class SessionOut(BaseModel):
    id: str
    title: str
    advisor_ids: list[str]
    message_count: int
    is_active: bool
    created_at: str
    updated_at: str


class SessionDetailOut(SessionOut):
    messages: list["MessageOut"] = []


class MessageOut(BaseModel):
    id: str
    sequence: int
    role: str
    advisor_id: Optional[str] = None
    advisor_name: str = ""
    content: str
    created_at: str
    metadata: dict = {}


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class AskEvent(BaseModel):
    advisor_id: str
    advisor_name: str = ""
    content: str = ""
    done: bool = False
    metadata: dict = {}


# ── Auth ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    is_admin: bool


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = ""


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    is_admin: bool
    created_at: str
