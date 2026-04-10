from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Agent runtime
    agent_runtime_image: str = "aviary-runtime:latest"
    max_concurrent_sessions_per_pod: int = 5
    host_gateway_ip: str

    # Database
    database_url: str

    # Pod environment — injected into agent runtime containers
    inference_router_url: str
    mcp_gateway_url: str
    litellm_api_key: str
    egress_proxy_url: str
    aviary_api_url: str
    internal_api_key: str
    no_proxy: str = (
        "litellm.platform.svc,"
        "mcp-gateway.platform.svc,"
        "egress-proxy.platform.svc,"
        ".svc,.svc.cluster.local,"
        "localhost,127.0.0.1"
    )

    # Scaling
    scaling_check_interval: int = 30
    sessions_per_pod_scale_up: int = 3
    sessions_per_pod_scale_down: int = 1

    # Idle cleanup
    agent_idle_timeout: int = 604800  # 7 days in seconds
    idle_cleanup_interval: int = 300  # 5 minutes

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
