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
    visibility: str = "public"
    creator_id: Optional[str] = None


class AdvisorAdminOut(AdvisorOut):
    thinking_framework: dict = {}
    voice: dict = {}
    core_beliefs: list = []
    canonical_works: list = []
    knowledge_domain: dict = {}
    skill_config: Optional[dict] = None
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
    force: bool = False  # If True, drop collection + docstore, rebuild from scratch


class PublishRequest(BaseModel):
    persona_id: str
    publish: bool = True


class SmartCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class PersonaCreate(BaseModel):
    id: Optional[str] = None
    name: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=256)
    category: str = "其他"
    era: str = ""
    avatar: str = ""
    short_bio: str = ""
    style: str = ""
    thinking_framework: Optional[dict] = None
    voice: Optional[dict] = None
    core_beliefs: Optional[list] = None
    canonical_works: Optional[list] = None
    knowledge_domain: Optional[dict] = None


class PersonaUpdate(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    category: Optional[str] = None
    era: Optional[str] = None
    avatar: Optional[str] = None
    short_bio: Optional[str] = None
    style: Optional[str] = None
    thinking_framework: Optional[dict] = None
    voice: Optional[dict] = None
    core_beliefs: Optional[list] = None
    canonical_works: Optional[list] = None
    knowledge_domain: Optional[dict] = None
    skill_config: Optional[dict] = None
    yaml_config: Optional[str] = None


# ── Council / Session ──────────────────────────────────────────────────────

class CreateCouncilRequest(BaseModel):
    advisor_ids: list[str] = Field(min_length=1, max_length=12)
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
    target_advisor_ids: Optional[list[str]] = None  # if set, only these advisors respond (sequentially)


class AddAdvisorsRequest(BaseModel):
    advisor_ids: list[str] = Field(min_length=1, max_length=12)


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
    role: str = "user"
    avatar_url: str = ""
    display_name: str = ""


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = ""


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    avatar_url: str = ""
    role: str = "user"
    created_at: str


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


class RoleUpdateRequest(BaseModel):
    role: str = Field(min_length=1, max_length=16)
