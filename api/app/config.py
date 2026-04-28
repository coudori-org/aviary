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

    # CORS — single proxy origin (the browser never hits web directly).
    cors_origins: list[str] = ["http://localhost:3000"]

    # Agent Supervisor
    supervisor_url: str

    # Unset → direct mode (model catalog from config.yaml, MCP disabled).
    llm_gateway_url: str | None = None
    llm_gateway_api_key: str | None = None
    mcp_gateway_url: str | None = None
    mcp_gateway_api_key: str | None = None
    llm_backends_config_path: str = "/workspace/config.yaml"

    # Per-user credentials live at
    # secret/aviary/credentials/{sub}/{namespace}/{key_name}. Leave both
    # empty to fall back to the ``secrets:`` table in config.yaml.
    vault_addr: str = ""
    vault_token: str = ""

    # Temporal — workflow orchestration
    temporal_host: str = "temporal:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "aviary-workflows"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def idp_enabled(self) -> bool:
        return bool(self.oidc_issuer)

    @property
    def direct_llm_mode(self) -> bool:
        return not self.llm_gateway_url

    @property
    def vault_enabled(self) -> bool:
        return bool(self.vault_addr and self.vault_token)


settings = Settings()
