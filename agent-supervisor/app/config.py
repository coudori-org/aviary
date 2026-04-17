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

    # Shared secret authenticating the Temporal workflow worker. When the
    # request carries `X-Aviary-Worker-Key: <this>`, the supervisor trusts
    # `on_behalf_of_sub` from the body as the user identity instead of
    # validating a Bearer JWT. Unset in prod disables the worker path.
    worker_shared_secret: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
