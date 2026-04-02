from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://aviary:aviary@localhost:5432/aviary"
    redis_url: str = "redis://localhost:6379/0"
    agent_controller_url: str = "http://localhost:9000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
