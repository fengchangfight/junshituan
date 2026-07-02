import sys
from contextlib import asynccontextmanager

# Force UTF-8 on Windows to prevent GBK encoding crashes with emoji
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.database import init_db
from app.api.advisors import router as advisors_router
from app.api.council import router as council_router
from app.api.auth import router as auth_router
from app.api.admin.advisors import router as admin_advisors_router
from app.services.persona_engine import init_persona_engine
from app.services.skill_engine import init_skill_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
        print("Database initialized successfully")
    except Exception as e:
        print(f"WARNING: Database init failed ({e}). Server will start without DB.")
    try:
        await init_persona_engine()
        print("PersonaEngine initialized successfully")
    except Exception as e:
        print(f"WARNING: PersonaEngine init failed ({e}).")
    try:
        await init_skill_engine()
        print("SkillEngine initialized successfully")
    except Exception as e:
        print(f"WARNING: SkillEngine init failed ({e}).")
    yield


app = FastAPI(
    title="军师团 API",
    description="Virtual Advisory Council — LangGraph Agents + Milvus Knowledge Base",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public routes
app.include_router(advisors_router)
app.include_router(auth_router)

# Authenticated routes
app.include_router(council_router)

# Admin routes
app.include_router(admin_advisors_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
