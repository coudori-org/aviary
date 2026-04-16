from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Redis broker (shared namespace with API server).
    redis_url: str = "redis://redis:6379/0"

    # Endpoint used when a publish request carries a null runtime_endpoint.
    # Helm sets this to the default environment's Service DNS.
    supervisor_default_runtime_endpoint: str

    # Expose /metrics (Prometheus text format).
    metrics_enabled: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
