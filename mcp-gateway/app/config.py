from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://aviary:aviary@localhost:5432/aviary"

    # OIDC (same dual-URL pattern as API server)
    oidc_issuer: str = "http://localhost:8080/realms/aviary"
    oidc_internal_issuer: str | None = None
    oidc_client_id: str = "aviary-web"
    oidc_audience: str | None = None

    # Vault
    vault_addr: str = "http://vault:8200"
    vault_token: str = "dev-root-token"

    # Server
    mcp_gateway_port: int = 8100

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
