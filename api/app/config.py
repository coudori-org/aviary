from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Set ENV=production in docker-compose / k8s manifests for any
    # deployed environment served over TLS — this auto-flips
    # cookie_secure on.
    env: str = "development"

    # Database
    database_url: str

    # Redis
    redis_url: str

    # OIDC — see aviary_shared.auth.IdpSettings for the canonical schema.
    # `oidc_provider` selects the ClaimMapper (keycloak | okta | generic).
    oidc_provider: str = "keycloak"
    oidc_issuer: str
    oidc_internal_issuer: str | None = None
    oidc_client_id: str
    oidc_audience: str | None = None

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Internal API key for service-to-service calls (runtime → API)
    internal_api_key: str

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
    def cookie_secure(self) -> bool:
        return self.env == "production"


settings = Settings()
