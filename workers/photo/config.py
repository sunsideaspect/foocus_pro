from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://identity:identity@localhost:5432/identity"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "identity-results"
    minio_secure: bool = False
    job_max_retries: int = 3

    foocus_adapter_mode: str = "mock"
    foocus_http_url: str = "http://localhost:8888/generate"
    foocus_cli_command: str = "python /opt/foocus_new/entrypoint.py"


@lru_cache
def get_settings() -> Settings:
    return Settings()
