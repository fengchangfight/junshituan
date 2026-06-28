from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # Database (PostgreSQL in prod, SQLite for dev)
    database_url: str = "sqlite+aiosqlite:///./data/junshituan.db"
    use_postgres: bool = False

    # Milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection_prefix: str = "junshituan_kb_"
    # Set to True to use embedded Milvus Lite
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
