from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Agent runtime
    agent_runtime_image: str = "aviary-runtime:latest"
    max_concurrent_sessions_per_pod: int = 10
    host_gateway_ip: str = "172.18.0.1"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
