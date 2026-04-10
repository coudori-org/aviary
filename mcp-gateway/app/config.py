from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str

    # OIDC
    oidc_issuer: str
    oidc_internal_issuer: str | None = None
    oidc_client_id: str
    oidc_audience: str | None = None

    # Vault
    vault_addr: str
    vault_token: str

    # Server
    mcp_gateway_port: int = 8100

    # Platform servers config file path
    platform_servers_config: str = "/app/config/platform-servers.yaml"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
