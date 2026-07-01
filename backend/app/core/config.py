from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── LLM ─────────────────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-v4-pro"

    # ── Embeddings (Zhipu embedding-2) ──────────────────────────────────
    embedding_api_key: str = ""
    embedding_model: str = "embedding-2"
    embedding_dim: int = 1024
    embedding_base_url: str = "https://open.bigmodel.cn/api/paas/v4"

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

    # ── Uploads ──────────────────────────────────────────────────────────
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
