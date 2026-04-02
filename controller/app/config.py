from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Agent runtime
    agent_runtime_image: str = "aviary-runtime:latest"
    max_concurrent_sessions_per_pod: int = 5
    host_gateway_ip: str  # Required — injected via K8s manifest env var

    # Database
    database_url: str = "postgresql+asyncpg://aviary:aviary@localhost:5432/aviary"

    # Scaling
    scaling_check_interval: int = 30
    sessions_per_pod_scale_up: int = 3
    sessions_per_pod_scale_down: int = 1

    # Idle cleanup
    agent_idle_timeout: int = 604800  # 7 days in seconds
    idle_cleanup_interval: int = 300  # 5 minutes

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
