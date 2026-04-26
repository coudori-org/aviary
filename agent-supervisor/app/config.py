from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Redis broker (shared namespace with API server).
    redis_url: str = "redis://redis:6379/0"

    # Endpoint used when a publish request carries a null runtime_endpoint.
    # Helm sets this to the default environment's Service DNS.
    supervisor_default_runtime_endpoint: str

    # OTel metrics — pushed via OTLP/HTTP. Standard OTEL_* envvars are read
    # by the SDK directly. Export is enabled iff OTEL_EXPORTER_OTLP_ENDPOINT
    # is set (checked at startup in main.py).
    otel_metric_export_interval_ms: int = 60000

    # OIDC — see .env.example.
    oidc_issuer: str | None = None
    oidc_internal_issuer: str | None = None
    dev_user_sub: str = "dev-user"

    # Vault — per-user credentials live at
    # secret/aviary/credentials/{sub}/{namespace}/{key_name}. Leave both
    # empty to fall back to the ``secrets:`` table in config.yaml
    # (single-machine dev without a real Vault).
    vault_addr: str = ""
    vault_token: str = ""

    # Shared secret authenticating the Temporal workflow worker. When the
    # request carries `X-Aviary-Worker-Key: <this>`, the supervisor trusts
    # `on_behalf_of_sub` from the body as the user identity instead of
    # validating a Bearer JWT. Unset in prod disables the worker path.
    worker_shared_secret: str | None = None

    # Unset → direct mode: resolve api_base/api_key from config.yaml.
    llm_gateway_url: str | None = None
    llm_backends_config_path: str = "/workspace/config.yaml"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def direct_llm_mode(self) -> bool:
        return not self.llm_gateway_url

    @property
    def vault_enabled(self) -> bool:
        return bool(self.vault_addr and self.vault_token)

    @property
    def idp_enabled(self) -> bool:
        return bool(self.oidc_issuer)


settings = Settings()
