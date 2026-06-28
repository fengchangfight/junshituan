from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── LLM ─────────────────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-v4-pro"

    # ── Embeddings ──────────────────────────────────────────────────────
    # Dev: set LOCAL_EMBEDDING=true → uses sentence-transformers (free, no API key)
    # Prod: LOCAL_EMBEDDING=false → uses OpenAI text-embedding-3-small via API
    local_embedding: bool = True
    local_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    # OpenAI embedding (prod fallback)
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 512  # bge-small-zh-v1.5 = 512; text-embedding-3-small = 1536
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""

    # ── Budget (per session, CNY) ───────────────────────────────────────
    max_budget_per_session_cny: float = 15.0
    llm_input_price_per_m: float = 2.0
    llm_output_price_per_m: float = 8.0
    embedding_price_per_m: float = 0.5

    # ── Database ────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./data/junshituan.db"

    # ── Milvus (Standalone via Docker) ─────────────────────────────────
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection_prefix: str = "junshituan_kb_"

    # ── Personas & Skills ───────────────────────────────────────────────
    personas_dir: str = "./data/personas"
    skills_dir: str = "./data/skills"
    uploads_dir: str = "./data/uploads"

    # ── Session ─────────────────────────────────────────────────────────
    session_ttl_hours: int = 72
    max_context_tokens: int = 8000
    summary_trigger_tokens: int = 6000

    # ── Memory ──────────────────────────────────────────────────────────
    memory_consolidation_interval: int = 10
    long_term_memory_limit: int = 100

    # ── Auth ────────────────────────────────────────────────────────────
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    admin_users: list[str] = ["admin"]

    # ── CORS ────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
