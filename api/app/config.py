from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Secure-by-default. Set COOKIE_SECURE=false for non-localhost dev (LAN IP, host.docker.internal).
    cookie_secure: bool = True

    # Database
    database_url: str

    # Redis
    redis_url: str

    # OIDC — see .env.example.
    oidc_issuer: str | None = None
    oidc_internal_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    dev_user_sub: str = "dev-user"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Agent Supervisor
    agent_supervisor_url: str

    # LiteLLM Gateway
    litellm_url: str
    litellm_api_key: str

    # Temporal — workflow orchestration
    temporal_host: str = "temporal:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "aviary-workflows"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def idp_enabled(self) -> bool:
        return bool(self.oidc_issuer)


settings = Settings()
