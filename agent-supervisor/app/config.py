from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Redis broker (shared namespace with API server).
    redis_url: str = "redis://redis:6379/0"

    # Endpoint used when a publish request carries a null runtime_endpoint.
    # Helm sets this to the default environment's Service DNS.
    supervisor_default_runtime_endpoint: str

    # Expose /metrics (Prometheus text format).
    metrics_enabled: bool = True

    # OIDC — the supervisor validates the caller's user JWT (Bearer) and
    # uses the resulting `sub` to look up per-user credentials in Vault.
    oidc_issuer: str
    oidc_internal_issuer: str | None = None
    oidc_audience: str | None = None

    # Vault — per-user credentials (GitHub token, etc.) live at
    # secret/aviary/credentials/{sub}/{key_name}.
    vault_addr: str
    vault_token: str

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
