from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://aviary:aviary@localhost:5432/aviary"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # OIDC
    oidc_issuer: str = "http://localhost:8080/realms/aviary"
    # Internal URL for fetching OIDC discovery/JWKS (container-to-container)
    # If unset, falls back to oidc_issuer
    oidc_internal_issuer: str | None = None
    oidc_client_id: str = "aviary-web"
    oidc_audience: str | None = None

    # Vault
    vault_addr: str = "http://localhost:8200"
    vault_token: str = "dev-root-token"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # K8s
    kubeconfig: str | None = None

    # Agent Runtime
    agent_runtime_image: str = "aviary-runtime:latest"
    default_session_timeout: int = 1800
    default_max_sessions_per_agent: int = 20

    # Pod management (agent-per-pod architecture)
    default_agent_idle_timeout: int = 604800  # 7 days in seconds
    default_min_pods: int = 1
    default_max_pods: int = 3
    max_concurrent_sessions_per_pod: int = 10

    # Auto-scaling
    scaling_check_interval: int = 30  # seconds between scaling checks
    sessions_per_pod_scale_up: int = 5  # scale up when sessions/pod exceeds this
    sessions_per_pod_scale_down: int = 2  # scale down when sessions/pod below this

    # Inference
    anthropic_api_key: str | None = None
    inference_ollama_url: str = "http://localhost:11434"
    inference_vllm_url: str = "http://localhost:8001"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
