from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM — default to DeepSeek
    openai_api_key: str = ""
    openai_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-v4-pro"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    # For embeddings we fall back to OpenAI if DeepSeek doesn't support them
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""

    # Budget (per session, in CNY)
    max_budget_per_session_cny: float = 15.0
    # Pricing per 1M tokens (CNY) — override via env
    llm_input_price_per_m: float = 2.0   # default: deepseek-chat input
    llm_output_price_per_m: float = 8.0  # default: deepseek-chat output
    embedding_price_per_m: float = 0.5   # default: text-embedding-3-small

    # Database (SQLite for dev, PostgreSQL for prod via Docker)
    database_url: str = "sqlite+aiosqlite:///./data/junshituan.db"

    # Milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection_prefix: str = "junshituan_kb_"
    milvus_lite: bool = True
    milvus_lite_db_path: str = "./data/milvus_lite.db"

    # Personas
    personas_dir: str = "./data/personas"
    uploads_dir: str = "./data/uploads"

    # Session
    session_ttl_hours: int = 72
    max_context_tokens: int = 8000
    summary_trigger_tokens: int = 6000

    # Memory (Hermes-style)
    memory_consolidation_interval: int = 10
    long_term_memory_limit: int = 100

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    admin_users: list[str] = ["admin"]

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
