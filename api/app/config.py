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

    # OIDC
    oidc_issuer: str
    oidc_internal_issuer: str | None = None
    oidc_client_id: str
    oidc_audience: str | None = None

    # Vault
    vault_addr: str
    vault_token: str

    # MCP Gateway
    mcp_gateway_url: str

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Internal API key for service-to-service calls (runtime → API)
    internal_api_key: str

    # Agent Supervisor
    agent_supervisor_url: str

    # LiteLLM Gateway
    litellm_url: str
    litellm_api_key: str

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def cookie_secure(self) -> bool:
        return self.env == "production"


settings = Settings()
