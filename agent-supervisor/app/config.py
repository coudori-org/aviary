from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Backend selection
    backend_kind: str = "k3s"  # k3s | eks_native | eks_fargate

    # Agent runtime defaults
    agent_runtime_image: str = "aviary-runtime:latest"
    max_concurrent_sessions_per_pod: int = 5
    host_gateway_ip: str
    default_memory_limit: str = "4Gi"
    default_cpu_limit: str = "4"
    default_min_pods: int = 0
    default_max_pods: int = 3

    # Database
    database_url: str

    # Pod environment
    inference_router_url: str
    mcp_gateway_url: str
    litellm_api_key: str
    aviary_api_url: str
    internal_api_key: str

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
