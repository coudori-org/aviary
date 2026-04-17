from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Temporal server
    temporal_host: str = "temporal:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "aviary-workflows"

    # Aviary platform services
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    supervisor_url: str = "http://supervisor:9000"

    # Must match supervisor's WORKER_SHARED_SECRET — this is how the worker
    # authenticates when calling supervisor on behalf of a workflow's owner.
    worker_shared_secret: str

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
