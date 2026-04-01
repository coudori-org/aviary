from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Agent runtime
    agent_runtime_image: str = "aviary-runtime:latest"
    max_concurrent_sessions_per_pod: int = 10
    host_gateway_ip: str  # Required — injected via K8s manifest env var

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
